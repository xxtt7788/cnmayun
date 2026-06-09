"""
Auto-review all pending ReviewQueue items by re-running the auto-review pipeline.

Strategy:
  Loop through all pending review items, re-process each source document
  with the latest auto-review rules, publish if auto-approved, resolve if
  auto-rejected, leave pending if still needs manual review.

Author: AI Assistant (Kimi)
Date: 2026-04-27
"""
from __future__ import annotations

import time

from app.db import session_scope
from app.models import ReviewQueue
from app.notice_pipeline import reprocess_pending_review_documents
from sqlalchemy import func, select


def main():
    batch_size = 100
    total_processed = 0
    total_created = 0
    total_review = 0
    round_num = 0

    print("=" * 60)
    print("AUTO REVIEW PENDING QUEUE")
    print(f"Batch size: {batch_size}")
    print("=" * 60)

    while True:
        with session_scope() as db:
            pending_count = db.scalar(
                select(func.count(ReviewQueue.id))
                .where(ReviewQueue.status == "pending", ReviewQueue.source_document_id.is_not(None))
            ) or 0

        if pending_count == 0:
            print("\nNo more pending review items.")
            break

        round_num += 1
        print(f"\nRound {round_num}: {pending_count} pending items remaining")

        start = time.time()
        with session_scope() as db:
            processed, created, review = reprocess_pending_review_documents(db, limit=batch_size)

        elapsed = time.time() - start
        total_processed += processed
        total_created += created
        total_review += review

        print(f"  Processed: {processed} | Created events: {created} | New reviews: {review} | Time: {elapsed:.1f}s")

        # Safety break: if no progress, stop
        if processed == 0:
            print("\nNo progress made in this round. Stopping.")
            break

    print("\n" + "=" * 60)
    print("AUTO REVIEW COMPLETE")
    print(f"  Total rounds: {round_num}")
    print(f"  Total processed: {total_processed}")
    print(f"  Total events created: {total_created}")
    print(f"  Total new reviews: {total_review}")
    print("=" * 60)


if __name__ == "__main__":
    main()
