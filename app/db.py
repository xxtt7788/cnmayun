from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False, "timeout": 60} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _get_existing_columns(conn, table_name: str) -> set[str]:
    """Return the set of column names that exist on ``table_name``.

    Portable across SQLite (PRAGMA) and PostgreSQL (information_schema).
    """
    is_sqlite = settings.database_url.startswith("sqlite")
    if is_sqlite:
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return {row[1] for row in rows}  # PRAGMA: (cid, name, type, ...)
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
    ), {"t": table_name}).fetchall()
    return {row[0] for row in rows}  # information_schema: (column_name, ...)


def _run_ddl(ddl: str, *, log_label: str = "") -> None:
    """Execute a single DDL statement in its own short transaction.

    For PostgreSQL CREATE INDEX we rewrite to CONCURRENTLY where possible so
    that the index build does not take a SHARE LOCK on the target table
    (which would block concurrent INSERT/DELETE/UPDATE and could deadlock
    with background workers like ``sync-notices``). CREATE INDEX CONCURRENTLY
    cannot run inside a transaction block, so each statement gets its own
    short-lived connection.

    For SQLite, CONCURRENTLY is not supported; the statement runs in a
    one-statement transaction.
    """
    is_sqlite = settings.database_url.startswith("sqlite")
    import logging
    log = logging.getLogger(__name__)

    # Rewrite CREATE INDEX IF NOT EXISTS → CREATE INDEX CONCURRENTLY IF NOT EXISTS on Postgres
    if (
        not is_sqlite
        and ddl.strip().upper().startswith("CREATE INDEX")
        and "CONCURRENTLY" not in ddl.upper()
    ):
        ddl = ddl.replace("CREATE INDEX", "CREATE INDEX CONCURRENTLY", 1)

    try:
        if is_sqlite:
            with engine.begin() as conn:
                conn.execute(text(ddl))
        else:
            # Postgres CONCURRENTLY: must be outside a transaction
            with engine.connect() as conn:
                conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text(ddl))
        if log_label:
            log.info("ensure_schema: %s OK", log_label)
    except Exception as exc:  # noqa: BLE001 — DDL failures must not crash startup
        log.warning("ensure_schema: %s failed: %s | %s", log_label, ddl, exc)


def ensure_schema() -> None:
    """Apply idempotent schema migrations. Safe to call on every startup.

    Each DDL runs in its own short transaction (PostgreSQL CONCURRENTLY where
    applicable) so a single slow index build can never block other writers
    or deadlock with background workers.
    """
    is_sqlite = settings.database_url.startswith("sqlite")

    # --- 1. Pre-existing company column add (SQLite only path) ---
    if is_sqlite:
        with engine.begin() as conn:
            cols = _get_existing_columns(conn, "companies")
            if "current_ticker" not in cols:
                conn.execute(text("ALTER TABLE companies ADD COLUMN current_ticker VARCHAR(32)"))

    # --- 2. ai_usage_logs table + its two pre-existing indexes ---
    _run_ddl('''
        CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id ''' + ('INTEGER PRIMARY KEY AUTOINCREMENT' if is_sqlite else 'SERIAL PRIMARY KEY') + ''',
            model_name VARCHAR(64) DEFAULT '',
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            request_source VARCHAR(256),
            success BOOLEAN DEFAULT true,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''', log_label="ai_usage_logs table")
    _run_ddl('CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at ON ai_usage_logs(created_at)',
             log_label="idx_ai_usage_created_at")
    _run_ddl('CREATE INDEX IF NOT EXISTS idx_ai_usage_success ON ai_usage_logs(success)',
             log_label="idx_ai_usage_success")

    # --- 3. Performance indexes (added 2026-06-09) — each in its own tx ---
    for label, ddl in [
        ("idx_page_views_created_at",         "CREATE INDEX IF NOT EXISTS idx_page_views_created_at ON page_views (created_at)"),
        ("idx_page_views_path",               "CREATE INDEX IF NOT EXISTS idx_page_views_path       ON page_views (path)"),
        ("idx_review_queue_status_created",   "CREATE INDEX IF NOT EXISTS idx_review_queue_status_created ON review_queue (status, created_at DESC)"),
        ("idx_events_status_ann_date",        "CREATE INDEX IF NOT EXISTS idx_events_status_ann_date  ON events (event_status, announcement_date DESC)"),
        ("idx_events_company_status",         "CREATE INDEX IF NOT EXISTS idx_events_company_status    ON events (company_id, event_status)"),
        ("idx_events_status_published",       "CREATE INDEX IF NOT EXISTS idx_events_status_published  ON events (event_status, published_at DESC)"),
        ("idx_companies_baseline_status",     "CREATE INDEX IF NOT EXISTS idx_companies_baseline_status ON companies (baseline_status)"),
        ("idx_companies_active_baseline",     "CREATE INDEX IF NOT EXISTS idx_companies_active_baseline ON companies (is_active, baseline_status)"),
        ("idx_alerts_status_created",         "CREATE INDEX IF NOT EXISTS idx_alerts_status_created    ON alerts (status, created_at DESC)"),
        ("idx_exec_snap_company_role",        "CREATE INDEX IF NOT EXISTS idx_exec_snap_company_role   ON executive_snapshots (company_id, role_canonical)"),
    ]:
        _run_ddl(ddl, log_label=label)

    # --- 4. page_views.is_bot column + partial index for fast /stats filter ---
    with engine.begin() as conn:
        cols = _get_existing_columns(conn, "page_views")
        if "is_bot" not in cols:
            # ADD COLUMN on Postgres is metadata-only (no rewrite) for nullable booleans.
            conn.execute(text("ALTER TABLE page_views ADD COLUMN is_bot BOOLEAN"))
    _run_ddl(
        "CREATE INDEX IF NOT EXISTS idx_page_views_is_bot_partial "
        "ON page_views (created_at) WHERE is_bot = FALSE",
        log_label="idx_page_views_is_bot_partial",
    )

    # --- 5. PageViewDaily aggregate table (mirrors CompanyMetricDaily) ---
    _run_ddl('''
        CREATE TABLE IF NOT EXISTS page_view_daily (
            id ''' + ('INTEGER PRIMARY KEY AUTOINCREMENT' if is_sqlite else 'SERIAL PRIMARY KEY') + ''',
            day DATE NOT NULL,
            hour INTEGER DEFAULT -1,
            path VARCHAR(256) NOT NULL,
            browser_bucket VARCHAR(16) NOT NULL,
            referrer_host VARCHAR(256),
            is_bot BOOLEAN NOT NULL DEFAULT FALSE,
            pv_count INTEGER DEFAULT 0,
            uv_count INTEGER DEFAULT 0,
            session_count INTEGER DEFAULT 0,
            single_page_session_count INTEGER DEFAULT 0,
            refreshed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''', log_label="page_view_daily table")
    _run_ddl(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_pv_daily_dims "
        "ON page_view_daily (day, hour, path, browser_bucket, referrer_host, is_bot)",
        log_label="uq_pv_daily_dims",
    )
    _run_ddl("CREATE INDEX IF NOT EXISTS idx_pv_daily_day_bot  ON page_view_daily (day, is_bot)",
             log_label="idx_pv_daily_day_bot")
    _run_ddl("CREATE INDEX IF NOT EXISTS idx_pv_daily_day_path ON page_view_daily (day, path)",
             log_label="idx_pv_daily_day_path")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
