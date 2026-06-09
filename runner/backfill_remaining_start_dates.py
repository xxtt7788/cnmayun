"""
Backfill remaining RoleTenure start_date for SSE/SZSE companies only.
Uses loose name matching (case-insensitive, space-stripped) against EastMoney API.
BSE companies are skipped as EastMoney API does not cover them well.

Author: AI Assistant (Kimi)
Date: 2026-04-27
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


def normalize_name(name: str) -> str:
    """Strip spaces and lowercase for loose matching."""
    return (name or "").replace(" ", "").replace("\u3000", "").lower()


def main():
    with session_scope() as db:
        # Get SSE/SZSE companies with missing start_date tenures
        missing_rows = db.execute(text("""
            SELECT DISTINCT c.id as company_id, c.ticker
            FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            WHERE rt.start_date IS NULL
            AND c.exchange IN ('SSE', 'SZSE')
        """)).fetchall()

        company_ids = [r.company_id for r in missing_rows]
        company_tickers = {r.company_id: r.ticker for r in missing_rows}

        # Preload all persons
        persons = db.scalars(select(Person)).all()
        person_names = {p.id: (p.canonical_name or "").strip() for p in persons}
        person_norm = {p.id: normalize_name(p.canonical_name) for p in persons}

        # Preload missing tenure ids by (company_id, person_id)
        all_missing = db.execute(text("""
            SELECT rt.id, rt.company_id, rt.person_id
            FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            WHERE rt.start_date IS NULL AND c.exchange IN ('SSE', 'SZSE')
        """)).fetchall()
        tenure_ids_by_cp: dict[tuple[int, int], list[int]] = {}
        for r in all_missing:
            tenure_ids_by_cp.setdefault((r.company_id, r.person_id), []).append(r.id)

    print(f"SSE/SZSE companies with missing start_date: {len(company_ids)}")
    print(f"Missing tenures to fill: {len(all_missing)}")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 60)

    # Fetch API data
    results: dict[int, dict[str, date]] = {}
    processed = 0
    failed_tickers = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {}
        for cid in company_ids:
            ticker = company_tickers[cid]
            future_map[executor.submit(fetch_company_management, ticker)] = (cid, ticker)

        for future in as_completed(future_map):
            cid, ticker = future_map[future]
            processed += 1
            try:
                managers = future.result()
                name_to_date: dict[str, date] = {}
                for m in managers:
                    name = m.get("xm", "").strip()
                    start = parse_rzsj(m.get("rzsj", ""))
                    if name and start:
                        norm = normalize_name(name)
                        if norm not in name_to_date or start < name_to_date[norm]:
                            name_to_date[norm] = start
                if name_to_date:
                    results[cid] = name_to_date
            except Exception as e:
                failed_tickers.append(ticker)
                print(f"  ERROR {ticker}: {e}")

            if processed % 100 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Fetch progress: {processed}/{len(company_ids)} | success={len(results)} | {rate:.1f}/sec")

    fetch_elapsed = time.time() - start_time
    print(f"\nFetch complete: {len(results)} companies, {failed_tickers and len(failed_tickers) or 0} failed, {fetch_elapsed:.1f}s")

    # Build updates
    updates: dict[int, date] = {}
    matched = 0

    for cid, name_to_date in results.items():
        for pid, norm in person_norm.items():
            start = name_to_date.get(norm)
            if not start:
                continue
            key = (cid, pid)
            tids = tenure_ids_by_cp.get(key)
            if tids:
                matched += 1
                for tid in tids:
                    updates[tid] = start

    print(f"Matched persons: {matched}")
    print(f"Tenures to update: {len(updates)}")

    # Batch update
    BATCH_SIZE = 1000
    updated_count = 0
    with session_scope() as db:
        all_ids = list(updates.keys())
        tenure_objs = {}
        for i in range(0, len(all_ids), BATCH_SIZE):
            batch_ids = all_ids[i:i+BATCH_SIZE]
            for t in db.scalars(select(RoleTenure).where(RoleTenure.id.in_(batch_ids))).all():
                tenure_objs[t.id] = t

        for tid, start in updates.items():
            t = tenure_objs.get(tid)
            if t and t.start_date is None:
                t.start_date = start
                updated_count += 1

        db.commit()

    update_elapsed = time.time() - start_time - fetch_elapsed

    with session_scope() as db:
        remaining = db.execute(text("""
            SELECT COUNT(*) FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            WHERE rt.start_date IS NULL AND c.exchange IN ('SSE', 'SZSE')
        """)).fetchone()[0]
        total_missing = db.scalar(select(func.count(RoleTenure.id)).where(RoleTenure.start_date.is_(None)))

    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print(f"  SSE/SZSE tenures updated: {updated_count}")
    print(f"  SSE/SZSE remaining: {remaining}")
    print(f"  Total remaining (incl. BSE): {total_missing}")
    print(f"  Fetch time: {fetch_elapsed:.1f}s")
    print(f"  Update time: {update_elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
