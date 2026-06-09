"""
Re-fetch 2024 management announcements with higher page limit for completeness.
Uses backfill_management_notices with page_limit=100.

Author: AI Assistant (Kimi)
Date: 2026-04-27
"""
from __future__ import annotations

from datetime import date

from app.db import session_scope
from app.notice_pipeline import backfill_management_notices


def main():
    print("=" * 60)
    print("2024 NOTICE BACKFILL (page_limit=100)")
    print("=" * 60)

    with session_scope() as db:
        summary = backfill_management_notices(
            db,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            window_days=30,
            page_limit=100,
        )

    print(f"\nComplete:")
    print(f"  Windows: {summary.window_count}")
    print(f"  Requested: {summary.requested_count}")
    print(f"  Processed: {summary.processed_count}")
    print(f"  Success: {summary.success_count}")
    print(f"  Failed: {summary.failed_count}")
    print(f"  Failed windows: {summary.failed_window_count}")
    print(f"  Published events (total): {summary.published_event_count}")
    print(f"  Pending reviews (total): {summary.pending_review_count}")


if __name__ == "__main__":
    main()
