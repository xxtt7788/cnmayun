#!/usr/bin/env python3
"""
Analyze gaps between tenures and events.
Identifies tenure changes that should have corresponding events.

Author: Kimi Code CLI Agent | Date: 2026-04-28
"""

import os, sys

ENV_PATH = "/etc/china-succession/china-succession.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.startswith("export "): key = key[7:]
                os.environ[key] = value.strip().strip('"').strip("'")

sys.path.insert(0, "/opt/china-succession")
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)

with engine.connect() as conn:
    # Tenures with start_date but no corresponding appointment event
    start_without_event = conn.execute(text("""
        SELECT COUNT(*) FROM role_tenures t
        WHERE t.start_date IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM events e
              WHERE e.company_id = t.company_id
                AND e.person_id = t.person_id
                AND e.event_type = 'appointment'
                AND e.announcement_date = t.start_date
          )
    """)).scalar()

    # Tenures with end_date but no corresponding resignation event
    end_without_event = conn.execute(text("""
        SELECT COUNT(*) FROM role_tenures t
        WHERE t.end_date IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM events e
              WHERE e.company_id = t.company_id
                AND e.person_id = t.person_id
                AND e.event_type = 'resignation'
                AND e.announcement_date = t.end_date
          )
    """)).scalar()

    # Monthly event creation potential
    monthly = conn.execute(text("""
        SELECT DATE_TRUNC('month', start_date) as month, COUNT(*) as cnt
        FROM role_tenures
        WHERE start_date IS NOT NULL
          AND start_date >= '2023-01-01'
        GROUP BY DATE_TRUNC('month', start_date)
        ORDER BY month DESC
        LIMIT 12
    """)).fetchall()

    print("=== EVENT GAP ANALYSIS ===")
    print(f"Tenures with start_date but no appointment event: {start_without_event}")
    print(f"Tenures with end_date but no resignation event:   {end_without_event}")
    print(f"\nRecent monthly start_date distribution (potential events):")
    for row in monthly:
        print(f"  {row.month.strftime('%Y-%m')}: {row.cnt} tenure starts")

    # Check if source_documents exist for event creation
    doc_count = conn.execute(text("SELECT COUNT(*) FROM source_documents")).scalar()
    print(f"\nSource documents available: {doc_count}")
    print("\nNote: Creating events requires source_document_id (FK, NOT NULL).")
    print("Cannot auto-generate events without corresponding source documents.")
