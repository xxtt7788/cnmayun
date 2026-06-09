#!/usr/bin/env python3
"""
Analyze events table to infer start_date for tenures.

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
        # Event types distribution
        print("=== Event types ===")
        result = db.execute(text("SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY COUNT(*) DESC"))
        for row in result:
            print(f"  {row.event_type}: {row[1]}")

        # Events with person_id
        print("\n=== Events with person_id ===")
        result = db.execute(text("SELECT COUNT(*) FROM events WHERE person_id IS NOT NULL"))
        print(f"  Count: {result.scalar()}")

        # Missing start_date tenures that have matching events
        print("\n=== Tenures with potential event matches ===")
        rows = db.execute(text("""
            SELECT rt.id, rt.company_id, rt.person_id, e.event_type, e.effective_date, e.announcement_date
            FROM role_tenures rt
            JOIN events e ON rt.company_id = e.company_id AND rt.person_id = e.person_id
            WHERE rt.start_date IS NULL
            ORDER BY rt.id, e.effective_date
            LIMIT 20
        """)).fetchall()
        print(f"Found {len(rows)} matches")
        for row in rows:
            print(f"  tenure={row.id}, company={row.company_id}, person={row.person_id}, type={row.event_type}, effective={row.effective_date}, announced={row.announcement_date}")

        # Count unique tenures that could be filled
        result = db.execute(text("""
            SELECT COUNT(DISTINCT rt.id)
            FROM role_tenures rt
            JOIN events e ON rt.company_id = e.company_id AND rt.person_id = e.person_id
            WHERE rt.start_date IS NULL
        """))
        print(f"\nUnique tenures with event match: {result.scalar()}")


if __name__ == "__main__":
    main()
