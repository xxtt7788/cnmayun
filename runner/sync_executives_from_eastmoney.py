"""
通过东方财富 CompanyManagementAjax API 全量同步公司高管快照，
同时补齐现有高管个人信息，并将未入库的高管新建入库。

数据源: https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax?code={CODE}

执行方式 (服务器上):
  cd /opt/china-succession
  set -a; source /etc/china-succession/china-succession.env; set +a
  .venv/bin/python runner/sync_executives_from_eastmoney.py

并发控制:
  脚本默认使用 20 线程并发请求, 可根据网络状况调整 MAX_WORKERS 环境变量。

Author: AI Assistant (Kimi)
Date: 2026-04-25
Modified: Added executive_sync_disabled filter
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.db import session_scope
from app.models import Company, ExecutiveSnapshot, Person, RoleTenure
from app.normalization import extract_canonical_roles, is_core_role, role_priority
from sqlalchemy import delete, func, select, text

EASTMONEY_MGMT_API = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

MAX_WORKERS = int(os.getenv("EASTMONEY_SYNC_WORKERS", "20"))

# 简历中抽取出生年份的正则模式
BIRTH_YEAR_PATTERNS = [
    re.compile(r"(\d{4})年生"),
    re.compile(r"(\d{4})年出生"),
    re.compile(r"生于(\d{4})年"),
    re.compile(r"(\d{4})年\d{1,2}月生"),
    re.compile(r"(\d{4})年\d{1,2}月\d{1,2}日生"),
]

# 学历标准化映射
EDU_MAP = {
    "博士": "博士",
    "硕士": "硕士",
    "研究生": "硕士",
    "MBA": "硕士",
    "EMBA": "硕士",
    "本科": "本科",
    "学士": "本科",
    "大专": "大专",
    "专科": "大专",
    "中专": "中专",
    "高中": "高中",
    "初中": "初中",
    "小学": "小学",
}


def build_em_code(ticker: str) -> str:
    """将 A 股代码转换为东方财富格式."""
    if ticker.startswith(("0", "3")):
        return f"SZ{ticker}"
    if ticker.startswith(("4", "8", "9", "92")):
        return f"BJ{ticker}"
    return f"SH{ticker}"


def fetch_company_managers(ticker: str) -> list[dict]:
    """获取单家公司的高管列表."""
    code = build_em_code(ticker)
    url = f"{EASTMONEY_MGMT_API}?code={code}"
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/Index?type=web&code={code}",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("RptManagerList", [])
    except HTTPError as e:
        if e.code == 404:
            return []
        return []
    except Exception:
        return []


def extract_birth_year_from_resume(resume: str | None) -> int | None:
    """从简历文本中提取出生年份."""
    if not resume:
        return None
    for pattern in BIRTH_YEAR_PATTERNS:
        match = pattern.search(resume)
        if match:
            year = int(match.group(1))
            if 1940 <= year <= 2010:
                return year
    return None


def normalize_education(edu: str | None) -> str | None:
    """标准化学历字符串."""
    if not edu:
        return None
    edu = edu.strip()
    for key, val in EDU_MAP.items():
        if key in edu:
            return val
    return edu if edu != "--" else None


def normalize_gender(gender: str | None) -> str | None:
    """标准化性别字符串."""
    if not gender:
        return None
    gender = gender.strip()
    if gender in ("男", "M", "Male", "male"):
        return "male"
    if gender in ("女", "F", "Female", "female"):
        return "female"
    return None


def calculate_birth_year(age: str | int | None) -> int | None:
    """根据年龄计算出生年份."""
    if age is None:
        return None
    try:
        age = int(age)
        if not (20 <= age <= 100):
            return None
        return date.today().year - age
    except (ValueError, TypeError):
        return None


def process_all_companies(companies: list[Company]) -> dict[str, list[dict]]:
    """
    并发爬取所有公司的高管数据.
    返回: {ticker: [manager_dict, ...]}
    """
    results: dict[str, list[dict]] = {}
    completed = 0
    total = len(companies)
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_company = {
            executor.submit(fetch_company_managers, c.current_ticker or c.ticker): c for c in companies
        }
        for future in as_completed(future_to_company):
            company = future_to_company[future]
            completed += 1
            try:
                managers = future.result()
                if managers:
                    results[company.ticker] = managers
            except Exception as e:
                print(f"  {company.ticker}: API 异常: {e}")

            if completed % 100 == 0:
                elapsed = time.time() - start_time
                print(
                    f"  爬取进度: {completed}/{total} "
                    f"({completed/total*100:.1f}%), "
                    f"耗时 {elapsed/60:.1f} 分钟, "
                    f"成功 {len(results)} 家"
                )

    return results


def main():
    print("=" * 60)
    print("东方财富高管全量同步")
    print(f"并发数: {MAX_WORKERS}")
    print("=" * 60)

    with session_scope() as db:
        # ===== 基线统计 =====
        # Get disabled company IDs via raw SQL (column exists in DB but not in ORM model)
        disabled_ids = {row[0] for row in db.execute(text("SELECT id FROM companies WHERE executive_sync_disabled = TRUE")).fetchall()}

        baseline = {
            "companies": db.scalar(select(func.count(Company.id)).where(Company.is_active == True)) - len(disabled_ids),
            "persons": db.scalar(select(func.count(Person.id))),
            "snapshots": db.scalar(select(func.count(ExecutiveSnapshot.id))),
            "missing_birth": db.scalar(select(func.count(Person.id)).where(Person.birth_year.is_(None))),
            "missing_edu": db.scalar(select(func.count(Person.id)).where(Person.education.is_(None))),
            "missing_gender": db.scalar(select(func.count(Person.id)).where(Person.gender.is_(None))),
        }
        print(f"\n基线统计:")
        print(f"  活跃公司: {baseline['companies']}")
        print(f"  人物总数: {baseline['persons']}")
        print(f"  快照总数: {baseline['snapshots']}")
        print(f"  缺失 birth_year: {baseline['missing_birth']}")
        print(f"  缺失 education: {baseline['missing_edu']}")
        print(f"  缺失 gender: {baseline['missing_gender']}")

        # ===== 预加载所有公司和人物 =====
        print("\n预加载数据...")
        companies = list(db.scalars(select(Company).where(Company.is_active == True)).all())
        companies = [c for c in companies if c.id not in disabled_ids]
        company_by_ticker: dict[str, Company] = {}
        for c in companies:
            company_by_ticker[c.ticker] = c
            if c.current_ticker and c.current_ticker != c.ticker:
                company_by_ticker[c.current_ticker] = c

        persons = list(db.scalars(select(Person)).all())
        person_by_name: dict[str, Person] = {}
        for p in persons:
            person_by_name[p.canonical_name] = p
            person_by_name[p.canonical_name.replace(" ", "")] = p

        print(f"  加载公司: {len(companies)}")
        print(f"  加载人物: {len(persons)}")

        # ===== 阶段1: 并发爬取所有公司高管数据 =====
        print(f"\n阶段1: 并发爬取高管数据 ({len(companies)} 家公司)...")
        start_time = time.time()
        company_managers = process_all_companies(companies)
        fetch_elapsed = time.time() - start_time
        print(f"  爬取完成: {len(company_managers)} 家公司有数据, 耗时 {fetch_elapsed/60:.1f} 分钟")

        # ===== 阶段2: 串行写入数据库 =====
        print(f"\n阶段2: 写入数据库...")
        start_time = time.time()

        total_managers = 0
        created_persons = 0
        updated_persons = 0
        created_snapshots = 0
        created_tenures = 0
        skipped_no_role = 0

        snapshot_date = date.today()

        for ticker, managers in company_managers.items():
            company = company_by_ticker.get(ticker)
            if not company:
                continue

            # 删除该公司由东方财富创建的旧快照
            db.execute(
                delete(ExecutiveSnapshot).where(
                    ExecutiveSnapshot.company_id == company.id,
                    ExecutiveSnapshot.source_platform == "EASTMONEY",
                )
            )

            for manager in managers:
                name = (manager.get("xm") or "").strip()
                if not name:
                    continue

                total_managers += 1

                # 匹配或创建 Person
                person = person_by_name.get(name) or person_by_name.get(name.replace(" ", ""))
                if not person:
                    person = Person(canonical_name=name)
                    db.add(person)
                    db.flush()
                    person_by_name[name] = person
                    person_by_name[name.replace(" ", "")] = person
                    created_persons += 1

                # 提取字段
                gender = normalize_gender(manager.get("xb"))
                age = manager.get("nl")
                edu = normalize_education(manager.get("xl"))
                resume = manager.get("jj", "")
                birth_year = extract_birth_year_from_resume(resume)
                if not birth_year and age:
                    birth_year = calculate_birth_year(age)

                # 更新 Person（仅补充缺失字段）
                person_updated = False
                if gender and not person.gender:
                    person.gender = gender
                    person_updated = True
                if birth_year and not person.birth_year:
                    person.birth_year = birth_year
                    person_updated = True
                if edu and not person.education:
                    person.education = edu
                    person_updated = True
                if person_updated:
                    updated_persons += 1

                # 提取角色
                title_raw = manager.get("zw", "")
                canonical_roles = extract_canonical_roles(title_raw)
                if not canonical_roles:
                    # 如果没有识别到标准角色，尝试兜底
                    if title_raw:
                        # 至少标记为高管
                        canonical_roles = ["senior_management"]
                    else:
                        skipped_no_role += 1
                        continue

                for role in canonical_roles:
                    # 创建 ExecutiveSnapshot
                    snapshot = ExecutiveSnapshot(
                        company_id=company.id,
                        person_id=person.id,
                        snapshot_date=snapshot_date,
                        source_platform="EASTMONEY",
                        source_api="/PC_HSF10/CompanyManagement/CompanyManagementAjax",
                        source_url=f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/Index?type=web&code={build_em_code(ticker)}",
                        person_name_raw=name,
                        title_raw=title_raw,
                        role_canonical=role,
                        role_priority=role_priority(role),
                        gender=gender,
                        birth_year=birth_year,
                        education=edu,
                        is_core_role=is_core_role(role),
                        confidence=Decimal("0.90"),
                    )
                    db.add(snapshot)
                    created_snapshots += 1

                    # 查询是否已存在相同的 RoleTenure
                    existing_tenure = db.scalar(
                        select(RoleTenure).where(
                            RoleTenure.company_id == company.id,
                            RoleTenure.person_id == person.id,
                            RoleTenure.role_canonical == role,
                        )
                    )
                    if existing_tenure:
                        existing_tenure.role_raw_latest = title_raw
                        existing_tenure.is_active = True
                    else:
                        tenure = RoleTenure(
                            company_id=company.id,
                            person_id=person.id,
                            role_canonical=role,
                            role_raw_latest=title_raw,
                            is_active=True,
                            inferred_flag=True,
                            confidence=Decimal("0.90"),
                        )
                        db.add(tenure)
                        created_tenures += 1

            # 每 50 家公司 commit 一次
            if created_snapshots % 500 == 0:
                db.commit()

        db.commit()
        write_elapsed = time.time() - start_time

        # ===== 最终统计 =====
        after = {
            "persons": db.scalar(select(func.count(Person.id))),
            "snapshots": db.scalar(select(func.count(ExecutiveSnapshot.id))),
            "missing_birth": db.scalar(select(func.count(Person.id)).where(Person.birth_year.is_(None))),
            "missing_edu": db.scalar(select(func.count(Person.id)).where(Person.education.is_(None))),
            "missing_gender": db.scalar(select(func.count(Person.id)).where(Person.gender.is_(None))),
        }

    print("\n" + "=" * 60)
    print("执行完成")
    print("=" * 60)
    print(f"爬取耗时: {fetch_elapsed/60:.1f} 分钟")
    print(f"写入耗时: {write_elapsed/60:.1f} 分钟")
    print(f"\n数据变动:")
    print(f"  爬取高管记录: {total_managers}")
    print(f"  新建人物: {created_persons}")
    print(f"  更新人物: {updated_persons}")
    print(f"  新建快照: {created_snapshots}")
    print(f"  新建/更新任职: {created_tenures}")
    print(f"  跳过(无角色): {skipped_no_role}")
    print(f"\n人物库:")
    print(f"  总数: {baseline['persons']} -> {after['persons']} (+{after['persons'] - baseline['persons']})")
    print(f"  birth_year: {baseline['missing_birth']} -> {after['missing_birth']} (补全 {baseline['missing_birth'] - after['missing_birth']})")
    print(f"  education: {baseline['missing_edu']} -> {after['missing_edu']} (补全 {baseline['missing_edu'] - after['missing_edu']})")
    print(f"  gender: {baseline['missing_gender']} -> {after['missing_gender']} (补全 {baseline['missing_gender'] - after['missing_gender']})")
    print(f"\n快照库:")
    print(f"  总数: {baseline['snapshots']} -> {after['snapshots']} (+{after['snapshots'] - baseline['snapshots']})")


if __name__ == "__main__":
    main()
