from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.bootstrap import count_zero_snapshot_issuers, repair_zero_snapshot_companies
from app.config import settings
from app.db import session_scope
from app.models import Event, ReviewQueue, SourceDocument
from app.notice_pipeline import sync_management_notices


LOG_PATH = settings.data_dir / "overnight_maintenance.log"


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def iter_windows(start: date, end: date, window_days: int) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=window_days - 1), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def current_counts() -> tuple[int, int, int, int]:
    with session_scope() as db:
        published = db.scalar(select(func.count()).select_from(Event).where(Event.event_status == "published")) or 0
        review = db.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.status == "pending")) or 0
        docs = db.scalar(select(func.count()).select_from(SourceDocument)) or 0
        active_zero = count_zero_snapshot_issuers(db, active_only=True)
        return published, review, docs, active_zero


def main() -> None:
    log("夜间维护开始")
    published, review, docs, active_zero = current_counts()
    log(f"初始状态 published={published} review={review} docs={docs} active_zero={active_zero}")

    for round_index in range(1, 5):
        with session_scope() as db:
            result = repair_zero_snapshot_companies(db, limit=40, max_workers=4, active_only=True)
            if not result:
                log(f"零快照修复 round={round_index} 无待处理目标")
                break
            log(
                "零快照修复 "
                f"round={round_index} requested={result.requested_company_count} "
                f"repaired={result.repaired_issuer_count} remaining={result.remaining_zero_snapshot_issuers}"
            )

    windows = []
    windows.extend(iter_windows(date(2026, 4, 1), date(2026, 4, 19), 10))
    windows.extend(iter_windows(date(2025, 7, 1), date(2025, 12, 31), 15))

    for start, end in windows:
        try:
            with session_scope() as db:
                run = sync_management_notices(db, start_date=start, end_date=end, page_limit=6)
                log(
                    "公告回填 "
                    f"{start.isoformat()}~{end.isoformat()} requested={run.requested_count} "
                    f"processed={run.processed_count} success={run.success_count} failed={run.failed_count}"
                )
        except Exception as exc:
            log(f"公告回填失败 {start.isoformat()}~{end.isoformat()} error={exc!r}")

    published, review, docs, active_zero = current_counts()
    log(f"结束状态 published={published} review={review} docs={docs} active_zero={active_zero}")
    log("夜间维护结束")


if __name__ == "__main__":
    main()
