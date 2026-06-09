#!/usr/bin/env python3
"""
Extract actual effective dates from source document text - v2 with broader patterns.

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

# Broader regex patterns for effective date extraction
# Handle spaces/newlines in PDF-extracted text
EFFECTIVE_PATTERNS = [
    # "任期自2023年5月10日起"
    re.compile(r"任期自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起"),
    # "自2023年5月10日起生效/任职/担任"
    re.compile(r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起(?:生效|任职|担任|履行)"),
    # "2023年5月10日起生效"
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起\s*生效"),
    # "任期从2023年5月10日开始"
    re.compile(r"任期从\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日开始"),
    # "自2023年5月10日起"
    re.compile(r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起"),
    # "于2023年5月10日生效"
    re.compile(r"于\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:生效|任职|担任)"),
    # "2023年5月10日任职"
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:任职|担任|生效)"),
    # "任期自2023年5月起" (no day)
    re.compile(r"任期自\s*(\d{4})\s*年\s*(\d{1,2})\s*月起"),
    # "自2023年5月起" (no day)
    re.compile(r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月起"),
    # "任期：2023年5月10日至2026年5月9日" -> extract start date
    re.compile(r"任期\s*[:：]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*至"),
    # "第五届董事会任期自2020年1月1日起"
    re.compile(r"任期自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起"),
    # Date near "聘任" or "任命"
    re.compile(r"(?:聘任|任命|选举|提名).*?(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
]

# Patterns that indicate resolution date (董事会/股东大会决议日)
RESOLUTION_PATTERNS = [
    re.compile(r"(?:董事会|股东大会|股东会).*?(?:决议|通过|审议|批准).*?(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
]


def extract_date_from_text(text: str) -> tuple[date | None, str]:
    """Extract effective date from announcement text. Returns (date, source_pattern)."""
    if not text:
        return None, ""

    # Try each date pattern
    for pat in EFFECTIVE_PATTERNS:
        m = pat.search(text)
        if m:
            groups = m.groups()
            try:
                year = int(groups[0])
                month = int(groups[1])
                day = int(groups[2]) if len(groups) >= 3 else 1
                # Validate reasonable date range
                if 2000 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
                    return date(year, month, day), pat.pattern[:40]
            except (ValueError, IndexError):
                continue

    return None, ""


def main():
    with session_scope() as db:
        rows = db.execute(text("""
            SELECT e.id, e.announcement_date, e.effective_date, sd.raw_text, e.event_type, sd.title as title
            FROM events e
            JOIN source_documents sd ON e.source_document_id = sd.id
            WHERE sd.raw_text IS NOT NULL AND LENGTH(sd.raw_text) > 50
            ORDER BY e.id
        """)).fetchall()

    print(f"Events with source text: {len(rows)}")

    updates = []
    pattern_counts: dict[str, int] = {}
    no_match = 0

    for event_id, ann_date, eff_date, raw_text, event_type, title in rows:
        extracted, pattern = extract_date_from_text(raw_text or "")

        if extracted is None:
            no_match += 1
            continue

        if pattern:
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

        # Only update if different from announcement_date
        if ann_date and extracted != ann_date:
            updates.append((event_id, extracted, pattern))

    print(f"\nExtracted different date: {len(updates)}")
    print(f"No match: {no_match}")
    print(f"\nPattern distribution:")
    for pat, cnt in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {pat}: {cnt}")

    if not updates:
        print("\nNo updates needed.")
        return

    print("\nSample updates:")
    for eid, new_date, pat in updates[:15]:
        print(f"  event_id={eid}, date={new_date}, pattern={pat}")

    # Apply updates
    with session_scope() as db:
        for eid, new_date, _ in updates:
            db.execute(
                text("UPDATE events SET effective_date = :date WHERE id = :id"),
                {"date": new_date, "id": eid}
            )
        db.commit()

    print(f"\nUpdated {len(updates)} events.")


if __name__ == "__main__":
    main()
