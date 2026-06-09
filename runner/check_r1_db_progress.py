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
    sh_total = conn.execute(text("SELECT COUNT(*) FROM company_shareholders")).scalar()
    sh_companies = conn.execute(text("SELECT COUNT(DISTINCT company_id) FROM company_shareholders")).scalar()
    sp_total = conn.execute(text("SELECT COUNT(*) FROM company_stock_prices")).scalar()
    sp_companies = conn.execute(text("SELECT COUNT(DISTINCT company_id) FROM company_stock_prices")).scalar()
    rc = conn.execute(text("SELECT COUNT(*) FROM companies WHERE registered_capital IS NOT NULL")).scalar()
    ec = conn.execute(text("SELECT COUNT(*) FROM companies WHERE employee_count IS NOT NULL")).scalar()
    print(f"shareholders: {sh_total} rows / {sh_companies} companies")
    print(f"stock_prices: {sp_total} rows / {sp_companies} companies")
    print(f"registered_capital: {rc} companies")
    print(f"employee_count: {ec} companies")
