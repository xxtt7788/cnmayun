#!/usr/bin/env python3
"""
Backfill start_date from events table for matched tenures.

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
        # Find tenures with event matches
        rows = db.execute(text("""
            SELECT rt.id, e.effective_date, e.announcement_date, e.event_type
            FROM role_tenures rt
            JOIN events e ON rt.company_id = e.company_id AND rt.person_id = e.person_id
            WHERE rt.start_date IS NULL
            ORDER BY rt.id, e.effective_date
        """)).fetchall()

        updates = {}
        for tid, effective, announced, event_type in rows:
            if tid in updates:
                continue
            date_to_use = effective or announced
            if date_to_use:
                updates[tid] = (date_to_use, event_type)

        print(f"Tenures to update from events: {len(updates)}")

        updated = 0
        for tid, (date_val, event_type) in updates.items():
            result = db.execute(
                text("UPDATE role_tenures SET start_date = :date WHERE id = :id AND start_date IS NULL"),
                {"date": date_val, "id": tid}
            )
            if result.rowcount > 0:
                updated += 1
                print(f"  Updated tenure {tid} with {date_val} (from {event_type})")

        db.commit()
        print(f"\nTotal updated: {updated}")


if __name__ == "__main__":
    main()
