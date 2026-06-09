#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round 3.1, 4.2, 4.3, 5: SQL-only backfills

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


def r31_person_shareholdings():
    logger.info("START R3.1: Person Shareholdings (match by name)")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO person_shareholdings (person_id, company_id, share_count, share_ratio, report_date)
            SELECT
                p.id AS person_id,
                cs.company_id,
                cs.share_count,
                cs.share_ratio,
                cs.report_date
            FROM company_shareholders cs
            JOIN persons p ON cs.shareholder_name = p.canonical_name
            WHERE NOT EXISTS (
                SELECT 1 FROM person_shareholdings ps
                WHERE ps.person_id = p.id AND ps.company_id = cs.company_id
            )
        """))
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM person_shareholdings")).scalar()
    logger.info(f"R3.1 DONE: person_shareholdings count={count}")


def r42_industry_median():
    logger.info("START R4.2: Industry Median Financials")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE OR REPLACE VIEW industry_median AS
            SELECT
                industry_l2,
                report_period,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue) AS revenue_median,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY net_profit) AS net_profit_median,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY roe) AS roe_median,
                COUNT(*) AS company_count
            FROM company_financials
            WHERE industry_l2 IS NOT NULL
            GROUP BY industry_l2, report_period
        """))
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM industry_median")).scalar()
    logger.info(f"R4.2 DONE: industry_median rows={count}")


def r43_mark_inferred_docs():
    logger.info("START R4.3: Mark Inferred Source Documents")
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE source_documents
            SET source_type = 'inferred'
            WHERE source_type IS NULL
            AND id IN (
                SELECT sd.id FROM source_documents sd
                LEFT JOIN events e ON e.source_document_id = sd.id
                WHERE e.is_inferred = TRUE
            )
        """))
    logger.info(f"R4.3 DONE: marked {result.rowcount} inferred docs")


def r51_post_risk_flag():
    logger.info("START R5.1: Post-Risk Event Flagging")
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE events
            SET post_risk_flag = TRUE
            WHERE post_risk_flag = FALSE
            AND EXISTS (
                SELECT 1 FROM company_risks cr
                WHERE cr.company_id = events.company_id
                AND cr.event_date <= events.effective_date
                AND cr.event_date >= events.effective_date - INTERVAL '90 days'
            )
        """))
    logger.info(f"R5.1 DONE: flagged {result.rowcount} events")


def r52_post_decline_flag():
    logger.info("START R5.2: Post-Decline Event Flagging")
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE events
            SET post_decline_flag = TRUE
            WHERE post_decline_flag = FALSE
            AND EXISTS (
                SELECT 1 FROM company_financials cf1
                JOIN company_financials cf2 ON cf1.company_id = cf2.company_id
                    AND cf2.report_period = (
                        SELECT MAX(report_period) FROM company_financials
                        WHERE company_id = cf1.company_id AND report_period < cf1.report_period
                    )
                WHERE cf1.company_id = events.company_id
                AND cf1.revenue_yoy < -20
                AND cf1.net_profit_yoy < -20
                AND cf1.report_period = (
                    SELECT MAX(report_period) FROM company_financials
                    WHERE company_id = events.company_id AND report_period <= TO_CHAR(events.effective_date, 'YYYYMMDD')
                )
            )
        """))
    logger.info(f"R5.2 DONE: flagged {result.rowcount} events")


def r53_transfer_score_update():
    logger.info("START R5.3: Transfer Frequency Score Update")
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE persons p
            SET transfer_frequency_score = COALESCE(sub.cnt, 0)
            FROM (
                SELECT person_id, COUNT(*) AS cnt
                FROM person_transfers
                GROUP BY person_id
            ) sub
            WHERE p.id = sub.person_id
        """))
    with engine.connect() as conn:
        avg_score = conn.execute(text("SELECT AVG(transfer_frequency_score) FROM persons WHERE transfer_frequency_score > 0")).scalar()
    logger.info(f"R5.3 DONE: avg transfer_frequency_score={avg_score}")


def main():
    r31_person_shareholdings()
    r42_industry_median()
    r43_mark_inferred_docs()
    r51_post_risk_flag()
    r52_post_decline_flag()
    r53_transfer_score_update()
    logger.info("=" * 60)
    logger.info("ROUND 3.1 + 4.2 + 4.3 + 5 COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
