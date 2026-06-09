"""
Fetch historical management notices year by year from cninfo.

Strategy:
  Starting from 2024, go backwards year by year.
  For each year, use backfill_management_notices with 30-day windows.
  Increase page_limit for historical data to ensure completeness.

Author: AI Assistant (Kimi)
Date: 2026-04-25
"""
from __future__ import annotations

import sys
from datetime import date

from app.db import session_scope
from app.notice_pipeline import backfill_management_notices


def fetch_year(year: int, page_limit: int = 50) -> dict:
    """Fetch all management notices for a given year."""
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    print(f"\n{'='*60}")
    print(f"Fetching year {year}: {start_date} ~ {end_date}")
    print(f"Page limit per keyword per window: {page_limit}")
    print(f"{'='*60}")

    with session_scope() as db:
        summary = backfill_management_notices(
            db,
            start_date=start_date,
            end_date=end_date,
            window_days=30,
            page_limit=page_limit,
        )

    result = {
        "year": year,
        "windows": summary.window_count,
        "requested": summary.requested_count,
        "processed": summary.processed_count,
        "success": summary.success_count,
        "failed": summary.failed_count,
        "failed_windows": summary.failed_window_count,
        "published_events": summary.published_event_count,
        "pending_reviews": summary.pending_review_count,
    }

    print(f"\nYear {year} complete:")
    print(f"  Windows: {result['windows']}")
    print(f"  Requested: {result['requested']}")
    print(f"  Processed: {result['processed']}")
    print(f"  Success: {result['success']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Failed windows: {result['failed_windows']}")
    print(f"  Published events (total): {result['published_events']}")
    print(f"  Pending reviews (total): {result['pending_reviews']}")

    return result


def main():
    # Define years to fetch: 2024, then backwards
    # Start with 2024 since it's partially filled, then 2023, 2022, ...
    years = [2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015]
    page_limit = 50  # Increase for historical completeness

    print("=" * 60)
    print("HISTORICAL NOTICE FETCH")
    print(f"Years: {years}")
    print(f"Page limit: {page_limit}")
    print("=" * 60)

    results = []
    for year in years:
        try:
            result = fetch_year(year, page_limit=page_limit)
            results.append(result)
        except KeyboardInterrupt:
            print("\nInterrupted by user. Stopping.")
            break
        except Exception as e:
            print(f"\nERROR fetching year {year}: {e}")
            results.append({"year": year, "error": str(e)})

    # Summary
    print("\n" + "=" * 60)
    print("OVERALL SUMMARY")
    print("=" * 60)
    total_requested = sum(r.get("requested", 0) for r in results)
    total_success = sum(r.get("success", 0) for r in results)
    total_failed = sum(r.get("failed", 0) for r in results)
    print(f"Total requested: {total_requested}")
    print(f"Total success: {total_success}")
    print(f"Total failed: {total_failed}")
    print("\nBy year:")
    for r in results:
        yr = r.get("year", "?")
        if "error" in r:
            print(f"  {yr}: ERROR - {r['error']}")
        else:
            print(f"  {yr}: requested={r.get('requested',0)} success={r.get('success',0)} failed={r.get('failed',0)}")


if __name__ == "__main__":
    main()
