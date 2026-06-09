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
    done = {r[0] for r in conn.execute(text("SELECT DISTINCT company_id FROM company_shareholders")).fetchall()}
    rows = conn.execute(text("SELECT id, ticker, exchange FROM companies WHERE is_active = true ORDER BY id")).fetchall()

remaining = [r for r in rows if r.id not in done]
print(f"Done: {len(done)}, Remaining: {len(remaining)}")
if remaining:
    print(f"Next 5: {[(r.id, r.ticker, r.exchange) for r in remaining[:5]]}")
