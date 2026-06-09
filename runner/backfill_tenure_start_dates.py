"""
Backfill RoleTenure.start_date from EastMoney API rzsj (任职时间) field.

Strategy:
  1. Pre-load all (company_id, ticker, person_id, person_name) needing backfill.
  2. Concurrently fetch management list from EastMoney API per company.
  3. Match executives by name, extract date from rzsj.
  4. Batch-update RoleTenure records.

Author: AI Assistant (Kimi)
Date: 2026-04-25
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
RZSJ_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


def build_em_code(ticker: str) -> str:
    ticker = str(ticker).strip()
    if ticker.startswith("6") or ticker.startswith("5"):
        return f"SH{ticker}"
    return f"SZ{ticker}"


def fetch_company_management(ticker: str) -> list[dict]:
    """Fetch executive list from EastMoney API."""
    em_code = build_em_code(ticker)
    url = f"{EASTMONEY_MGMT_API}?code={em_code}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("RptManagerList") or []
    except Exception:
        return []


def parse_rzsj(rzsj: str | None) -> date | None:
    if not rzsj:
        return None
    m = RZSJ_PATTERN.search(rzsj)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def fetch_for_company(company_id: int, ticker: str) -> tuple[int, str, list[dict]]:
    """Pure fetch, no DB. Returns (company_id, ticker, managers)."""
    managers = fetch_company_management(ticker)
    return company_id, ticker, managers


def main():
    with session_scope() as db:
        # Load active companies
        companies = list(db.scalars(
            select(Company).where(Company.is_active.is_(True))
        ).all())
        company_by_id = {c.id: c for c in companies}

        # Load all persons
        persons = db.scalars(select(Person)).all()
        person_names = {p.id: (p.canonical_name or "").strip() for p in persons}

        # Count missing before
        missing_before = db.scalar(
            select(func.count(RoleTenure.id)).where(RoleTenure.start_date.is_(None))
        )

        # Pre-load all tenures needing backfill into memory
        all_tenures = db.scalars(
            select(RoleTenure).where(RoleTenure.start_date.is_(None))
        ).all()

    # Build lookup: (company_id, person_name_lower) -> list of tenure objects (as dict)
    # But we can't hold ORM objects across sessions. Build ID-based lookup.
    tenure_ids_by_company_person: dict[tuple[int, int], list[int]] = {}
    for t in all_tenures:
        key = (t.company_id, t.person_id)
        tenure_ids_by_company_person.setdefault(key, []).append(t.id)

    print(f"Companies to process: {len(companies)}")
    print(f"Tenures missing start_date: {missing_before}")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 60)

    # Phase 1: Concurrently fetch all API data
    results: dict[int, dict[str, date]] = {}  # company_id -> {name -> date}
    processed = 0
    failed_tickers = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(fetch_for_company, c.id, c.ticker): c
            for c in companies
        }
        for future in as_completed(future_map):
            company = future_map[future]
            processed += 1
            try:
                cid, ticker, managers = future.result()
                name_to_date: dict[str, date] = {}
                for m in managers:
                    name = m.get("xm", "").strip()
                    start = parse_rzsj(m.get("rzsj", ""))
                    if name and start:
                        if name not in name_to_date or start < name_to_date[name]:
                            name_to_date[name] = start
                if name_to_date:
                    results[cid] = name_to_date
            except Exception as e:
                failed_tickers.append(ticker)
                print(f"  ERROR {ticker}: {e}")

            if processed % 200 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Fetch progress: {processed}/{len(companies)} | "
                      f"success={len(results)} | {rate:.1f}/sec")

    fetch_elapsed = time.time() - start_time
    print(f"\nFetch complete: {len(results)} companies with data, "
          f"{failed_tickers and len(failed_tickers) or 0} failed, {fetch_elapsed:.1f}s")

    # Phase 2: Build update map
    updates: dict[int, date] = {}  # tenure_id -> start_date
    matched_persons = 0

    for cid, name_to_date in results.items():
        for pid, name in person_names.items():
            start = name_to_date.get(name)
            if not start:
                continue
            key = (cid, pid)
            tids = tenure_ids_by_company_person.get(key)
            if tids:
                matched_persons += 1
                for tid in tids:
                    updates[tid] = start

    print(f"Matched persons: {matched_persons}")
    print(f"Tenures to update: {len(updates)}")

    # Phase 3: Batch update in DB
    BATCH_SIZE = 1000
    updated_count = 0
    with session_scope() as db:
        # Reload tenures by ID
        tenure_map = {}
        all_ids = list(updates.keys())
        for i in range(0, len(all_ids), BATCH_SIZE):
            batch_ids = all_ids[i:i+BATCH_SIZE]
            for t in db.scalars(select(RoleTenure).where(RoleTenure.id.in_(batch_ids))).all():
                tenure_map[t.id] = t

        for tid, start in updates.items():
            t = tenure_map.get(tid)
            if t and t.start_date is None:
                t.start_date = start
                updated_count += 1

        db.commit()

    update_elapsed = time.time() - start_time - fetch_elapsed

    # Final stats
    with session_scope() as db:
        missing_after = db.scalar(
            select(func.count(RoleTenure.id)).where(RoleTenure.start_date.is_(None))
        )
        has_after = db.scalar(
            select(func.count(RoleTenure.id)).where(RoleTenure.start_date.isnot(None))
        )

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print(f"  Companies processed: {processed}")
    print(f"  API responses with data: {len(results)}")
    print(f"  Failed tickers: {len(failed_tickers)}")
    print(f"  Persons matched: {matched_persons}")
    print(f"  Tenures updated: {updated_count}")
    print(f"  Missing before: {missing_before}")
    print(f"  Missing after: {missing_after}")
    print(f"  Has start_date: {has_after}")
    print(f"  Fetch time: {fetch_elapsed:.1f}s")
    print(f"  Update time: {update_elapsed:.1f}s")
    print(f"  Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")
    if failed_tickers:
        print(f"  Failed: {failed_tickers[:10]}")


if __name__ == "__main__":
    main()
