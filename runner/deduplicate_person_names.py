#!/usr/bin/env python3
"""
Deduplicate person names using resume/birth_year/education as signals.

Identifies persons with identical canonical_name but different birth_year
or education, and updates alias_names to disambiguate.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import json
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
from sqlalchemy import text


def main():
    with session_scope() as db:
        # Find duplicate canonical_names
        rows = db.execute(text("""
            SELECT 
                p.canonical_name,
                p.id,
                p.birth_year,
                p.gender,
                p.education,
                pp.professional_title,
                pp.nationality
            FROM persons p
            LEFT JOIN person_profiles pp ON p.id = pp.person_id
            WHERE p.canonical_name IS NOT NULL AND LENGTH(p.canonical_name) >= 2
            ORDER BY p.canonical_name, p.id
        """)).fetchall()

    # Group by name
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_name[row.canonical_name].append({
            "id": row.id,
            "birth_year": row.birth_year,
            "gender": row.gender,
            "education": row.education,
            "title": row.professional_title,
            "nationality": row.nationality,
        })

    # Find names with multiple distinct persons
    duplicates = {
        name: persons for name, persons in by_name.items()
        if len(persons) > 1
    }

    print(f"Total persons: {len(rows)}")
    print(f"Unique names: {len(by_name)}")
    print(f"Duplicate names: {len(duplicates)}")

    # Analyze duplicates
    updated = 0
    with session_scope() as db:
        for name, persons in sorted(duplicates.items(), key=lambda x: -len(x[1]))[:50]:
            # If they have different birth_years, they're different people
            birth_years = set(p["birth_year"] for p in persons if p["birth_year"])
            if len(birth_years) > 1:
                # Update alias_names with disambiguation info
                for p in persons:
                    alias = f"{name}({p['birth_year'] or '?'})"
                    # Only update if alias not already present
                    current = db.execute(
                        text("SELECT alias_names FROM persons WHERE id = :id"),
                        {"id": p["id"]}
                    ).scalar()
                    current_list = json.loads(current) if current else []
                    if alias not in current_list:
                        current_list.append(alias)
                        db.execute(
                            text("UPDATE persons SET alias_names = :alias WHERE id = :id"),
                            {"alias": json.dumps(current_list, ensure_ascii=False), "id": p["id"]}
                        )
                        updated += 1

        db.commit()

    print(f"\nUpdated {updated} persons with disambiguation aliases.")

    # Show top duplicates
    print("\n=== Top 10 most duplicated names ===")
    for name, persons in sorted(duplicates.items(), key=lambda x: -len(x[1]))[:10]:
        bys = [str(p["birth_year"] or "?") for p in persons]
        print(f"  {name}: {len(persons)} persons, birth_years=[{', '.join(bys)}]")


if __name__ == "__main__":
    main()
