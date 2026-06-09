#!/usr/bin/env python3
"""
Analyze source_documents that don't have associated events.

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
        print("=== Review Queue Status ===")
        pending = db.execute(text("SELECT COUNT(*) FROM review_queue WHERE status='pending'")).scalar()
        approved = db.execute(text("SELECT COUNT(*) FROM review_queue WHERE status='approved'")).scalar()
        print(f"  Pending: {pending}")
        print(f"  Approved: {approved}")

        print("\n=== Document Processing Runs ===")
        statuses = db.execute(text("""
            SELECT status, COUNT(*) 
            FROM document_processing_runs 
            GROUP BY status 
            ORDER BY COUNT(*) DESC
        """)).fetchall()
        for status, cnt in statuses:
            print(f"  {status}: {cnt}")

        print("\n=== Orphan docs by month (2025+) ===")
        orphans = db.execute(text("""
            SELECT 
                DATE_TRUNC('month', sd.announcement_date) as month,
                COUNT(*) as cnt
            FROM source_documents sd
            WHERE sd.announcement_date >= '2025-01-01'
            AND NOT EXISTS (SELECT 1 FROM events e WHERE e.source_document_id = sd.id)
            GROUP BY DATE_TRUNC('month', sd.announcement_date)
            ORDER BY month
        """)).fetchall()
        for row in orphans:
            print(f"  {row.month.strftime('%Y-%m')}: {row.cnt}")

        print("\n=== Orphan doc titles (sample) ===")
        titles = db.execute(text("""
            SELECT sd.title, sd.announcement_date
            FROM source_documents sd
            WHERE sd.announcement_date >= '2025-01-01'
            AND NOT EXISTS (SELECT 1 FROM events e WHERE e.source_document_id = sd.id)
            ORDER BY sd.announcement_date DESC
            LIMIT 30
        """)).fetchall()
        for title, ann_date in titles:
            print(f"  {ann_date}: {title}")

        print("\n=== Docs with processing runs but no events ===")
        processed_no_event = db.execute(text("""
            SELECT dpr.status, COUNT(*)
            FROM document_processing_runs dpr
            JOIN source_documents sd ON dpr.source_document_id = sd.id
            WHERE sd.announcement_date >= '2025-01-01'
            AND NOT EXISTS (SELECT 1 FROM events e WHERE e.source_document_id = sd.id)
            GROUP BY dpr.status
            ORDER BY COUNT(*) DESC
        """)).fetchall()
        for status, cnt in processed_no_event:
            print(f"  {status}: {cnt}")


if __name__ == "__main__":
    main()
