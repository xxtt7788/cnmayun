#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill missing compensation from EastMoney for executive_snapshots.

Re-fetches CompanyManagementAjax for companies with NULL compensation snapshots.

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


def build_em_code(ticker):
    t = str(ticker).strip()
    if t.startswith('6'):
        return f"SH{t}"
    elif t[0] in '03':
        return f"SZ{t}"
    elif t[0] in '489':
        return f"BJ{t}"
    return None


def parse_compensation(val):
    if val is None or val == '--' or val == '-':
        return None
    s = str(val).strip()
    m = re.match(r'^([\d.]+)\s*(万|亿)?$', s)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit == '亿':
        return round(num * 10000, 2)
    elif unit == '万':
        return round(num, 2)
    else:
        if num > 1000:
            return round(num, 2)
        return round(num, 2)


def fetch_compensation(em_code):
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax?code={em_code}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        data = r.json()
        mgmt = data.get("RptManagerList", [])
        return {m.get("xm", "").strip(): parse_compensation(m.get("xc")) for m in mgmt if m.get("xm")}
    except Exception:
        return {}


def main():
    from sqlalchemy import create_engine, text
    from app.config import settings

    engine = create_engine(settings.database_url)

    # Find snapshots missing compensation
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT s.id, c.ticker, s.person_name_raw as person_name
            FROM executive_snapshots s
            JOIN companies c ON s.company_id = c.id
            WHERE s.compensation IS NULL AND c.is_active = true
              AND c.ticker !~ '^[489]'
            ORDER BY c.ticker
        """)).fetchall()

    logger.info(f"Found {len(rows)} snapshots missing compensation")

    # Group by ticker
    ticker_to_snapshots = {}
    for row in rows:
        ticker_to_snapshots.setdefault(row.ticker, []).append({"id": row.id, "person_name": row.person_name})

    logger.info(f"Unique tickers to fetch: {len(ticker_to_snapshots)}")

    # Fetch compensation data
    ticker_to_comp = {}
    valid = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {}
        for ticker in ticker_to_snapshots:
            em_code = build_em_code(ticker)
            if em_code:
                future_to_ticker[executor.submit(fetch_compensation, em_code)] = ticker

        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                comp = future.result()
                if comp:
                    ticker_to_comp[ticker] = comp
                    valid += 1
            except Exception as e:
                logger.warning(f"Error fetching {ticker}: {e}")

    logger.info(f"Got compensation data for {valid}/{len(ticker_to_snapshots)} tickers")

    # Build updates
    updates = []
    matched = 0
    for ticker, snapshots in ticker_to_snapshots.items():
        comp_map = ticker_to_comp.get(ticker)
        if not comp_map:
            continue
        for snap in snapshots:
            comp = comp_map.get(snap["person_name"])
            if comp is not None:
                updates.append({"id": snap["id"], "comp": comp})
                matched += 1

    logger.info(f"Matched {matched}/{len(rows)} snapshots with compensation")

    if not updates:
        logger.info("No updates to apply.")
        return

    # Update database
    logger.info(f"Updating {len(updates)} snapshots...")
    with engine.begin() as conn:
        for u in updates:
            conn.execute(
                text("UPDATE executive_snapshots SET compensation = :comp WHERE id = :id"),
                u
            )

    logger.info("Done.")

    # Summary
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM executive_snapshots")).scalar()
        has_comp = conn.execute(text("SELECT COUNT(*) FROM executive_snapshots WHERE compensation IS NOT NULL")).scalar()
    logger.info(f"Compensation coverage: {has_comp}/{total} ({has_comp/total*100:.1f}%)")


if __name__ == "__main__":
    main()
