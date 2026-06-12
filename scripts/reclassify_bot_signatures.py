"""One-off script: reclassify page_views.is_bot from FALSE to TRUE for rows
whose User-Agent now matches an AI training / SEO scraper signature that was
NOT in the original ``_BOT_SIGNATURES`` list at the time the row was written.

Why this exists separately from ``scripts/backfill_is_bot.py``:
  - ``backfill_is_bot.py`` only handles rows where ``is_bot IS NULL``
    (pre-deploy rows that haven't been classified yet).
  - This script handles rows where ``is_bot = FALSE`` but the UA *should* now
    be classified as bot (e.g., ClaudeBot traffic that slipped through before
    we added the signature on 2026-06-12).

Usage:
    cd /opt/china-succession
    source /etc/china-succession/china-succession.env   # loads DATABASE_URL
    /opt/china-succession/.venv/bin/python -m scripts.reclassify_bot_signatures

Idempotent: only flips FALSE -> TRUE. Re-running has no further effect.
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
from app.normalization import _BOT_SIGNATURES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reclassify_bot_signatures")


def _escape_like(s: str) -> str:
    """Escape SQL LIKE metacharacters in a substring for safe binding.

    ``%`` and ``_`` are LIKE wildcards; ``\\`` is the LIKE escape char. Wrap
    each signature in ``%`` for substring matching AFTER escaping the inner
    contents, so a signature like ``ia_archiver`` matches only the literal
    underscore, not "any single character between ia and archiver".
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_reclassify_sql(signatures: tuple[str, ...] | list[str]) -> str:
    """Build a single UPDATE that flips is_bot=FALSE -> TRUE for matching UAs.

    Exposed as a pure function (no DB access) so it can be unit-tested without
    a live database connection. The SQL is dialect-portable: PostgreSQL and
    SQLite both support ``LOWER(x) LIKE :p`` with bound parameters.

    Note: signatures containing SQL LIKE metacharacters (``%``, ``_``) must be
    escaped by the caller before binding (see ``_escape_like``). The bound
    param values for ``main()`` are wrapped in ``%`` for substring matching.
    """
    if not signatures:
        raise ValueError("signatures must be non-empty")
    like_clauses = " OR ".join(
        f"LOWER(COALESCE(user_agent, '')) LIKE :p{i}" for i in range(len(signatures))
    )
    return f"""
        UPDATE page_views
        SET is_bot = TRUE
        WHERE is_bot = FALSE
          AND ({like_clauses})
    """.strip()


def main() -> None:
    db = SessionLocal()
    try:
        start = time.monotonic()
        sql = build_reclassify_sql(_BOT_SIGNATURES)
        params = {f"p{i}": f"%{_escape_like(sig)}%" for i, sig in enumerate(_BOT_SIGNATURES)}
        log.info(
            "reclassifying with %d signatures (claudebot=%s, gptbot=%s, ...)",
            len(_BOT_SIGNATURES),
            "claudebot" in _BOT_SIGNATURES,
            "gptbot" in _BOT_SIGNATURES,
        )
        result = db.execute(text(sql), params)
        db.commit()
        log.info(
            "re-tagged %d rows as bot (FALSE -> TRUE), took %.1fs",
            result.rowcount,
            time.monotonic() - start,
        )

        # Refresh the daily aggregate so /stats reflects the change immediately,
        # without waiting for the next sync-notices cycle (≤30 min).
        # Wrap in try/except: the UPDATE has already been committed, so the
        # reclassification is durable — if the recompute fails, we log a warning
        # rather than masking the success. Operator can rerun the recompute
        # manually (or wait for the next sync-notices cycle, ≤30 min).
        from app.stats_aggregator import recompute_page_view_daily
        agg_start = time.monotonic()
        try:
            rows_upserted = recompute_page_view_daily(db, days=14)
        except Exception:  # noqa: BLE001 — best-effort cache refresh
            log.warning(
                "recompute_page_view_daily failed; UPDATE is committed but "
                "/stats may be stale until next sync cycle (≤30 min) or "
                "manual `python -m scripts.backfill_page_view_daily` rerun",
                exc_info=True,
            )
        else:
            log.info(
                "recomputed page_view_daily (14-day window, %d rows upserted, %.1fs)",
                rows_upserted,
                time.monotonic() - agg_start,
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
