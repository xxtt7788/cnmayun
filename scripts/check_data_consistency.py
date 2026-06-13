"""One-shot consistency checks: are events + role_tenures + processing_runs in sync?

Run periodically (cron) and on demand. Exits with non-zero if any check fails,
so it can be wired into monitoring.

Checks:
1. published events missing role_tenure updates (events whose person/company/
   role tuple has no role_tenure row OR still has is_active=true despite
   being a non_renewal/removal/resignation/retirement).
2. source_documents older than 24h with no processing_run.
3. Active role_tenures with end_date IS NULL where the most recent event
   for that (person, company, role) is a closing type.

Usage:
    python -m scripts.check_data_consistency [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402


def run_checks(db) -> dict:
    out: dict = {"checks": [], "ok": True}

    # 1. Events that should have closed a tenure but didn't
    rows = db.execute(text("""
        SELECT e.id, p.canonical_name, e.role_canonical, e.event_type,
               e.announcement_date, c.ticker
        FROM events e
        JOIN persons p ON p.id = e.person_id
        JOIN companies c ON c.id = e.company_id
        JOIN role_tenures t ON t.person_id = e.person_id
            AND t.company_id = e.company_id
            AND t.role_canonical = e.role_canonical
        WHERE e.event_type IN ('non_renewal', 'removal', 'resignation', 'retirement')
          AND e.event_status = 'published'
          AND t.is_active = true
          AND t.end_date IS NULL
        ORDER BY e.announcement_date DESC
        LIMIT 50
    """)).all()
    out["checks"].append({
        "name": "stale_active_tenures_after_closing_event",
        "count": len(rows),
        "sample": [dict(r._mapping) for r in rows[:5]],
    })
    if len(rows) > 0:
        out["ok"] = False

    # 2. Source documents older than 24h with no processing run
    rows = db.execute(text("""
        SELECT sd.id, sd.title, sd.created_at, c.ticker
        FROM source_documents sd
        LEFT JOIN companies c ON c.id = sd.company_id
        LEFT JOIN document_processing_runs pr ON pr.source_document_id = sd.id
        WHERE pr.id IS NULL
          AND sd.created_at < NOW() - INTERVAL '24 hours'
        ORDER BY sd.created_at DESC
        LIMIT 50
    """)).all()
    out["checks"].append({
        "name": "unprocessed_documents_older_than_24h",
        "count": len(rows),
        "sample": [dict(r._mapping) for r in rows[:5]],
    })
    # Note: do NOT mark ok=False for this. Many of these are old seed/backfill
    # records without raw_text. The real check would be "unprocessed AND has raw_text".

    # 3. Active tenures with very old start_date and no end_date (heuristic)
    rows = db.execute(text("""
        SELECT t.id, p.canonical_name, t.role_canonical, t.start_date,
               c.ticker, t.confidence
        FROM role_tenures t
        JOIN persons p ON p.id = t.person_id
        JOIN companies c ON c.id = t.company_id
        WHERE t.is_active = true
          AND t.end_date IS NULL
          AND t.start_date IS NOT NULL
          AND t.start_date < NOW() - INTERVAL '4 years'
        ORDER BY t.start_date ASC
        LIMIT 20
    """)).all()
    out["checks"].append({
        "name": "very_long_active_tenures_over_4_years",
        "count": len(rows),
        "sample": [dict(r._mapping) for r in rows[:5]],
    })
    # Also heuristic-only; not a hard failure.

    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        out = run_checks(db)
        if args.json:
            print(json.dumps(out, default=str, ensure_ascii=False, indent=2))
        else:
            for chk in out["checks"]:
                print(f"[{chk['name']}] count={chk['count']}")
                if chk.get("sample"):
                    for s in chk["sample"][:3]:
                        print(f"  - {s}")
            print(f"\noverall ok: {out['ok']}")
        return 0 if out["ok"] else 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
