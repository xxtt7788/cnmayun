"""
Analyze the 6,692 RoleTenure records missing start_date.
Find distribution by company, exchange, and person name patterns.

Author: AI Assistant (Kimi)
Date: 2026-04-27
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/opt/china-succession')

from app.db import session_scope
from sqlalchemy import text


def main():
    with session_scope() as db:
        # Count missing by exchange
        rows = db.execute(text("""
            SELECT c.exchange, COUNT(*) as cnt
            FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            WHERE rt.start_date IS NULL
            GROUP BY c.exchange ORDER BY cnt DESC
        """)).fetchall()
        print("Missing start_date by exchange:")
        for r in rows:
            print(f"  {r.exchange}: {r.cnt}")

        # Count missing by company (top 20)
        rows = db.execute(text("""
            SELECT c.ticker, c.short_name, COUNT(*) as cnt
            FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            WHERE rt.start_date IS NULL
            GROUP BY c.id, c.ticker, c.short_name
            ORDER BY cnt DESC LIMIT 20
        """)).fetchall()
        print("\nTop 20 companies with missing start_date:")
        for r in rows:
            print(f"  {r.ticker} {r.short_name}: {r.cnt}")

        # Sample some missing tenures with person names
        rows = db.execute(text("""
            SELECT c.ticker, p.canonical_name, rt.role_canonical
            FROM role_tenures rt
            JOIN companies c ON rt.company_id = c.id
            JOIN persons p ON rt.person_id = p.id
            WHERE rt.start_date IS NULL
            LIMIT 30
        """)).fetchall()
        print("\nSample missing tenures:")
        for r in rows:
            print(f"  {r.ticker} | {r.canonical_name} | {r.role_canonical}")

        # Count how many of these persons appear in multiple companies
        multi = db.execute(text("""
            SELECT COUNT(*) as cnt FROM (
                SELECT rt.person_id, COUNT(DISTINCT rt.company_id) as cc
                FROM role_tenures rt
                WHERE rt.start_date IS NULL AND rt.person_id IS NOT NULL
                GROUP BY rt.person_id HAVING COUNT(DISTINCT rt.company_id) > 1
            ) t
        """)).fetchone()
        print(f"\nPersons with missing start_date in multiple companies: {multi.cnt}")


if __name__ == "__main__":
    main()
