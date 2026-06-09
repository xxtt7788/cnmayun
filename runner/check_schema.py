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

tables = ["companies", "company_shareholders", "company_stock_prices", "event_chains", "person_shareholdings", "person_transfers", "company_risks", "events", "persons"]

with engine.connect() as conn:
    for t in tables:
        try:
            cols = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}' ORDER BY ordinal_position")).fetchall()
            print(f"{t}: {[c[0] for c in cols]}")
        except Exception as e:
            print(f"{t}: ERROR {e}")
