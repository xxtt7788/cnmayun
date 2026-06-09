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
    count = conn.execute(text("SELECT COUNT(*) FROM event_chains")).scalar()
    print(f"event_chains count: {count}")
    rows = conn.execute(text("SELECT * FROM event_chains WHERE company_id = 94 AND role = 'director' AND event_out_id = 1050")).fetchall()
    for r in rows:
        print(dict(r._mapping))
