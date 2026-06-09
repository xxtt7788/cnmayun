#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round 3.2: 人物跨公司流动路径

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


def r32_person_transfers():
    logger.info("START R3.2: Person Transfers")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO person_transfers
            (person_id, from_company_id, from_role, from_start_date, to_company_id, to_role, to_start_date, transfer_days)
            SELECT DISTINCT ON (rt1.person_id, rt1.company_id, rt2.company_id)
                rt1.person_id,
                rt1.company_id AS from_company_id,
                rt1.role_canonical AS from_role,
                rt1.start_date AS from_start_date,
                rt2.company_id AS to_company_id,
                rt2.role_canonical AS to_role,
                rt2.start_date AS to_start_date,
                (rt2.start_date - COALESCE(rt1.end_date, rt1.start_date))::int AS transfer_days
            FROM role_tenures rt1
            JOIN role_tenures rt2 ON rt1.person_id = rt2.person_id
                AND rt1.company_id != rt2.company_id
                AND rt2.start_date >= COALESCE(rt1.end_date, rt1.start_date, '1900-01-01')
            WHERE NOT EXISTS (
                SELECT 1 FROM person_transfers pt
                WHERE pt.person_id = rt1.person_id
                AND pt.from_company_id = rt1.company_id
                AND pt.to_company_id = rt2.company_id
            )
            ORDER BY rt1.person_id, rt1.company_id, rt2.company_id, rt2.start_date
        """))

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM person_transfers")).scalar()
    logger.info(f"R3.2 DONE: person_transfers count={count}")


def r34_transfer_frequency():
    logger.info("START R3.4 (bonus): Transfer Frequency Score")
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE persons p
            SET transfer_frequency_score = sub.cnt
            FROM (
                SELECT person_id, COUNT(*) AS cnt
                FROM person_transfers
                GROUP BY person_id
            ) sub
            WHERE p.id = sub.person_id
        """))

    with engine.connect() as conn:
        avg_score = conn.execute(text("SELECT AVG(transfer_frequency_score) FROM persons WHERE transfer_frequency_score > 0")).scalar()
    logger.info(f"R3.4 DONE: avg transfer_frequency_score={avg_score}")


def main():
    r32_person_transfers()
    r34_transfer_frequency()
    logger.info("=" * 60)
    logger.info("ROUND 3.2 COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
