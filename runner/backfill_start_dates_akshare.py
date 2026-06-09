#!/usr/bin/env python3
"""
Backfill start_date using akshare stock_manager interface.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys
import time

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
from sqlalchemy import text


def main():
    try:
        import akshare as ak
    except ImportError:
        print("akshare not installed")
        return

    with session_scope() as db:
        # Get missing start_date tenures with person names
        rows = db.execute(text("""
            SELECT rt.id, c.ticker, p.canonical_name
            FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            JOIN persons p ON rt.person_id = p.id
            WHERE rt.start_date IS NULL
            ORDER BY c.ticker
            LIMIT 200
        """)).fetchall()

    print(f"Testing akshare on {len(rows)} tenures...")

    updated = 0
    tested = 0
    found_data = 0

    for tid, ticker, name in rows:
        tested += 1
        try:
            # Try akshare stock_manager_change
            df = ak.stock_manager_change_detail(symbol=ticker)
            if df is not None and not df.empty:
                found_data += 1
                # Look for this person's name
                print(f"  {ticker}: got {len(df)} rows from akshare")
                print(f"    columns: {list(df.columns)}")
                print(f"    sample: {df.head(2).to_dict()}")
                if tested >= 5:
                    break
        except Exception as e:
            print(f"  {ticker}: {e}")
            if tested >= 10:
                break
        time.sleep(0.5)

    print(f"\nTested: {tested}, found data: {found_data}")


if __name__ == "__main__":
    main()
