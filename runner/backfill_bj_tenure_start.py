#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill BJ stock tenure start_dates from EastMoney CompanyManagementAjax.

Uses BJ prefix for EastMoney API. Only processes BJ tickers that return data.

Author: Kimi Code CLI Agent | Date: 2026-04-28
"""

import os
import sys
import re
import requests
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

ENV_PATH = "/etc/china-succession/china-succession.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.startswith("export "):
                    key = key[7:]
                os.environ[key] = value.strip().strip('"').strip("'")

sys.path.insert(0, "/opt/china-succession")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://emweb.securities.eastmoney.com/",
}


def parse_rzsj(rzsj):
    """Parse rzsj field to YYYY-MM-DD."""
    if not rzsj:
        return None
    s = str(rzsj).strip()
    m = re.search(r'(\d{4})[\-/年](\d{1,2})[\-/月](\d{1,2})', s)
    if m:
        y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1900 <= y <= 2030 and 1 <= mth <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mth:02d}-{d:02d}"
    return None


def fetch_company_management(ticker):
    """Fetch management data from EastMoney for BJ stock."""
    em_code = f"BJ{ticker}"
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax?code={em_code}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        data = r.json()
        mgmt = data.get("RptManagerList", [])
        return {m.get("xm", "").strip(): parse_rzsj(m.get("rzsj")) for m in mgmt if m.get("xm")}
    except Exception as e:
        return {}


def main():
    from sqlalchemy import create_engine, text
    from app.config import settings

    engine = create_engine(settings.database_url)

    # Load BJ tenures missing start_date
    logger.info("Loading BJ tenures missing start_date...")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT t.id, c.ticker, c.company_name, p.canonical_name as person_name
            FROM role_tenures t
            JOIN companies c ON t.company_id = c.id
            JOIN persons p ON t.person_id = p.id
            WHERE c.is_active = true AND c.ticker ~ '^[489]'
              AND t.start_date IS NULL
            ORDER BY c.ticker
        """)).fetchall()

    logger.info(f"Found {len(rows)} BJ tenures missing start_date")

    # Group by ticker for efficient fetching
    tickers_needed = sorted(set(r.ticker for r in rows))
    logger.info(f"Unique BJ tickers to fetch: {len(tickers_needed)}")

    # Phase 1: Fetch management data
    logger.info("Fetching management data from EastMoney...")
    ticker_to_mgmt = {}
    valid_tickers = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {
            executor.submit(fetch_company_management, ticker): ticker
            for ticker in tickers_needed
        }
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                mgmt = future.result()
                if mgmt:
                    ticker_to_mgmt[ticker] = mgmt
                    valid_tickers += 1
            except Exception as e:
                logger.warning(f"Error fetching {ticker}: {e}")

    logger.info(f"EastMoney returned data for {valid_tickers}/{len(tickers_needed)} BJ tickers")

    # Phase 2: Build updates
    updates = {}
    matched = 0
    unmatched = 0

    for row in rows:
        mgmt = ticker_to_mgmt.get(row.ticker)
        if not mgmt:
            unmatched += 1
            continue
        start_date = mgmt.get(row.person_name)
        if start_date:
            updates[row.id] = start_date
            matched += 1
        else:
            unmatched += 1

    logger.info(f"Matched {matched}/{len(rows)} tenures to person names")
    logger.info(f"Unmatched: {unmatched}")

    if not updates:
        logger.info("No updates to apply.")
        return

    # Phase 3: Update database
    logger.info(f"Updating {len(updates)} tenures...")
    with engine.begin() as conn:
        for tid, sd in updates.items():
            conn.execute(
                text("UPDATE role_tenures SET start_date = :sd WHERE id = :id"),
                {"id": tid, "sd": sd}
            )
    logger.info("Done.")

    # Summary
    with engine.connect() as conn:
        bj_total = conn.execute(text("""
            SELECT COUNT(*) FROM role_tenures t
            JOIN companies c ON t.company_id = c.id
            WHERE c.is_active = true AND c.ticker ~ '^[489]'
        """)).scalar()
        bj_has_start = conn.execute(text("""
            SELECT COUNT(*) FROM role_tenures t
            JOIN companies c ON t.company_id = c.id
            WHERE c.is_active = true AND c.ticker ~ '^[489]' AND t.start_date IS NOT NULL
        """)).scalar()

    logger.info("=" * 50)
    logger.info("BJ TENURE START_DATE SUMMARY")
    logger.info(f"  Total BJ tenures:  {bj_total}")
    logger.info(f"  With start_date:   {bj_has_start} ({bj_has_start/bj_total*100:.1f}%)")
    logger.info(f"  Missing:           {bj_total - bj_has_start}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
