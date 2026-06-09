#!/usr/bin/env python3
"""
Compute cross-company tenure network for each person.

For each person with tenures at multiple companies, generate a summary
of their career trajectory: current roles, past roles, and company count.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys
from collections import defaultdict

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
from app.models import PersonProfile
from sqlalchemy import select, text


def main():
    with session_scope() as db:
        # Load all tenures with company and person info
        rows = db.execute(text("""
            SELECT 
                rt.person_id,
                p.canonical_name,
                rt.company_id,
                c.ticker,
                c.exchange,
                rt.role_canonical,
                rt.start_date,
                rt.end_date,
                rt.is_active
            FROM role_tenures rt
            JOIN persons p ON rt.person_id = p.id
            JOIN companies c ON rt.company_id = c.id
            ORDER BY rt.person_id, rt.start_date
        """)).fetchall()

    print(f"Total tenure records: {len(rows)}")

    # Group by person
    person_tenures: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        person_tenures[row.person_id].append({
            "name": row.canonical_name,
            "company_id": row.company_id,
            "ticker": row.ticker,
            "exchange": row.exchange,
            "role": row.role_canonical,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "is_active": row.is_active,
        })

    # Find persons with multiple companies
    multi_company = {
        pid: tenures for pid, tenures in person_tenures.items()
        if len(set(t["company_id"] for t in tenures)) > 1
    }

    print(f"Persons with tenures: {len(person_tenures)}")
    print(f"Persons in multiple companies: {len(multi_company)}")

    # Generate profile summaries for multi-company persons
    profile_updates = {}
    for pid, tenures in multi_company.items():
        companies = sorted(set(t["ticker"] for t in tenures))
        active_roles = [f"{t['ticker']}({t['exchange']})-{t['role']}" for t in tenures if t["is_active"]]
        past_roles = [f"{t['ticker']}-{t['role']}" for t in tenures if not t["is_active"]]

        career_summary = f"历任{len(companies)}家公司: {', '.join(companies[:10])}"
        if len(companies) > 10:
            career_summary += f" 等共{len(companies)}家"

        if active_roles:
            career_summary += f"\n现任: {', '.join(active_roles[:5])}"

        profile_updates[pid] = {
            "career_summary": career_summary,
            "company_count": len(companies),
            "active_count": len(active_roles),
            "past_count": len(past_roles),
        }

    print(f"Profiles to update: {len(profile_updates)}")

    # Show top 10 most mobile executives
    top_mobile = sorted(profile_updates.items(), key=lambda x: -x[1]["company_count"])[:10]
    print("\n=== Top 10 most mobile executives ===")
    for pid, data in top_mobile:
        name = person_tenures[pid][0]["name"]
        print(f"  {name}: {data['company_count']} companies, {data['active_count']} active")

    # Apply to database: write to person_profiles or update persons.notes
    BATCH_SIZE = 500
    updated = 0
    inserted = 0

    with session_scope() as db:
        person_ids = list(profile_updates.keys())
        for i in range(0, len(person_ids), BATCH_SIZE):
            batch_ids = person_ids[i:i+BATCH_SIZE]
            existing_profiles = {}
            for p in db.scalars(
                select(PersonProfile).where(PersonProfile.person_id.in_(batch_ids))
            ).all():
                existing_profiles[p.person_id] = p

            for pid in batch_ids:
                data = profile_updates[pid]
                profile = existing_profiles.get(pid)
                if profile:
                    # Update existing profile with network summary
                    db.execute(
                        text("""
                            UPDATE person_profiles 
                            SET career_history_raw = :career
                            WHERE person_id = :pid
                        """),
                        {
                            "career": data["career_summary"],
                            "pid": pid,
                        }
                    )
                    updated += 1
                else:
                    # Insert new profile
                    db.execute(
                        text("""
                            INSERT INTO person_profiles 
                            (person_id, identity_key, profile_name, career_history_raw, resume_raw, source_url, confidence, created_at, updated_at)
                            VALUES (:pid, :ikey, 'Network Profile', :career, '', 'computed', 1.0, NOW(), NOW())
                        """),
                        {
                            "pid": pid,
                            "ikey": f"network_{pid}",
                            "career": data["career_summary"],
                        }
                    )
                    inserted += 1

        db.commit()

    print(f"\nInserted: {inserted}, Updated: {updated}")
    print("Cross-company network computation complete.")


if __name__ == "__main__":
    main()
