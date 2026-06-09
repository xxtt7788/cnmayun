#!/usr/bin/env python3
"""
Backfill executive_snapshots.compensation from EastMoney API.

EastMoney CompanyManagementAjax returns a 'xc' (薪酬) field for some companies.
This script fetches current management lists and extracts compensation data.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from __future__ import annotations

import json
import os
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
from app.models import Company, ExecutiveSnapshot
from sqlalchemy import select, text

EASTMONEY_MGMT_API = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

MAX_WORKERS = int(os.getenv("BACKFILL_WORKERS", "20"))


def build_em_code(ticker: str) -> str:
    ticker = str(ticker).strip()
    if ticker.startswith("6") or ticker.startswith("5"):
        return f"SH{ticker}"
    return f"SZ{ticker}"


def fetch_company_management(ticker: str) -> list[dict]:
    em_code = build_em_code(ticker)
    url = f"{EASTMONEY_MGMT_API}?code={em_code}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("RptManagerList") or []
    except Exception:
        return []


def main():
    with session_scope() as db:
        disabled_ids = {row[0] for row in db.execute(text("SELECT id FROM companies WHERE executive_sync_disabled = TRUE")).fetchall()}
        companies = db.scalars(select(Company).where(Company.is_active.is_(True))).all()
        companies = [c for c in companies if c.id not in disabled_ids]

    print(f"Companies to process: {len(companies)}")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 60)

    # Fetch all management lists
    results: dict[int, list[dict]] = {}
    processed = 0
    failed_tickers = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(fetch_company_management, c.ticker): c
            for c in companies
        }
        for future in as_completed(future_map):
            company = future_map[future]
            processed += 1
            try:
                managers = future.result()
                if managers:
                    results[company.id] = managers
            except Exception as e:
                failed_tickers.append(company.ticker)
                print(f"  ERROR {company.ticker}: {e}")

            if processed % 500 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Fetch progress: {processed}/{len(companies)} | success={len(results)} | {rate:.1f}/sec")

    fetch_elapsed = time.time() - start_time
    print(f"\nFetch complete: {len(results)} companies, {len(failed_tickers)} failed, {fetch_elapsed:.1f}s")

    # Extract compensation data
    comp_updates: list[tuple[int, float]] = []
    comp_field_found = 0

    for cid, managers in results.items():
        for m in managers:
            name = m.get("xm", "").strip()
            # Check multiple possible compensation field names
            comp_raw = m.get("xc") or m.get("gz") or m.get("salary") or m.get("薪酬") or m.get("年薪")
            if comp_raw and name:
                comp_field_found += 1
                # Parse compensation value
                try:
                    comp_str = str(comp_raw).replace(",", "").replace("万", "").strip()
                    if comp_str and comp_str.replace(".", "").isdigit():
                        comp_val = float(comp_str)
                        if 0 < comp_val < 10000:  # Reasonable range (万元)
                            comp_updates.append((cid, name, comp_val))
                except (ValueError, TypeError):
                    pass

    print(f"Records with comp field: {comp_field_found}")
    print(f"Parsed compensation values: {len(comp_updates)}")

    if comp_updates:
        print("\nSample:")
        for cid, name, val in comp_updates[:10]:
            print(f"  company={cid}, name={name}, comp={val}万")

    # Apply updates to executive_snapshots
    updated = 0
    with session_scope() as db:
        for cid, name, comp_val in comp_updates:
            result = db.execute(
                text("""
                    UPDATE executive_snapshots 
                    SET compensation = :comp
                    WHERE company_id = :cid AND person_name_raw = :name
                    AND compensation IS NULL
                """),
                {"comp": comp_val, "cid": cid, "name": name}
            )
            if result.rowcount > 0:
                updated += result.rowcount

        db.commit()

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("COMPENSATION BACKFILL COMPLETE")
    print(f"  Snapshots updated: {updated}")
    print(f"  Fetch time: {fetch_elapsed:.1f}s")
    print(f"  Total time: {total_elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
