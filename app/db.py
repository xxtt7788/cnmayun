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


def ensure_schema() -> None:
    with engine.begin() as conn:
        if settings.database_url.startswith("sqlite"):
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(companies)")).fetchall()}
            if "current_ticker" not in columns:
                conn.execute(text("ALTER TABLE companies ADD COLUMN current_ticker VARCHAR(32)"))
        # Ensure ai_usage_logs table exists (PostgreSQL / SQLite both)
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS ai_usage_logs (
                id ''' + ('INTEGER PRIMARY KEY AUTOINCREMENT' if settings.database_url.startswith('sqlite') else 'SERIAL PRIMARY KEY') + ''',
                model_name VARCHAR(64) DEFAULT '',
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                request_source VARCHAR(256),
                success BOOLEAN DEFAULT true,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        conn.execute(text('CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at ON ai_usage_logs(created_at)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS idx_ai_usage_success ON ai_usage_logs(success)'))


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
