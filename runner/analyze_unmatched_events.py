#!/usr/bin/env python3
"""
Analyze unmatched events to understand why effective date extraction failed.

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
        # Get unmatched events (no effective date pattern found)
        rows = db.execute(text("""
            SELECT e.id, e.event_type, e.announcement_date, sd.title, sd.raw_text
            FROM events e
            JOIN source_documents sd ON e.source_document_id = sd.id
            WHERE sd.raw_text IS NOT NULL AND LENGTH(sd.raw_text) > 50
            AND e.effective_date = e.announcement_date
            ORDER BY e.id
            LIMIT 50
        """)).fetchall()

        print(f"Unmatched events sample (total ~1337): {len(rows)}\n")

        # Count by event type
        type_counts = db.execute(text("""
            SELECT e.event_type, COUNT(*)
            FROM events e
            JOIN source_documents sd ON e.source_document_id = sd.id
            WHERE sd.raw_text IS NOT NULL AND LENGTH(sd.raw_text) > 50
            AND e.effective_date = e.announcement_date
            GROUP BY e.event_type
            ORDER BY COUNT(*) DESC
        """)).fetchall()

        print("=== Unmatched by event type ===")
        for etype, cnt in type_counts:
            print(f"  {etype}: {cnt}")

        # Show samples
        print("\n=== Sample unmatched events ===")
        for eid, etype, ann_date, title, raw_text in rows[:10]:
            snippet = (raw_text or "")[:200].replace("\n", " ")
            print(f"\n  ID={eid}, type={etype}, date={ann_date}")
            print(f"  Title: {title}")
            print(f"  Text snippet: {snippet}")


if __name__ == "__main__":
    main()
