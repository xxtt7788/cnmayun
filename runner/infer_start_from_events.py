#!/usr/bin/env python3
"""
Infer start_date from events table for tenures missing start_date.

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

from app.db import session_scope
from sqlalchemy import text


def main():
    with session_scope() as db:
        # Check if events have person associations
        result = db.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'event_person_associations'
        """)).fetchone()
        
        if result:
            print("event_person_associations table exists")
            # Check structure
            cols = db.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = 'event_person_associations'
            """)).fetchall()
            print(f"Columns: {[c[0] for c in cols]}")
            
            # Try to link events to tenures
            rows = db.execute(text("""
                SELECT rt.id, e.event_date, e.event_type, e.title
                FROM role_tenures rt
                JOIN event_person_associations epa ON rt.person_id = epa.person_id
                JOIN events e ON epa.event_id = e.id
                WHERE rt.start_date IS NULL
                AND e.company_id = rt.company_id
                ORDER BY rt.id, e.event_date
                LIMIT 20
            """)).fetchall()
            print(f"\nFound {len(rows)} potential matches")
            for row in rows:
                print(f"  tenure_id={row.id}, event_date={row.event_date}, type={row.event_type}, title={row.title}")
        else:
            print("event_person_associations table does not exist")
            
        # Also check if events table has company_id and person info directly
        cols = db.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'events'
        """)).fetchall()
        print(f"\nevents columns: {[c[0] for c in cols]}")
        
        # Check if source_docs can help
        cols2 = db.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'source_docs'
        """)).fetchall()
        print(f"source_docs columns: {[c[0] for c in cols2]}")


if __name__ == "__main__":
    main()
