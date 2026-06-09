#!/usr/bin/env python3
import os
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

from sqlalchemy import create_engine, text
from app.config import settings
engine = create_engine(settings.database_url)

with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM company_stock_prices")).scalar()
    distinct = conn.execute(text("SELECT COUNT(DISTINCT company_id) FROM company_stock_prices")).scalar()
    last = conn.execute(text("SELECT company_id, MAX(trade_date) FROM company_stock_prices GROUP BY company_id ORDER BY company_id DESC LIMIT 1")).fetchone()
    print(f"total rows: {total}")
    print(f"distinct companies: {distinct}")
    print(f"last company_id: {last[0] if last else None}, last_trade_date: {last[1] if last else None}")
