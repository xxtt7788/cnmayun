#!/usr/bin/env python3
"""
Backfill companies.industry_l2, province, city using EastMoney CompanySurveyAjax.
V2: Retry logic, BJ filter, single-thread per-company with batch commit.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys
import time
import re

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
    if not zcdz or not province:
        return ""
    if province in PROVINCES:
        return province
    remaining = zcdz
    for prefix in [province + "省", province, province + "自治区"]:
        if remaining.startswith(prefix):
            remaining = remaining[len(prefix):]
            break
    for suffix in ["壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "自治州"]:
        if remaining.startswith(suffix):
            remaining = remaining[len(suffix):]
            break
    m = re.search(r'^(.+?)(市|县)', remaining)
    if m:
        return m.group(1)
    return ""


def extract_industry_l2(sszjhhy: str) -> str:
    if not sszjhhy:
        return ""
    if "-" in sszjhhy:
        return sszjhhy.split("-")[-1].strip()
    return sszjhhy.strip()


def fetch_company_survey(ticker: str, retries: int = 3) -> dict:
    em_code = build_em_code(ticker)
    url = f"{EASTMONEY_SURVEY_API}?code={em_code}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
            return resp.json().get("jbzl", {})
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return {}


def main():
    with session_scope() as db:
        companies = db.scalars(
            select(Company).where(
                Company.is_active.is_(True),
                (Company.industry_l2.is_(None) | Company.province.is_(None) | Company.city.is_(None)),
                Company.ticker.notlike("4%"),
                Company.ticker.notlike("8%"),
                Company.ticker.notlike("9%"),
            )
        ).all()

    print(f"Non-BJ companies to process: {len(companies)}")
    if not companies:
        print("Nothing to do.")
        return

    updated = 0
    failed = 0
    start_time = time.time()

    for i, company in enumerate(companies):
        jbzl = fetch_company_survey(company.ticker)
        if not jbzl:
            failed += 1
            continue

        changes = {}
        if not company.industry_l2:
            sszjhhy = jbzl.get("sszjhhy", "")
            industry_l2 = extract_industry_l2(sszjhhy)
            if industry_l2:
                changes["industry_l2"] = industry_l2

        if not company.province:
            qy = jbzl.get("qy", "")
            if qy:
                changes["province"] = qy

        if not company.city:
            zcdz = jbzl.get("zcdz", "")
            province = changes.get("province") or company.province or qy
            city = extract_city(zcdz, province)
            if city:
                changes["city"] = city

        if changes:
            try:
                with session_scope() as db:
                    c = db.scalar(select(Company).where(Company.id == company.id))
                    if c:
                        for field, value in changes.items():
                            setattr(c, field, value)
                        db.commit()
                        updated += 1
            except Exception:
                failed += 1

        if (i + 1) % 200 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  Progress: {i+1}/{len(companies)} | updated={updated} | failed={failed} | {rate:.1f}/sec")

        time.sleep(0.25)

    print(f"\nUpdated: {updated}, Failed: {failed}")
    print(f"Total time: {time.time() - start_time:.1f}s")


if __name__ == "__main__":
    main()
