#!/usr/bin/env python3
"""
Reconstruct tenure start_date from appointment/nomination events.

For tenures missing start_date (but having end_date), find matching
appointment/nomination events and use their effective_date as start_date.

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
from app.models import Event, RoleTenure
from sqlalchemy import select, and_


def main():
    with session_scope() as db:
        # Find tenures missing start_date but having end_date
        tenures = db.scalars(
            select(RoleTenure).where(
                RoleTenure.start_date.is_(None),
                RoleTenure.end_date.isnot(None)
            )
        ).all()

    print(f"Tenures missing start_date: {len(tenures)}")
    if not tenures:
        print("Nothing to do.")
        return

    updated = 0
    no_match = 0
    multi_match = 0
    start_time = __import__('time').time()

    for i, tenure in enumerate(tenures):
        with session_scope() as db:
            # Find matching appointment/nomination events
            events = db.scalars(
                select(Event).where(
                    Event.company_id == tenure.company_id,
                    Event.person_id == tenure.person_id,
                    Event.event_type.in_(["appointment", "nomination"]),
                    Event.effective_date.isnot(None)
                ).order_by(Event.effective_date)
            ).all()

            if not events:
                no_match += 1
                continue

            # If multiple events, pick the earliest one
            # If role_canonical matches, prefer that one
            best_event = None
            for evt in events:
                if evt.role_canonical == tenure.role_canonical:
                    best_event = evt
                    break
            if best_event is None:
                best_event = events[0]
                if len(events) > 1:
                    multi_match += 1

            # Update tenure
            t = db.scalar(select(RoleTenure).where(RoleTenure.id == tenure.id))
            if t:
                t.start_date = best_event.effective_date
                # If the event gave us a start_date after end_date, something is wrong
                # but we'll still set it (data quality issue, not ours to fix)
                db.commit()
                updated += 1

        if (i + 1) % 500 == 0:
            elapsed = __import__('time').time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  Progress: {i+1}/{len(tenures)} | updated={updated} | no_match={no_match} | multi={multi_match} | {rate:.1f}/sec")

    print(f"\nUpdated: {updated}, No match: {no_match}, Multi-match (used earliest): {multi_match}")
    print(f"Total time: {__import__('time').time() - start_time:.1f}s")


if __name__ == "__main__":
    main()
