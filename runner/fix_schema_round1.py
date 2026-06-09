#!/usr/bin/env python3
"""
Fix Round 1 Schema: idempotent DDL execution with per-statement transactions.
Author: Kimi Code CLI Agent
Date: 2026-04-25
"""
import os
import sys

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

from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)

STATEMENTS = [
    # companies
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS market_cap NUMERIC(20,2)",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS registered_capital NUMERIC(20,2)",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS employee_count INTEGER",

    # company_shareholders
    """CREATE TABLE IF NOT EXISTS company_shareholders (
        id SERIAL PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id),
        shareholder_name VARCHAR(255),
        shareholder_type VARCHAR(50),
        share_count BIGINT,
        share_ratio NUMERIC(10,4),
        change_direction VARCHAR(20),
        report_date DATE,
        UNIQUE(company_id, shareholder_name, report_date)
    )""",

    # company_stock_prices
    """CREATE TABLE IF NOT EXISTS company_stock_prices (
        id BIGSERIAL PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id),
        trade_date DATE,
        open NUMERIC(15,4),
        high NUMERIC(15,4),
        low NUMERIC(15,4),
        close NUMERIC(15,4),
        volume BIGINT,
        amount NUMERIC(20,4),
        UNIQUE(company_id, trade_date)
    )""",

    # event_chains
    """CREATE TABLE IF NOT EXISTS event_chains (
        id SERIAL PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id),
        role VARCHAR(100),
        event_out_id INTEGER REFERENCES events(id),
        event_in_id INTEGER REFERENCES events(id),
        gap_days INTEGER,
        UNIQUE(company_id, role, event_out_id)
    )""",

    # person_shareholdings
    """CREATE TABLE IF NOT EXISTS person_shareholdings (
        id SERIAL PRIMARY KEY,
        person_id INTEGER REFERENCES persons(id),
        company_id INTEGER REFERENCES companies(id),
        share_count BIGINT,
        share_ratio NUMERIC(10,4),
        report_date DATE,
        UNIQUE(person_id, company_id, report_date)
    )""",

    # person_transfers
    """CREATE TABLE IF NOT EXISTS person_transfers (
        id SERIAL PRIMARY KEY,
        person_id INTEGER REFERENCES persons(id),
        from_company_id INTEGER REFERENCES companies(id),
        from_role VARCHAR(100),
        from_start_date DATE,
        to_company_id INTEGER REFERENCES companies(id),
        to_role VARCHAR(100),
        to_start_date DATE,
        transfer_days INTEGER
    )""",

    # company_risks
    """CREATE TABLE IF NOT EXISTS company_risks (
        id SERIAL PRIMARY KEY,
        company_id INTEGER REFERENCES companies(id),
        risk_type VARCHAR(50),
        source VARCHAR(100),
        event_date DATE,
        description TEXT,
        UNIQUE(company_id, event_date, risk_type)
    )""",

    # events
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS reason_category VARCHAR(50)",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS post_risk_flag BOOLEAN DEFAULT FALSE",
    "ALTER TABLE events ADD COLUMN IF NOT EXISTS post_decline_flag BOOLEAN DEFAULT FALSE",

    # persons
    "ALTER TABLE persons ADD COLUMN IF NOT EXISTS transfer_frequency_score INTEGER DEFAULT 0",
]

def main():
    for stmt in STATEMENTS:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
            print(f"OK: {stmt[:60]}...")
        except Exception as e:
            print(f"ERR: {stmt[:60]}... -> {e}")
    print("Schema fix complete.")

if __name__ == "__main__":
    main()
