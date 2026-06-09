#!/usr/bin/env python3
"""
Extract actual effective dates from source document text and update events.

Current state: events.effective_date == events.announcement_date for all records.
Many announcements contain phrases like "任期自2023年5月10日起" or "自即日起生效".
This script extracts the real effective date from raw_text and updates events.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from __future__ import annotations

import os
import re
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

# Regex patterns for effective date extraction
EFFECTIVE_PATTERNS = [
    # "任期自2023年5月10日起"
    re.compile(r"任期自(\d{4})年(\d{1,2})月(\d{1,2})日起"),
    # "自2023年5月10日起生效"
    re.compile(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起生效"),
    # "自2023年5月10日起任职"
    re.compile(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起任职"),
    # "2023年5月10日起生效"
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日起生效"),
    # "任期从2023年5月10日开始"
    re.compile(r"任期从(\d{4})年(\d{1,2})月(\d{1,2})日开始"),
    # "自2023年5月10日起担任"
    re.compile(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起担任"),
    # "自2023年5月起生效" (no day)
    re.compile(r"自(\d{4})年(\d{1,2})月起生效"),
    # "自即日起生效" -> already equals announcement_date, skip
]

# Patterns that indicate "effective immediately" (no change needed)
IMMEDIATE_PATTERNS = [
    re.compile(r"自即日起生效"),
    re.compile(r"自即日起任职"),
    re.compile(r"自即日起担任"),
]


def extract_date_from_text(text: str, announcement_date: date | None) -> date | None:
    """Extract effective date from announcement text. Returns None if not found or immediate."""
    if not text:
        return None

    # Check for immediate patterns first
    for pat in IMMEDIATE_PATTERNS:
        if pat.search(text):
            return None  # Keep announcement_date

    # Try each date pattern
    for pat in EFFECTIVE_PATTERNS:
        m = pat.search(text)
        if m:
            groups = m.groups()
            try:
                year = int(groups[0])
                month = int(groups[1])
                day = int(groups[2]) if len(groups) >= 3 else 1
                return date(year, month, day)
            except (ValueError, IndexError):
                continue

    return None


def main():
    with session_scope() as db:
        # Get all events with their source document text
        rows = db.execute(text("""
            SELECT e.id, e.announcement_date, e.effective_date, sd.raw_text, e.event_type
            FROM events e
            JOIN source_documents sd ON e.source_document_id = sd.id
            WHERE sd.raw_text IS NOT NULL AND LENGTH(sd.raw_text) > 50
            ORDER BY e.id
        """)).fetchall()

    print(f"Events with source text: {len(rows)}")

    updates = []
    immediate_count = 0
    extracted_count = 0
    no_match_count = 0

    for event_id, ann_date, eff_date, raw_text, event_type in rows:
        extracted = extract_date_from_text(raw_text or "", ann_date)

        if extracted is None:
            # Check if immediate
            if any(pat.search(raw_text or "") for pat in IMMEDIATE_PATTERNS):
                immediate_count += 1
            else:
                no_match_count += 1
            continue

        # Only update if extracted date differs from announcement_date
        if ann_date and extracted != ann_date:
            updates.append((event_id, extracted))
            extracted_count += 1

    print(f"Effective immediately (keep ann_date): {immediate_count}")
    print(f"Extracted different date: {extracted_count}")
    print(f"No date pattern found: {no_match_count}")
    print(f"Total to update: {len(updates)}")

    if not updates:
        print("\nNo updates needed.")
        return

    # Show sample
    print("\nSample updates:")
    for eid, new_date in updates[:10]:
        print(f"  event_id={eid}, new_effective_date={new_date}")

    # Apply updates
    BATCH_SIZE = 100
    with session_scope() as db:
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i:i+BATCH_SIZE]
            for eid, new_date in batch:
                db.execute(
                    text("UPDATE events SET effective_date = :date WHERE id = :id"),
                    {"date": new_date, "id": eid}
                )
        db.commit()

    print(f"\nUpdated {len(updates)} events with extracted effective dates.")


if __name__ == "__main__":
    main()
