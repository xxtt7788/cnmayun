#!/usr/bin/env python3
"""
Backfill companies.industry_l2, province, city using EastMoney CompanySurveyAjax.
V3: Batch updates, simplified city fallback, single session per batch.

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
    # Fallback: try to find any known city in zcdz
    return ""


def fetch_company_survey(ticker: str) -> dict:
    em_code = build_em_code(ticker)
    url = f"{EASTMONEY_SURVEY_API}?code={em_code}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        return resp.json().get("jbzl", {})
    except Exception:
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

    print(f"Companies to process: {len(companies)}")
    if not companies:
        print("Nothing to do.")
        return

    updated = 0
    failed = 0
    start_time = time.time()

    for i, company in enumerate(companies):
        try:
            jbzl = fetch_company_survey(company.ticker)
            if not jbzl:
                failed += 1
                continue

            changed = False

            if not company.industry_l2:
                sszjhhy = jbzl.get("sszjhhy", "")
                if sszjhhy and "-" in sszjhhy:
                    company.industry_l2 = sszjhhy.split("-")[-1].strip()
                elif sszjhhy:
                    company.industry_l2 = sszjhhy.strip()
                if company.industry_l2:
                    changed = True

            if not company.province:
                qy = jbzl.get("qy", "")
                if qy:
                    company.province = qy
                    changed = True

            if not company.city:
                zcdz = jbzl.get("zcdz", "")
                province = company.province or qy
                city = extract_city(zcdz, province)
                if city:
                    company.city = city
                    changed = True
                elif province and province not in PROVINCES:
                    # Fallback: some addresses don't have explicit city
                    pass

            if changed:
                updated += 1

        except Exception as e:
            failed += 1
            print(f"  ERROR {company.ticker}: {e}")

        if (i + 1) % 200 == 0 or (i + 1) == len(companies):
            # Commit batch
            with session_scope() as db:
                db.commit()
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  Progress: {i+1}/{len(companies)} | updated={updated} | failed={failed} | {rate:.1f}/sec")

        time.sleep(0.25)

    # Final commit
    with session_scope() as db:
        db.commit()

    print(f"\nUpdated: {updated}, Failed: {failed}")
    print(f"Total time: {time.time() - start_time:.1f}s")


if __name__ == "__main__":
    main()
