"""Propagate published events to the denormalized role_tenures table.

Background
----------
The ``events`` table records raw personnel changes (appointment,
non_renewal, continuation, etc.) extracted from announcements. The
``role_tenures`` table is the denormalized "current positions" cache
that powers ``/people``, ``/companies``, ``/feed``, and the leadership
displays. The events→role_tenures propagation was previously missing
(2026-06-13 audit), causing stale displays (e.g., 王宏向 was extracted
as a non_renewal chairperson but role_tenures still showed him active on
``/people/35627``).

This module:
- ``apply_event_to_tenures``: per-event propagation; safe to call from
  any path that creates or updates an ``Event`` row.
- ``backfill_role_tenures``: re-derive role_tenures for ALL published
  events (one-shot recovery script; see
  ``scripts/backfill_role_tenures_from_events.py``).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Event, RoleTenure


# Event types that close the currently-active tenure for the (person,
# company, role) tuple.
CLOSE_EVENT_TYPES: frozenset[str] = frozenset({
    "non_renewal",
    "removal",
    "resignation",
    "retirement",
})

# Event types that open a new active tenure OR keep the existing one.
OPEN_EVENT_TYPES: frozenset[str] = frozenset({
    "appointment",
    "reelection",
    "continuation",
})

# Event types that should NOT touch role_tenures (yet):
# - nomination: pending shareholder vote; don't pre-commit the role
# - interim_assignment: temporary; doesn't represent a stable position
# - title_change: TODO; would need close-old + open-new logic
DEFER_EVENT_TYPES: frozenset[str] = frozenset({
    "nomination",
    "interim_assignment",
    "title_change",
})


def apply_event_to_tenures(db: Session, event: Event) -> int:
    """Update ``role_tenures`` based on a single event.

    Returns the number of ``role_tenures`` rows affected (inserted,
    updated, or closed). 0 means no-op (e.g., defer event type, missing
    person_id/company_id, or event not yet published).

    Idempotent: running it twice on the same event is a no-op the second
    time (the active tenure is already in the right state).
    """
    if event.event_status != "published":
        return 0
    if not event.person_id or not event.company_id:
        return 0

    event_date = event.effective_date or event.announcement_date or _today()

    if event.event_type in CLOSE_EVENT_TYPES:
        return _close_active_tenure(db, event, event_date)
    if event.event_type in OPEN_EVENT_TYPES:
        return _open_or_keep_tenure(db, event, event_date)
    return 0


def backfill_role_tenures(db: Session, *, dry_run: bool = False) -> dict:
    """Re-derive role_tenures from ALL published events.

    Designed for a one-shot recovery. Iterates events in chronological
    order, applying each one. Existing role_tenures rows that are
    bootstrap-inferred (``inferred_flag=True``) will be closed or
    updated as the event stream dictates.

    Returns a stats dict with counts. Use ``dry_run=True`` to see what
    would change without modifying the DB.
    """
    events = list(db.scalars(
        select(Event)
        .where(
            Event.event_status == "published",
            Event.person_id.is_not(None),
            Event.company_id.is_not(None),
        )
        .order_by(Event.announcement_date.asc().nullslast(), Event.effective_date.asc().nullslast(), Event.id.asc())
    ))
    stats = {
        "events_processed": 0,
        "events_skipped": 0,
        "rows_closed": 0,
        "rows_opened": 0,
        "rows_kept": 0,
    }
    for ev in events:
        affected = apply_event_to_tenures(db, ev)
        if affected:
            stats["events_processed"] += 1
            if ev.event_type in CLOSE_EVENT_TYPES:
                stats["rows_closed"] += affected
            elif ev.event_type in OPEN_EVENT_TYPES:
                # Distinguish open vs keep by checking state before/after;
                # for simplicity, count both as "opened/kept".
                stats["rows_opened"] += affected
        else:
            stats["events_skipped"] += 1
    if not dry_run:
        db.commit()
    else:
        db.rollback()
    return stats


def _close_active_tenure(db: Session, event: Event, end_date: date) -> int:
    """Close the active tenure for this (person, company, role) tuple."""
    result = db.execute(
        update(RoleTenure)
        .where(
            RoleTenure.person_id == event.person_id,
            RoleTenure.company_id == event.company_id,
            RoleTenure.role_canonical == event.role_canonical,
            RoleTenure.is_active.is_(True),
        )
        .values(
            end_date=end_date,
            is_active=False,
            role_raw_latest=event.role_raw,
            confidence=max(_tenure_confidence(event.confidence), 0.0),
        )
    )
    return result.rowcount or 0


def _open_or_keep_tenure(db: Session, event: Event, start_date: date) -> int:
    """Open a new active tenure, or update the existing one in place."""
    existing = db.scalar(select(RoleTenure).where(
        RoleTenure.person_id == event.person_id,
        RoleTenure.company_id == event.company_id,
        RoleTenure.role_canonical == event.role_canonical,
        RoleTenure.is_active.is_(True),
    ))
    if existing is None:
        db.add(RoleTenure(
            person_id=event.person_id,
            company_id=event.company_id,
            role_canonical=event.role_canonical,
            role_raw_latest=event.role_raw,
            start_date=start_date,
            end_date=None,
            is_active=True,
            inferred_flag=False,  # derived from a real event
            confidence=event.confidence,
        ))
        return 1
    # Existing active tenure: keep it, but refresh raw + confidence.
    existing.role_raw_latest = event.role_raw
    if existing.start_date is None:
        existing.start_date = start_date
    existing.confidence = max(existing.confidence or 0, event.confidence or 0)
    return 1


def _tenure_confidence(c: float | None) -> float:
    """Defensive coercion for the role_tenures.confidence column type."""
    return float(c) if c is not None else 0.0


def _today() -> date:
    return datetime.utcnow().date()
