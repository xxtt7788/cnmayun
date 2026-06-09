#!/usr/bin/env python3
"""Sync education from latest executive_snapshot to person_profiles."""
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

print("Building person_id -> education mapping from snapshots...")
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT DISTINCT ON (person_id) person_id, education
        FROM executive_snapshots
        WHERE education IS NOT NULL AND education != ''
        ORDER BY person_id, snapshot_date DESC
    """)).fetchall()

edu_map = {r.person_id: r.education for r in rows}
print(f"Got education for {len(edu_map)} persons from snapshots")

if not edu_map:
    print("No education data in snapshots.")
    sys.exit(0)

print("Updating person_profiles...")
updated = 0
with engine.begin() as conn:
    for pid, edu in edu_map.items():
        result = conn.execute(
            text("""
                UPDATE person_profiles
                SET education = :edu
                WHERE person_id = :pid AND (education IS NULL OR education = '')
            """),
            {"pid": pid, "edu": edu}
        )
        updated += result.rowcount

print(f"Updated {updated} person_profiles rows with education")

# Summary
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM person_profiles")).scalar()
    has_edu = conn.execute(text("SELECT COUNT(*) FROM person_profiles WHERE education IS NOT NULL AND education != ''")).scalar()

print(f"Profile education coverage: {has_edu}/{total} ({has_edu/total*100:.1f}%)")
