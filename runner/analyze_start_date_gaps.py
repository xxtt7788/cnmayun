#!/usr/bin/env python3
"""
Analyze start_date gaps by exchange and company.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys

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
    with session_scope() as db:
        # Missing start_date by exchange
        result = db.execute(text("""
            SELECT c.exchange, COUNT(*) as cnt
            FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            WHERE rt.start_date IS NULL
            GROUP BY c.exchange
            ORDER BY cnt DESC
        """))
        print("=== Missing start_date by exchange ===")
        for row in result:
            print(f"  {row.exchange}: {row.cnt}")

        # Missing start_date by company (top 30)
        result2 = db.execute(text("""
            SELECT c.ticker, c.exchange, COUNT(*) as cnt
            FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            WHERE rt.start_date IS NULL
            GROUP BY c.id, c.ticker, c.exchange
            ORDER BY cnt DESC
            LIMIT 30
        """))
        print("\n=== Top 30 companies with missing start_date ===")
        for row in result2:
            print(f"  {row.ticker} ({row.exchange}): {row.cnt}")

        # Total
        total = db.execute(text("SELECT COUNT(*) FROM role_tenures WHERE start_date IS NULL")).scalar()
        print(f"\nTotal missing start_date: {total}")

        # Check if any of these tenures have is_active=False (might have end_date)
        inactive_missing = db.execute(text("""
            SELECT COUNT(*) FROM role_tenures 
            WHERE start_date IS NULL AND is_active = FALSE
        """)).scalar()
        print(f"Missing start_date AND inactive: {inactive_missing}")


if __name__ == "__main__":
    main()
