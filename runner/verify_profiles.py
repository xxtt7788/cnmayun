#!/usr/bin/env python3
"""
Verify person_profiles table after enrichment.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENV_PATH = "/etc/china-succession/china-succession.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.startswith("export "):
                    key = key[7:]
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value

from sqlalchemy import create_engine, text
engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM person_profiles")).scalar()
    with_resume = conn.execute(text("SELECT COUNT(*) FROM person_profiles WHERE resume_raw IS NOT NULL AND LENGTH(resume_raw) > 10")).scalar()
    with_career = conn.execute(text("SELECT COUNT(*) FROM person_profiles WHERE career_history_raw IS NOT NULL AND LENGTH(career_history_raw) > 10")).scalar()
    em_profiles = conn.execute(text("SELECT COUNT(*) FROM person_profiles WHERE profile_name = 'EastMoney Profile'")).scalar()
    network_profiles = conn.execute(text("SELECT COUNT(*) FROM person_profiles WHERE profile_name = 'Network Profile'")).scalar()

    print(f"Total person_profiles: {total}")
    print(f"With resume: {with_resume}")
    print(f"With career_history: {with_career}")
    print(f"EastMoney profiles: {em_profiles}")
    print(f"Network profiles: {network_profiles}")
