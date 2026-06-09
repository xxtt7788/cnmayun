#!/usr/bin/env python3
"""Fix company with UNKNOWN exchange based on ticker prefix."""
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
    row = conn.execute(text("""
        SELECT id, ticker, company_name FROM companies
        WHERE exchange = 'UNKNOWN' OR exchange IS NULL
    """)).fetchone()

if not row:
    print("No UNKNOWN exchange companies found.")
    sys.exit(0)

ticker = row.ticker
if ticker.startswith('6'):
    new_ex = 'SSE'
elif ticker.startswith('0') or ticker.startswith('3'):
    new_ex = 'SZSE'
elif ticker[0] in '489':
    new_ex = 'BSE'
else:
    new_ex = 'UNKNOWN'

print(f"Fixing {ticker} ({row.company_name}): UNKNOWN -> {new_ex}")

with engine.begin() as conn:
    conn.execute(text("UPDATE companies SET exchange = :ex WHERE id = :id"), {"ex": new_ex, "id": row.id})

print("Done.")
