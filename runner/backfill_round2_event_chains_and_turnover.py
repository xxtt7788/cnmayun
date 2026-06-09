#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round 2.2 + R2.3: 前任继任链 + 高管变动率指标

Author: Kimi Code CLI Agent
Date: 2026-04-25
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)


def r22_event_chains():
    logger.info("START R2.2: Event Chains (predecessor-successor)")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO event_chains (company_id, role, event_out_id, event_in_id, gap_days)
            SELECT DISTINCT ON (e1.company_id, e1.role_canonical, e1.id)
                e1.company_id,
                e1.role_canonical,
                e1.id AS event_out_id,
                e2.id AS event_in_id,
                (e2.effective_date - e1.effective_date)::int AS gap_days
            FROM events e1
            JOIN events e2 ON e1.company_id = e2.company_id
                AND e1.role_canonical = e2.role_canonical
                AND e1.event_type = 'resignation'
                AND e2.event_type = 'appointment'
                AND e2.effective_date >= e1.effective_date
                AND e2.effective_date <= e1.effective_date + INTERVAL '180 days'
            WHERE NOT EXISTS (
                SELECT 1 FROM event_chains ec
                WHERE ec.company_id = e1.company_id
                AND ec.role = e1.role_canonical
                AND ec.event_out_id = e1.id
            )
            ORDER BY e1.company_id, e1.role_canonical, e1.id, e2.effective_date, e2.id
        """))

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM event_chains")).scalar()
    logger.info(f"R2.2 DONE: event_chains count={count}")


def r23_turnover_rate():
    logger.info("START R2.3: Executive Turnover Rate Metrics")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW company_turnover_rate AS
            SELECT
                company_id,
                DATE_TRUNC('year', effective_date)::date AS year,
                COUNT(*) FILTER (WHERE event_type = 'resignation') AS resignations,
                COUNT(*) FILTER (WHERE event_type = 'appointment') AS appointments,
                COUNT(DISTINCT person_id) AS distinct_persons
            FROM events
            WHERE effective_date IS NOT NULL
            GROUP BY company_id, DATE_TRUNC('year', effective_date)
        """))

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM company_turnover_rate")).scalar()
    logger.info(f"R2.3 DONE: company_turnover_rate rows={count}")


def main():
    r22_event_chains()
    r23_turnover_rate()
    logger.info("=" * 60)
    logger.info("ROUND 2.2 + 2.3 COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
