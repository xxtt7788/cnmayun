#!/usr/bin/env python3
"""
Reconstruct tenure chains from appointment/resignation events.

For each (company, person, role) triplet:
- appointment event -> tenure.start_date
- resignation/removal/non_renewal event -> tenure.end_date
- If appointment date < existing start_date, update start_date

This fills missing start_dates for tenures that have matching events.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys
from datetime import date

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
        # Find appointment events linked to tenures
        appointment_links = db.execute(text("""
            SELECT 
                rt.id as tenure_id,
                rt.start_date,
                e.effective_date as event_date,
                e.event_type,
                rt.person_id,
                p.canonical_name
            FROM role_tenures rt
            JOIN persons p ON rt.person_id = p.id
            JOIN events e ON rt.company_id = e.company_id 
                AND rt.person_id = e.person_id
                AND (rt.role_canonical = e.role_canonical OR e.role_canonical IS NULL)
            WHERE e.event_type IN ('appointment', 'reelection', 'interim_assignment')
            AND rt.start_date IS NULL
            ORDER BY rt.id, e.effective_date
        """)).fetchall()

        # Find resignation/removal events linked to tenures
        end_links = db.execute(text("""
            SELECT 
                rt.id as tenure_id,
                rt.end_date,
                e.effective_date as event_date,
                e.event_type,
                rt.person_id,
                p.canonical_name
            FROM role_tenures rt
            JOIN persons p ON rt.person_id = p.id
            JOIN events e ON rt.company_id = e.company_id 
                AND rt.person_id = e.person_id
                AND (rt.role_canonical = e.role_canonical OR e.role_canonical IS NULL)
            WHERE e.event_type IN ('resignation', 'removal', 'non_renewal', 'retirement')
            AND rt.end_date IS NULL
            AND rt.is_active = TRUE
            ORDER BY rt.id, e.effective_date
        """)).fetchall()

    print(f"Appointment links for missing start_date: {len(appointment_links)}")
    print(f"Resignation links for missing end_date: {len(end_links)}")

    # Build update maps (take earliest date per tenure)
    start_updates: dict[int, date] = {}
    end_updates: dict[int, date] = {}

    for row in appointment_links:
        tid = row.tenure_id
        event_date = row.event_date
        if event_date and (tid not in start_updates or event_date < start_updates[tid]):
            start_updates[tid] = event_date

    for row in end_links:
        tid = row.tenure_id
        event_date = row.event_date
        if event_date and (tid not in end_updates or event_date < end_updates[tid]):
            end_updates[tid] = event_date

    print(f"Unique start_date updates: {len(start_updates)}")
    print(f"Unique end_date updates: {len(end_updates)}")

    # Show samples
    print("\nSample start_date updates:")
    for tid, d in list(start_updates.items())[:10]:
        print(f"  tenure_id={tid}, start_date={d}")

    print("\nSample end_date updates:")
    for tid, d in list(end_updates.items())[:10]:
        print(f"  tenure_id={tid}, end_date={d}")

    # Apply updates
    updated_start = 0
    updated_end = 0

    with session_scope() as db:
        for tid, d in start_updates.items():
            result = db.execute(
                text("UPDATE role_tenures SET start_date = :date WHERE id = :id AND start_date IS NULL"),
                {"date": d, "id": tid}
            )
            if result.rowcount > 0:
                updated_start += 1

        for tid, d in end_updates.items():
            result = db.execute(
                text("UPDATE role_tenures SET end_date = :date, is_active = FALSE WHERE id = :id AND end_date IS NULL"),
                {"date": d, "id": tid}
            )
            if result.rowcount > 0:
                updated_end += 1

        db.commit()

    print(f"\nUpdated start_date: {updated_start}")
    print(f"Updated end_date: {updated_end}")
    print("Tenure chain reconstruction complete.")


if __name__ == "__main__":
    main()
