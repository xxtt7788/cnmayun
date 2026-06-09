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
    cols = [c[0] for c in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'role_tenures' ORDER BY ordinal_position")).fetchall()]
    print("role_tenures columns:", cols)
    rows = conn.execute(text("SELECT * FROM role_tenures LIMIT 1")).fetchall()
    if rows:
        print("sample:", dict(rows[0]._mapping))
