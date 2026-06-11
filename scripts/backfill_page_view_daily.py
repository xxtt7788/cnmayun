"""One-off script: backfill page_view_daily for the last N days.

Run after deploying the schema migration. The aggregator's daily call only
refreshes the last 2 days; this script populates the historical window the
first time so /stats daily_trend / top_pages / top_referrers are accurate
immediately.

Usage:
    cd /opt/china-succession
    /opt/china-succession/.venv/bin/python -m scripts.backfill_page_view_daily
    /opt/china-succession/.venv/bin/python -m scripts.backfill_page_view_daily --days 30
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

# Load the production env file before importing app.* (DATABASE_URL lives there).
# This is required when running the script over SSH — the env file is only
# auto-loaded by the systemd service, not by an interactive shell.
_ENV_FILE = "/etc/china-succession/china-succession.env"
if os.path.exists(_ENV_FILE) and not os.environ.get("DATABASE_URL"):
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import session_scope  # noqa: E402
from app.stats_aggregator import recompute_page_view_daily  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_pv_daily")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14, help="Number of days to backfill (default 14)")
    args = parser.parse_args()

    with session_scope() as db:
        # Recompute only once for the whole window — the function DELETEs
        # the window and re-inserts, so passing days=N covers N days in one call.
        # For very large windows (months) we'd want to chunk; for 14 days this
        # is fine.
        n = recompute_page_view_daily(db, days=args.days)
    log.info("backfill done. rows upserted: %d for the last %d days", n, args.days)


if __name__ == "__main__":
    main()
