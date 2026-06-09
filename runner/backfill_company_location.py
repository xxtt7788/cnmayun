#!/usr/bin/env python3
"""
Backfill companies.industry_l2, province, city using EastMoney CompanySurveyAjax.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENV_PATH = "/etc/china-succession/china-succession.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.startswith("export "):
                    key = key[7:]
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value

import requests
from app.db import session_scope
from app.models import Company
from sqlalchemy import select

EASTMONEY_SURVEY_API = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

PROVINCES = {"北京", "上海", "天津", "重庆"}


def build_em_code(ticker: str) -> str:
    ticker = str(ticker).strip()
    if ticker.startswith(("0", "3")):
        return f"SZ{ticker}"
    if ticker.startswith(("4", "8", "9", "92")):
        return f"BJ{ticker}"
    return f"SH{ticker}"


def extract_city(zcdz: str, province: str) -> str:
    """从注册地址中提取城市名."""
    if not zcdz or not province:
        return ""
    if province in PROVINCES:
        return province

    # 去掉省份部分
    remaining = zcdz
    for prefix in [province + "省", province, province + "自治区"]:
        if remaining.startswith(prefix):
            remaining = remaining[len(prefix):]
            break

    # 去掉自治区/自治州等后缀
    for suffix in ["壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "自治州"]:
        if remaining.startswith(suffix):
            remaining = remaining[len(suffix):]
            break

    # 匹配城市名（到第一个"市"或"县"）
    m = re.search(r'^(.+?)(市|县)', remaining)
    if m:
        return m.group(1)

    return ""


def extract_industry_l2(sszjhhy: str) -> str:
    """从证监会行业分类提取二级行业."""
    if not sszjhhy:
        return ""
    if "-" in sszjhhy:
        parts = sszjhhy.split("-")
        return parts[-1].strip()
    return sszjhhy.strip()


def fetch_company_survey(ticker: str) -> dict:
    """Fetch company survey data from EastMoney."""
    em_code = build_em_code(ticker)
    url = f"{EASTMONEY_SURVEY_API}?code={em_code}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("jbzl", {})
    except Exception:
        return {}


def process_company(company: Company) -> tuple[int, dict]:
    """Process a single company, return (company_id, changes_dict)."""
    jbzl = fetch_company_survey(company.ticker)
    if not jbzl:
        return company.id, {}

    changes = {}

    # industry_l2 from sszjhhy
    if not company.industry_l2:
        sszjhhy = jbzl.get("sszjhhy", "")
        industry_l2 = extract_industry_l2(sszjhhy)
        if industry_l2:
            changes["industry_l2"] = industry_l2

    # province from qy
    if not company.province:
        qy = jbzl.get("qy", "")
        if qy:
            changes["province"] = qy

    # city from zcdz
    if not company.city:
        zcdz = jbzl.get("zcdz", "")
        province = changes.get("province") or company.province or qy
        city = extract_city(zcdz, province)
        if city:
            changes["city"] = city

    return company.id, changes


def main():
    with session_scope() as db:
        companies = db.scalars(
            select(Company).where(
                Company.is_active.is_(True),
                (Company.industry_l2.is_(None) | Company.province.is_(None) | Company.city.is_(None))
            )
        ).all()

    print(f"Companies to process: {len(companies)}")
    if not companies:
        print("Nothing to do.")
        return

    updated = 0
    failed = 0
    lock = Lock()
    start_time = time.time()

    def worker(company):
        try:
            cid, changes = process_company(company)
            if changes:
                with session_scope() as db:
                    c = db.scalar(select(Company).where(Company.id == cid))
                    if c:
                        for field, value in changes.items():
                            setattr(c, field, value)
                        db.commit()
                with lock:
                    nonlocal updated
                    updated += 1
        except Exception as e:
            with lock:
                nonlocal failed
                failed += 1

    # Use ThreadPoolExecutor for concurrency
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(worker, c): c for c in companies}
        for i, future in enumerate(as_completed(futures)):
            try:
                future.result()
            except Exception:
                pass
            if (i + 1) % 500 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"  Progress: {i+1}/{len(companies)} | updated={updated} | {rate:.1f}/sec")

    print(f"\nUpdated: {updated}, Failed: {failed}")
    print(f"Total time: {time.time() - start_time:.1f}s")


if __name__ == "__main__":
    main()
