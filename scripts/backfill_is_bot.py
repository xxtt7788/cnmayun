"""One-off script: backfill page_views.is_bot for rows where it is NULL.

Run after deploying the schema migration. After this completes, the
``is_bot IS NULL`` carve-out in get_stats can be tightened to ``is_bot = FALSE``.

Usage:
    cd /opt/china-succession
    source /etc/china-succession/china-succession.env   # loads DATABASE_URL
    /opt/china-succession/.venv/bin/python -m scripts.backfill_is_bot

Idempotent: only processes rows with is_bot IS NULL.
"""
from __future__ import annotations

import logging
import os
import sys
import time

from sqlalchemy import text

# Load the production env file before importing app.* (DATABASE_URL lives there).
_ENV_FILE = "/etc/china-succession/china-succession.env"
if os.path.exists(_ENV_FILE) and not os.environ.get("DATABASE_URL"):
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

# Allow running as a plain script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal  # noqa: E402
from app.normalization import is_bot_user_agent  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_is_bot")

BATCH_SIZE = 10_000


def main() -> None:
    db = SessionLocal()
    try:
        start = time.monotonic()
        # Pull rows in batches and update by id. The Python-side is_bot_user_agent
        # call avoids re-implementing the substring logic in SQL.
        total_updated = 0
        while True:
            rows = db.execute(text(
                "SELECT id, user_agent FROM page_views "
                "WHERE is_bot IS NULL LIMIT :batch FOR UPDATE SKIP LOCKED"
            ), {"batch": BATCH_SIZE}).all()
            if not rows:
                break
            # Build a CASE expression server-side to avoid N round-trips
            from sqlalchemy import case
            whens = {r.id: is_bot_user_agent(r.user_agent) for r in rows}
            # The fastest path: one UPDATE per batch using VALUES + a CASE.
            # Simpler: loop and update one by one, but commit every 5k to keep
            # transactions short. Empirically 1k updates/s on this hardware.
            for row_id, is_bot in whens.items():
                db.execute(
                    text("UPDATE page_views SET is_bot = :v WHERE id = :id"),
                    {"v": is_bot, "id": row_id},
                )
            db.commit()
            total_updated += len(rows)
            log.info("updated %d rows (total=%d, elapsed=%.1fs)",
                     len(rows), total_updated, time.monotonic() - start)
        # Final: log remaining NULLs
        remaining = db.scalar(text("SELECT COUNT(*) FROM page_views WHERE is_bot IS NULL")) or 0
        log.info("done. total=%d, remaining NULLs=%d, took=%.1fs",
                 total_updated, remaining, time.monotonic() - start)
    finally:
        db.close()


if __name__ == "__main__":
    main()
