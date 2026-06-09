#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate inferred events from tenure start/end dates.

Creates placeholder source_documents and appointment/resignation events
for tenures lacking corresponding event records.

Limits scope to avoid overwhelming the system:
- All tenures with end_date (resignation events)
- Most recent 5000 tenures with start_date (appointment events)

Author: Kimi Code CLI Agent | Date: 2026-04-28
"""

import os
import sys
import logging

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


def main():
    from sqlalchemy import create_engine, text
    from app.config import settings

    engine = create_engine(settings.database_url)

    # Phase 1: Resignation events (end_date)
    logger.info("Phase 1: Finding tenures with end_date but no resignation event...")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT t.id, t.company_id, t.person_id, t.role_canonical as role, t.end_date
            FROM role_tenures t
            WHERE t.end_date IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM events e
                  WHERE e.company_id = t.company_id
                    AND e.person_id = t.person_id
                    AND e.event_type = 'resignation'
                    AND e.effective_date = t.end_date
              )
            ORDER BY t.end_date DESC
        """)).fetchall()

    logger.info(f"Found {len(rows)} tenures needing resignation events")
    resignation_count = 0

    with engine.begin() as conn:
        for row in rows:
            # Create placeholder source_document
            doc_result = conn.execute(
                text("""
                INSERT INTO source_documents (company_id, source_type, source_platform, title, source_url, created_at, updated_at)
                VALUES (:company_id, 'inferred', 'system', 'Inferred from tenure end date', '', NOW(), NOW())
                RETURNING id
                """),
                {"company_id": row.company_id}
            )
            doc_id = doc_result.scalar()

            # Create event
            conn.execute(
                text("""
                INSERT INTO events (company_id, person_id, source_document_id, role_raw, role_canonical, event_type,
                    event_status, effective_date, excerpt, confidence, is_inferred, created_at, updated_at)
                VALUES (:company_id, :person_id, :doc_id, :role_raw, :role_canonical, 'resignation', 'published',
                    :end_date, 'Inferred resignation from tenure end_date', 0.5, true, NOW(), NOW())
                ON CONFLICT DO NOTHING
                """),
                {
                    "company_id": row.company_id,
                    "person_id": row.person_id,
                    "doc_id": doc_id,
                    "role_raw": row.role or "unknown",
                    "role_canonical": row.role or "unknown",
                    "end_date": row.end_date,
                }
            )
            resignation_count += 1

    logger.info(f"Created {resignation_count} resignation events")

    # Phase 2: Appointment events (start_date) - limit to 5000 most recent
    logger.info("Phase 2: Finding recent tenures with start_date but no appointment event...")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT t.id, t.company_id, t.person_id, t.role_canonical as role, t.start_date
            FROM role_tenures t
            WHERE t.start_date IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM events e
                  WHERE e.company_id = t.company_id
                    AND e.person_id = t.person_id
                    AND e.event_type = 'appointment'
                    AND e.effective_date = t.start_date
              )
            ORDER BY t.start_date DESC
            LIMIT 5000
        """)).fetchall()

    logger.info(f"Found {len(rows)} tenures needing appointment events (capped at 5000)")
    appointment_count = 0

    with engine.begin() as conn:
        for row in rows:
            doc_result = conn.execute(
                text("""
                INSERT INTO source_documents (company_id, source_type, source_platform, title, source_url, created_at, updated_at)
                VALUES (:company_id, 'inferred', 'system', 'Inferred from tenure start date', '', NOW(), NOW())
                RETURNING id
                """),
                {"company_id": row.company_id}
            )
            doc_id = doc_result.scalar()

            conn.execute(
                text("""
                INSERT INTO events (company_id, person_id, source_document_id, role_raw, role_canonical, event_type,
                    event_status, effective_date, excerpt, confidence, is_inferred, created_at, updated_at)
                VALUES (:company_id, :person_id, :doc_id, :role_raw, :role_canonical, 'appointment', 'published',
                    :start_date, 'Inferred appointment from tenure start_date', 0.5, true, NOW(), NOW())
                ON CONFLICT DO NOTHING
                """),
                {
                    "company_id": row.company_id,
                    "person_id": row.person_id,
                    "doc_id": doc_id,
                    "role_raw": row.role or "unknown",
                    "role_canonical": row.role or "unknown",
                    "start_date": row.start_date,
                }
            )
            appointment_count += 1

    logger.info(f"Created {appointment_count} appointment events")

    # Summary
    with engine.connect() as conn:
        total_events = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
        inferred_events = conn.execute(text("SELECT COUNT(*) FROM events WHERE is_inferred = true")).scalar()
        total_docs = conn.execute(text("SELECT COUNT(*) FROM source_documents")).scalar()
        inferred_docs = conn.execute(text("SELECT COUNT(*) FROM source_documents WHERE source_type = 'inferred'")).scalar()

    logger.info("=" * 50)
    logger.info("INFERRED EVENTS GENERATION SUMMARY")
    logger.info(f"  Total events:      {total_events}")
    logger.info(f"  Inferred events:   {inferred_events}")
    logger.info(f"  Total source docs: {total_docs}")
    logger.info(f"  Inferred docs:     {inferred_docs}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
