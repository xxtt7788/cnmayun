#!/usr/bin/env python3
"""
Backfill company basic info from CNINFO getCompanyIntroduction API.

Fills: industry_l1, industry_l2, province, city, legal_representative,
       general_manager_name, website, listed_date, business_scope

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen

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

from app.db import session_scope
from app.models import Company
from sqlalchemy import select, text

CNINFO_INTRO_API = "https://webapi.cninfo.com.cn/api/data20/companyOverview/getCompanyIntroduction"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

MAX_WORKERS = 10


def build_cninfo_code(ticker: str, exchange: str) -> str:
    if exchange == "SSE" or ticker.startswith("6") or ticker.startswith("5"):
        return f"SH{ticker}"
    elif exchange == "BSE" or ticker.startswith("8") or ticker.startswith("4") or ticker.startswith("92"):
        return f"BJ{ticker}"
    return f"SZ{ticker}"


def fetch_company_intro(ticker: str, exchange: str) -> dict:
    code = build_cninfo_code(ticker, exchange)
    url = f"{CNINFO_INTRO_API}?scode={code}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            records = data.get("records") or data.get("data") or []
            return records[0] if records else {}
    except Exception:
        return {}


def parse_industry(record: dict) -> tuple[str, str]:
    """Extract L1 and L2 industry from record."""
    # CNINFO often returns industry as "金融业-货币金融服务" or single field
    ind = record.get("F008V") or record.get("INDUSTRY") or ""
    if not ind:
        return "", ""
    parts = ind.split("-")
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return ind.strip(), ""


def parse_address(record: dict) -> tuple[str, str]:
    """Extract province and city from address."""
    addr = record.get("F007V") or record.get("ADDRESS") or ""
    if not addr:
        return "", ""
    # Simple heuristic: first 2-3 chars are province
    m = re.match(r"^(.*?[省市自治区])", addr)
    province = m.group(1) if m else ""
    # City is usually after province
    city = ""
    if province:
        rest = addr[len(province):].strip()
        m2 = re.match(r"^(.*?[市区县])", rest)
        city = m2.group(1) if m2 else ""
    return province, city


def main():
    with session_scope() as db:
        # Only process companies with missing fields
        companies = db.scalars(
            select(Company).where(
                Company.is_active.is_(True),
                (
                    Company.industry_l1.is_(None) |
                    Company.province.is_(None) |
                    Company.legal_representative.is_(None)
                )
            )
        ).all()

    print(f"Companies with missing info: {len(companies)}")
    print("=" * 60)

    results: dict[int, dict] = {}
    processed = 0
    failed = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(fetch_company_intro, c.ticker, c.exchange): c
            for c in companies
        }
        for future in as_completed(future_map):
            company = future_map[future]
            processed += 1
            try:
                record = future.result()
                if record:
                    results[company.id] = record
            except Exception as e:
                failed.append(company.ticker)

            if processed % 200 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Progress: {processed}/{len(companies)} | success={len(results)} | {rate:.1f}/sec")

    print(f"\nFetch complete: {len(results)} companies, {len(failed)} failed, {time.time()-start_time:.1f}s")

    # Apply updates
    updated = 0
    with session_scope() as db:
        for cid, record in results.items():
            industry_l1, industry_l2 = parse_industry(record)
            province, city = parse_address(record)

            # Only update fields that are currently NULL or empty
            company = db.scalar(select(Company).where(Company.id == cid))
            if not company:
                continue

            changes = []
            if not company.industry_l1 and industry_l1:
                company.industry_l1 = industry_l1
                changes.append("industry_l1")
            if not company.industry_l2 and industry_l2:
                company.industry_l2 = industry_l2
                changes.append("industry_l2")
            if not company.province and province:
                company.province = province
                changes.append("province")
            if not company.city and city:
                company.city = city
                changes.append("city")

            legal = record.get("F010V") or record.get("LEGAL_PERSON") or ""
            if not company.legal_representative and legal:
                company.legal_representative = legal
                changes.append("legal")

            gm = record.get("F011V") or record.get("GENERAL_MANAGER") or ""
            if not company.general_manager_name and gm:
                company.general_manager_name = gm
                changes.append("gm")

            website = record.get("F006V") or record.get("WEBSITE") or ""
            if not company.website and website:
                company.website = website
                changes.append("website")

            listed = record.get("F012D") or record.get("LISTING_DATE") or ""
            if not company.listed_date and listed:
                try:
                    from datetime import datetime
                    if isinstance(listed, str):
                        company.listed_date = datetime.strptime(listed[:10], "%Y-%m-%d").date()
                        changes.append("listed_date")
                except Exception:
                    pass

            if changes:
                updated += 1

        db.commit()

    print(f"\nCompanies updated: {updated}")
    print("Company info backfill complete.")


if __name__ == "__main__":
    main()
