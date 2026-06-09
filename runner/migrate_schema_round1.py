#!/usr/bin/env python3
"""
Round 1 Schema Migration: 公司背景相关表与字段
Author: Kimi Code CLI Agent
Date: 2026-04-25
"""
import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://china_succession:ImyMBqKOL504xZLRu1InNpKcr8l3@127.0.0.1:5432/china_succession")
engine = create_engine(DATABASE_URL)

SQL = """
-- companies 扩展字段（第一轮用）
ALTER TABLE companies ADD COLUMN IF NOT EXISTS market_cap NUMERIC(20,2);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS registered_capital NUMERIC(20,2);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS employee_count INTEGER;

-- company_shareholders
CREATE TABLE IF NOT EXISTS company_shareholders (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    shareholder_name VARCHAR(255),
    shareholder_type VARCHAR(50),
    share_count BIGINT,
    share_ratio NUMERIC(10,4),
    change_direction VARCHAR(20),
    report_date DATE,
    UNIQUE(company_id, shareholder_name, report_date)
);

-- company_stock_prices
CREATE TABLE IF NOT EXISTS company_stock_prices (
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
);

-- 预留表（后续轮次使用，先创建避免重复迁移）
CREATE TABLE IF NOT EXISTS event_chains (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    role VARCHAR(100),
    event_out_id INTEGER REFERENCES events(id),
    event_in_id INTEGER REFERENCES events(id),
    gap_days INTEGER,
    UNIQUE(company_id, role, event_out_id)
);

CREATE TABLE IF NOT EXISTS person_shareholdings (
    id SERIAL PRIMARY KEY,
    person_id INTEGER REFERENCES persons(id),
    company_id INTEGER REFERENCES companies(id),
    share_count BIGINT,
    share_ratio NUMERIC(10,4),
    report_date DATE,
    UNIQUE(person_id, company_id, report_date)
);

CREATE TABLE IF NOT EXISTS person_transfers (
    id SERIAL PRIMARY KEY,
    person_id INTEGER REFERENCES persons(id),
    from_company_id INTEGER REFERENCES companies(id),
    from_role VARCHAR(100),
    from_start_date DATE,
    to_company_id INTEGER REFERENCES companies(id),
    to_role VARCHAR(100),
    to_start_date DATE,
    transfer_days INTEGER
);

CREATE TABLE IF NOT EXISTS company_risks (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    risk_type VARCHAR(50),
    source VARCHAR(100),
    event_date DATE,
    description TEXT,
    UNIQUE(company_id, event_date, risk_type)
);

-- events 扩展字段
ALTER TABLE events ADD COLUMN IF NOT EXISTS reason_category VARCHAR(50);
ALTER TABLE events ADD COLUMN IF NOT EXISTS post_risk_flag BOOLEAN DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS post_decline_flag BOOLEAN DEFAULT FALSE;

-- persons 扩展字段
ALTER TABLE persons ADD COLUMN IF NOT EXISTS transfer_frequency_score INTEGER DEFAULT 0;
"""

def main():
    with engine.begin() as conn:
        for stmt in SQL.strip().split(";\n"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                conn.execute(text(stmt))
    print("Schema migration completed.")

if __name__ == "__main__":
    main()
