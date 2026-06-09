"""
通过东方财富 CompanyManagementAjax API 批量补全高管 gender/birth_year/education。

数据源: https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax?code={CODE}
返回字段:
  xm: 姓名
  xb: 性别 (男/女)
  nl: 年龄
  xl: 学历 (硕士/博士/本科/大专等)
  zw: 职务
  jj: 简历 (通常包含出生年份, 如 "1967年生")
  rzsj: 任职时间
  cgs: 持股数
  xc: 薪酬

执行方式 (服务器上):
  cd /opt/china-succession
  set -a; source /etc/china-succession/china-succession.env; set +a
  .venv/bin/python runner/enhance_persons_from_eastmoney.py

并发控制:
  脚本默认使用 20 线程并发请求, 可根据网络状况调整 MAX_WORKERS。

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
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.db import session_scope
from app.models import Company, ExecutiveSnapshot, Person
from sqlalchemy import func, select, text

EASTMONEY_MGMT_API = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

# 可调整的并发数
MAX_WORKERS = int(os.getenv("EASTMONEY_ENHANCE_WORKERS", "20"))

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
        raise
    except Exception as e:
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


def find_companies_with_missing_fields(db) -> dict[str, list[Person]]:
    """
    找出有缺失字段的人物, 按公司代码分组.
    返回: {ticker: [Person, ...]}
    """
    # Get disabled company tickers via raw SQL (column exists in DB but not in ORM model)
    disabled_tickers = {row[0] for row in db.execute(text("SELECT ticker FROM companies WHERE executive_sync_disabled = TRUE")).fetchall()}

    stmt = (
        select(Person, Company.ticker, Company.current_ticker)
        .join(ExecutiveSnapshot, Person.id == ExecutiveSnapshot.person_id)
        .join(Company, ExecutiveSnapshot.company_id == Company.id)
        .where(
            (Person.birth_year.is_(None))
            | (Person.education.is_(None))
            | (Person.gender.is_(None))
        )
        .distinct()
    )

    company_to_persons: dict[str, list[Person]] = {}
    for person, ticker, current_ticker in db.execute(stmt).all():
        effective_ticker = (current_ticker or ticker or "").strip()
        if not effective_ticker:
            continue
        # Skip disabled companies
        if ticker in disabled_tickers or (current_ticker and current_ticker in disabled_tickers):
            continue
        if effective_ticker not in company_to_persons:
            company_to_persons[effective_ticker] = []
        # 避免同一人出现在同一公司多次
        if person not in company_to_persons[effective_ticker]:
            company_to_persons[effective_ticker].append(person)

    return company_to_persons


def process_company(ticker: str, persons: list[Person]) -> tuple[int, int, list[str]]:
    """
    处理单个公司: 获取高管列表, 匹配人物, 更新缺失字段.
    返回: (matched_count, updated_count, [log_messages])
    """
    logs: list[str] = []
    managers = fetch_company_managers(ticker)
    if not managers:
        return 0, 0, logs

    # 按姓名建立索引 (同时保留原始姓名和去除空格的姓名)
    manager_by_name: dict[str, dict] = {}
    for m in managers:
        name = (m.get("xm") or "").strip()
        if name:
            manager_by_name[name] = m
            manager_by_name[name.replace(" ", "")] = m

    matched = 0
    updated = 0
    for person in persons:
        manager = manager_by_name.get(person.canonical_name)
        if not manager:
            continue

        matched += 1
        gender = normalize_gender(manager.get("xb"))
        age = manager.get("nl")
        edu = normalize_education(manager.get("xl"))
        resume = manager.get("jj", "")

        # 优先从简历提取出生年份, 其次用年龄推算
        birth_year = extract_birth_year_from_resume(resume)
        if not birth_year and age:
            birth_year = calculate_birth_year(age)

        changed = False
        if gender and not person.gender:
            person.gender = gender
            changed = True
        if birth_year and not person.birth_year:
            person.birth_year = birth_year
            changed = True
        if edu and not person.education:
            person.education = edu
            changed = True

        if changed:
            updated += 1

    return matched, updated, logs


def main():
    print("=" * 60)
    print("东方财富高管信息批量补全")
    print(f"并发数: {MAX_WORKERS}")
    print("=" * 60)

    with session_scope() as db:
        # 先统计基线
        total_missing_birth = db.scalar(
            select(func.count(Person.id)).where(Person.birth_year.is_(None))
        )
        total_missing_edu = db.scalar(
            select(func.count(Person.id)).where(Person.education.is_(None))
        )
        total_missing_gender = db.scalar(
            select(func.count(Person.id)).where(Person.gender.is_(None))
        )
        print(f"\n基线统计:")
        print(f"  缺失 birth_year: {total_missing_birth}")
        print(f"  缺失 education: {total_missing_edu}")
        print(f"  缺失 gender: {total_missing_gender}")

        company_to_persons = find_companies_with_missing_fields(db)
        print(f"\n涉及公司数: {len(company_to_persons)}")
        print(f"涉及人物数: {sum(len(v) for v in company_to_persons.values())}")

        total_matched = 0
        total_updated = 0
        company_count = 0
        failed_tickers: list[str] = []

        start_time = time.time()

        # 并发处理
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_ticker = {
                executor.submit(process_company, ticker, persons): ticker
                for ticker, persons in company_to_persons.items()
            }

            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                company_count += 1
                try:
                    matched, updated, _ = future.result()
                    total_matched += matched
                    total_updated += updated
                    if company_count % 50 == 0:
                        elapsed = time.time() - start_time
                        print(
                            f"  进度: {company_count}/{len(company_to_persons)} "
                            f"({company_count/len(company_to_persons)*100:.1f}%), "
                            f"耗时 {elapsed/60:.1f} 分钟, "
                            f"匹配 {total_matched} 人, 更新 {total_updated} 人"
                        )
                except Exception as e:
                    failed_tickers.append(ticker)
                    print(f"  {ticker}: 异常: {e}")

        db.commit()

        # 再统计
        after_missing_birth = db.scalar(
            select(func.count(Person.id)).where(Person.birth_year.is_(None))
        )
        after_missing_edu = db.scalar(
            select(func.count(Person.id)).where(Person.education.is_(None))
        )
        after_missing_gender = db.scalar(
            select(func.count(Person.id)).where(Person.gender.is_(None))
        )

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("执行完成")
    print("=" * 60)
    print(f"处理公司: {company_count}")
    print(f"失败公司: {len(failed_tickers)}")
    print(f"匹配人物: {total_matched}")
    print(f"更新记录: {total_updated}")
    print(f"总耗时: {total_elapsed/60:.1f} 分钟")
    print(f"\nbirth_year: {total_missing_birth} -> {after_missing_birth} (补全 {total_missing_birth - after_missing_birth})")
    print(f"education: {total_missing_edu} -> {after_missing_edu} (补全 {total_missing_edu - after_missing_edu})")
    print(f"gender: {total_missing_gender} -> {after_missing_gender} (补全 {total_missing_gender - after_missing_gender})")

    if failed_tickers:
        print(f"\n失败的公司代码 ({len(failed_tickers)} 家):")
        print(", ".join(failed_tickers[:20]) + ("..." if len(failed_tickers) > 20 else ""))


if __name__ == "__main__":
    main()
