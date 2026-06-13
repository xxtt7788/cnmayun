"""One-off backfill: re-derive role_tenures from published events.

Background
----------
Discovered 2026-06-13 that the events→role_tenures propagation was missing
(王宏向 was extracted as non_renewal chairperson on 2026-06-12, but
role_tenures still showed him as active on /people/35627). This script
re-derives role_tenures for ALL published events.

Usage:
    cd /opt/china-succession
    source /etc/china-succession/china-succession.env
    .venv/bin/python -m scripts.backfill_role_tenures_from_events --dry-run
    .venv/bin/python -m scripts.backfill_role_tenures_from_events

Args:
    --dry-run: report what would change without modifying the DB
    --limit N: only process the first N events (for testing)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path so `app` can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_role_tenures")

from app.db import SessionLocal  # noqa: E402
from app.event_propagation import backfill_role_tenures  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not modify DB")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N events")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        log.info("Running backfill (dry_run=%s, limit=%s)", args.dry_run, args.limit)
        stats = backfill_role_tenures(db, dry_run=args.dry_run)
        log.info("Done. Stats: %s", stats)
        print()
        print("=== Backfill summary ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        if args.dry_run:
            print("\nThis was a DRY RUN. Re-run without --dry-run to apply.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
