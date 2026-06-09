#!/usr/bin/env python3
"""
Backfill RoleTenure end_date and is_active from EastMoney current management list.

Strategy:
  1. Fetch current management list from EastMoney API for each active company.
  2. Compare with existing RoleTenure records:
     - Person IN current list  → is_active=True (if not already set)
     - Person NOT IN current list → end_date=today, is_active=False
  3. Names matched against Person.canonical_name (exact match).

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env file directly
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
from app.models import Company, Person, RoleTenure
from sqlalchemy import func, select, text

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

    # Fetch current management lists
    current_names_by_company: dict[int, set[str]] = {}
    processed = 0
    failed_tickers = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(lambda c=c: (c.id, c.ticker, fetch_company_management(c.ticker))): c
            for c in companies
        }
        for future in as_completed(future_map):
            company = future_map[future]
            processed += 1
            try:
                cid, ticker, managers = future.result()
                names = {m.get("xm", "").strip() for m in managers if m.get("xm", "").strip()}
                if names:
                    current_names_by_company[cid] = names
            except Exception as e:
                failed_tickers.append(company.ticker)
                print(f"  ERROR {company.ticker}: {e}")

            if processed % 200 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Fetch progress: {processed}/{len(companies)} | success={len(current_names_by_company)} | {rate:.1f}/sec")

    fetch_elapsed = time.time() - start_time
    print(f"\nFetch complete: {len(current_names_by_company)} companies, {len(failed_tickers)} failed, {fetch_elapsed:.1f}s")

    # Load all tenures and persons
    with session_scope() as db:
        all_tenures = db.scalars(select(RoleTenure)).all()
        all_persons = db.scalars(select(Person)).all()

    person_name_by_id = {p.id: (p.canonical_name or "").strip() for p in all_persons}

    # Group tenures by company_id
    tenures_by_company: dict[int, list[RoleTenure]] = {}
    for t in all_tenures:
        tenures_by_company.setdefault(t.company_id, []).append(t)

    today = date.today()
    end_updates: list[tuple[int, date]] = []
    deactivate_updates: list[int] = []
    activate_updates: list[int] = []

    for cid, tenure_list in tenures_by_company.items():
        current_names = current_names_by_company.get(cid, set())
        for t in tenure_list:
            name = person_name_by_id.get(t.person_id, "")
            if not name:
                continue
            if name in current_names:
                # Still active
                if not t.is_active:
                    activate_updates.append(t.id)
            else:
                # No longer in current management list
                if t.end_date is None:
                    end_updates.append((t.id, today))
                if t.is_active:
                    deactivate_updates.append(t.id)

    print(f"Tenures to set end_date: {len(end_updates)}")
    print(f"Tenures to deactivate: {len(deactivate_updates)}")
    print(f"Tenures to re-activate: {len(activate_updates)}")

    # Apply updates in batches
    BATCH_SIZE = 1000
    updated_end = 0
    updated_deact = 0
    updated_act = 0

    with session_scope() as db:
        # Update end_date
        for i in range(0, len(end_updates), BATCH_SIZE):
            batch = end_updates[i:i+BATCH_SIZE]
            ids = [tid for tid, _ in batch]
            objs = {t.id: t for t in db.scalars(select(RoleTenure).where(RoleTenure.id.in_(ids))).all()}
            for tid, end_date in batch:
                t = objs.get(tid)
                if t and t.end_date is None:
                    t.end_date = end_date
                    updated_end += 1

        # Deactivate
        for i in range(0, len(deactivate_updates), BATCH_SIZE):
            batch = deactivate_updates[i:i+BATCH_SIZE]
            for t in db.scalars(select(RoleTenure).where(RoleTenure.id.in_(batch))).all():
                if t.is_active:
                    t.is_active = False
                    updated_deact += 1

        # Activate
        for i in range(0, len(activate_updates), BATCH_SIZE):
            batch = activate_updates[i:i+BATCH_SIZE]
            for t in db.scalars(select(RoleTenure).where(RoleTenure.id.in_(batch))).all():
                if not t.is_active:
                    t.is_active = True
                    updated_act += 1

        db.commit()

    update_elapsed = time.time() - start_time - fetch_elapsed

    with session_scope() as db:
        after_end = db.scalar(select(func.count(RoleTenure.id)).where(RoleTenure.end_date.isnot(None)))
        after_active = db.scalar(select(func.count(RoleTenure.id)).where(RoleTenure.is_active == True))
        after_inactive = db.scalar(select(func.count(RoleTenure.id)).where(RoleTenure.is_active == False))

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print(f"  End dates updated: {updated_end}")
    print(f"  Deactivated: {updated_deact}")
    print(f"  Re-activated: {updated_act}")
    print(f"  Has end_date: {after_end}")
    print(f"  Active tenures: {after_active}")
    print(f"  Inactive tenures: {after_inactive}")
    print(f"  Fetch time: {fetch_elapsed:.1f}s")
    print(f"  Update time: {update_elapsed:.1f}s")
    print(f"  Total time: {total_elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
