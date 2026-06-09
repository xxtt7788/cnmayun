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
    sh_distinct = conn.execute(text("SELECT COUNT(DISTINCT company_id) FROM company_shareholders")).scalar()
    reg_cap = conn.execute(text("SELECT COUNT(*) FROM companies WHERE registered_capital IS NOT NULL")).scalar()
    emp = conn.execute(text("SELECT COUNT(*) FROM companies WHERE employee_count IS NOT NULL")).scalar()
    print(f"shareholders: {sh_total} rows, {sh_distinct} companies")
    print(f"registered_capital filled: {reg_cap}")
    print(f"employee_count filled: {emp}")
