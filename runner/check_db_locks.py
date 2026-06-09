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
    rows = conn.execute(text("SELECT pid, state, query_start, query FROM pg_stat_activity WHERE datname = 'china_succession' AND state != 'idle'")).fetchall()
    print(f"active connections: {len(rows)}")
    for r in rows:
        print(f"  pid={r[0]} state={r[1]} query={r[3][:100] if r[3] else None}")
