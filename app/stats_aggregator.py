"""PageViewDaily aggregator.

Mirrors the pattern of ``notice_pipeline.recompute_company_metrics``:
- Called at the tail of every ``sync_management_notices`` run (every 30 min).
- Idempotent: deletes the recompute window, then bulk-inserts.
- The first run after deploy may take a few seconds on a 543K-row table;
  subsequent runs only touch the most recent ``days`` days.

For one-off full backfill use ``backfill_page_view_daily(days=14)`` from CLI.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PageView, PageViewDaily
from app.normalization import is_bot_user_agent

logger = logging.getLogger(__name__)


# --- browser/referrer derivation shared with the read path ---

_BROWSER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("edg", "Edge"),
    ("chrome", "Chrome"),
    ("safari", "Safari"),
    ("firefox", "Firefox"),
    ("mobile", "Mobile"),
    ("android", "Mobile"),
    ("iphone", "Mobile"),
)


def _browser_bucket(user_agent: str | None) -> str:
    if not user_agent:
        return "Other"
    ua = user_agent.lower()
    if "safari" in ua and "chrome" not in ua:
        return "Safari"
    for sig, name in _BROWSER_PATTERNS:
        if sig in ua:
            return name
    return "Other"


def _referrer_host(referrer: str | None) -> str | None:
    if not referrer:
        return None
    try:
        # Cheap parse — we don't want to pull in urllib just for this.
        if "://" in referrer:
            host = referrer.split("://", 1)[1].split("/", 1)[0]
        else:
            host = referrer.split("/", 1)[0]
        return host[:255] or None
    except Exception:  # noqa: BLE001 — best-effort, never crash on weird referrer
        return None


# --- the actual aggregator ---

def recompute_page_view_daily(db: Session, *, days: int = 2) -> int:
    """Recompute ``page_view_daily`` for the last ``days`` days.

    Returns the number of rows upserted. Safe to call frequently — the window
    is small and the DELETE/INSERT path uses the partial index on is_bot.
    """
    cutoff_date = date.today() - timedelta(days=days - 1)
    cutoff_dt = datetime.combine(cutoff_date, datetime.min.time())

    # Drop the window first (idempotent).
    db.execute(delete(PageViewDaily).where(PageViewDaily.day >= cutoff_date))

    is_sqlite = settings.database_url.startswith("sqlite")

    # Pull aggregated rows from page_views. Use a single SQL pass to avoid
    # round-tripping per-group.
    if is_sqlite:
        # SQLite: GROUP BY on (day, hour, path, user_agent, is_bot). UA and
        # referrer are then bucketed in Python so dev (SQLite) and prod
        # (PostgreSQL) produce the same browser_bucket values.
        rows = db.execute(text("""
            SELECT
                DATE(created_at) AS day,
                CAST(strftime('%H', created_at) AS INTEGER) AS hour,
                path,
                COALESCE(referrer, '') AS referrer,
                COALESCE(user_agent, '') AS user_agent,
                COALESCE(is_bot, 0) AS is_bot,
                COUNT(*) AS pv_count,
                COUNT(DISTINCT session_id) AS uv_count
            FROM page_views
            WHERE created_at >= :cutoff
            GROUP BY DATE(created_at),
                     CAST(strftime('%H', created_at) AS INTEGER),
                     path, referrer, user_agent, is_bot
        """), {"cutoff": cutoff_dt}).all()
    else:
        # PostgreSQL: same shape; we'll bucket browser/referrer in Python to
        # keep one code path. (Native PG functions would be faster but we
        # avoid an extension dependency for now.)
        rows = db.execute(text("""
            SELECT
                DATE(created_at) AS day,
                EXTRACT(HOUR FROM created_at)::int AS hour,
                path,
                COALESCE(referrer, '') AS referrer,
                COALESCE(user_agent, '') AS user_agent,
                COALESCE(is_bot, FALSE) AS is_bot,
                COUNT(*) AS pv_count,
                COUNT(DISTINCT session_id) AS uv_count
            FROM page_views
            WHERE created_at >= :cutoff
            GROUP BY DATE(created_at), EXTRACT(HOUR FROM created_at), path, referrer, user_agent, is_bot
        """), {"cutoff": cutoff_dt}).all()

    if not rows:
        db.commit()
        return 0

    # Day-level rollup (hour=-1) — second SQL pass that groups by (day, path,
    # referrer, user_agent, is_bot) WITHOUT hour, so uv_count = distinct
    # sessions for the whole day on a given path. Summing the hourly rows
    # would over-count sessions that hit the same path in multiple hours.
    if is_sqlite:
        day_rows = db.execute(text("""
            SELECT
                DATE(created_at) AS day,
                path,
                COALESCE(referrer, '') AS referrer,
                COALESCE(user_agent, '') AS user_agent,
                COALESCE(is_bot, 0) AS is_bot,
                COUNT(*) AS pv_count,
                COUNT(DISTINCT session_id) AS uv_count
            FROM page_views
            WHERE created_at >= :cutoff
            GROUP BY DATE(created_at), path, referrer, user_agent, is_bot
        """), {"cutoff": cutoff_dt}).all()
    else:
        day_rows = db.execute(text("""
            SELECT
                DATE(created_at) AS day,
                path,
                COALESCE(referrer, '') AS referrer,
                COALESCE(user_agent, '') AS user_agent,
                COALESCE(is_bot, FALSE) AS is_bot,
                COUNT(*) AS pv_count,
                COUNT(DISTINCT session_id) AS uv_count
            FROM page_views
            WHERE created_at >= :cutoff
            GROUP BY DATE(created_at), path, referrer, user_agent, is_bot
        """), {"cutoff": cutoff_dt}).all()

    day_aggregated: dict[tuple, dict] = {}
    for r in day_rows:
        ua = r.user_agent if hasattr(r, "user_agent") else None
        browser = _browser_bucket(ua)
        is_bot = bool(r.is_bot)
        ref_host = _referrer_host(r.referrer)
        key = (r.day, r.path, browser, ref_host, is_bot)
        agg = day_aggregated.get(key)
        if agg is None:
            day_aggregated[key] = {
                "pv_count": int(r.pv_count),
                "uv_count": int(r.uv_count),
            }
        else:
            agg["pv_count"] += int(r.pv_count)
            agg["uv_count"] += int(r.uv_count)

    day_payload = [
        {
            "day": k[0],
            "hour": -1,                       # -1 = day-level rollup
            "path": k[1],
            "browser_bucket": k[2],
            "referrer_host": k[3],
            "is_bot": k[4],
            "pv_count": v["pv_count"],
            "uv_count": v["uv_count"],
            "session_count": v["uv_count"],
            "single_page_session_count": 0,
            "refreshed_at": datetime.utcnow(),
        }
        for k, v in day_aggregated.items()
    ]

    # Bucket browser/referrer per group, then upsert in one shot. Both
    # SQLite and PostgreSQL now expose user_agent and referrer per group,
    # so the bucketing is uniform.
    aggregated: dict[tuple, dict] = {}
    for r in rows:
        ua = r.user_agent if hasattr(r, "user_agent") else None
        browser = _browser_bucket(ua)
        is_bot = bool(r.is_bot)
        ref_host = _referrer_host(r.referrer)
        key = (r.day, int(r.hour) if r.hour is not None else -1, r.path, browser, ref_host, is_bot)
        agg = aggregated.get(key)
        if agg is None:
            aggregated[key] = {
                "pv_count": int(r.pv_count),
                "uv_count": int(r.uv_count),
            }
        else:
            agg["pv_count"] += int(r.pv_count)
            agg["uv_count"] += int(r.uv_count)

    if not aggregated:
        db.commit()
        return 0

    payload = [
        {
            "day": k[0],
            "hour": k[1],
            "path": k[2],
            "browser_bucket": k[3],
            "referrer_host": k[4],
            "is_bot": k[5],
            "pv_count": v["pv_count"],
            "uv_count": v["uv_count"],
            "session_count": v["uv_count"],   # approximation; refined later
            "single_page_session_count": 0,
            "refreshed_at": datetime.utcnow(),
        }
        for k, v in aggregated.items()
    ]

    # Insert in batches — pg_insert with 60k+ rows blows past PostgreSQL's
    # 1664-column-per-tuple limit when the same columns repeat for each row.
    BATCH = 1000
    for start in range(0, len(payload), BATCH):
        chunk = payload[start:start + BATCH]
        if is_sqlite:
            for row in chunk:
                db.execute(text("""
                    INSERT INTO page_view_daily
                        (day, hour, path, browser_bucket, referrer_host, is_bot,
                         pv_count, uv_count, session_count, single_page_session_count, refreshed_at)
                    VALUES
                        (:day, :hour, :path, :browser_bucket, :referrer_host, :is_bot,
                         :pv_count, :uv_count, :session_count, :single_page_session_count, :refreshed_at)
                """), row)
        else:
            stmt = pg_insert(PageViewDaily).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_pv_daily_dims",
                set_={
                    "pv_count": stmt.excluded.pv_count,
                    "uv_count": stmt.excluded.uv_count,
                    "session_count": stmt.excluded.session_count,
                    "refreshed_at": stmt.excluded.refreshed_at,
                },
            )
            db.execute(stmt)

    # Day-level rollup rows (hour=-1) — same insert path; uv_count is distinct
    # sessions for the whole day so it's already correct.
    for start in range(0, len(day_payload), BATCH):
        chunk = day_payload[start:start + BATCH]
        if is_sqlite:
            for row in chunk:
                db.execute(text("""
                    INSERT INTO page_view_daily
                        (day, hour, path, browser_bucket, referrer_host, is_bot,
                         pv_count, uv_count, session_count, single_page_session_count, refreshed_at)
                    VALUES
                        (:day, :hour, :path, :browser_bucket, :referrer_host, :is_bot,
                         :pv_count, :uv_count, :session_count, :single_page_session_count, :refreshed_at)
                """), row)
        else:
            stmt = pg_insert(PageViewDaily).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_pv_daily_dims",
                set_={
                    "pv_count": stmt.excluded.pv_count,
                    "uv_count": stmt.excluded.uv_count,
                    "session_count": stmt.excluded.session_count,
                    "refreshed_at": stmt.excluded.refreshed_at,
                },
            )
            db.execute(stmt)

    db.commit()
    return len(payload) + len(day_payload)


def backfill_page_view_daily(days: int = 14) -> int:
    """One-off entry point: backfill the last ``days`` days, then bump cache."""
    from app.db import session_scope
    from app.services_base import bump_version

    with session_scope() as db:
        n = recompute_page_view_daily(db, days=days)
    bump_version("stats")
    return n


def refresh_stats_cache() -> None:
    """For API/CLI: just invalidate the cached /stats dashboard without recomputing."""
    from app.services_base import bump_version
    bump_version("stats")
