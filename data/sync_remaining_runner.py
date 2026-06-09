from datetime import datetime
from sqlalchemy import select, func

from app.bootstrap import sync_company_baseline
from app.db import session_scope
from app.models import Company

BATCH_SIZE = 100
MAX_WORKERS = 12
SLEEP_SECONDS = 3


def count_status(db):
    synced = db.scalar(select(func.count()).select_from(Company).where(Company.baseline_status == 'synced')) or 0
    pending = db.scalar(select(func.count()).select_from(Company).where(Company.is_active.is_(True), Company.baseline_status == 'pending')) or 0
    failed = db.scalar(select(func.count()).select_from(Company).where(Company.is_active.is_(True), Company.baseline_status == 'failed')) or 0
    return synced, pending, failed

print(f'[{datetime.now().isoformat()}] remaining sync runner started batch_size={BATCH_SIZE} workers={MAX_WORKERS}', flush=True)

while True:
    with session_scope() as db:
        tickers = db.scalars(
            select(Company.ticker)
            .where(Company.is_active.is_(True), Company.baseline_status == 'pending')
            .order_by(Company.ticker)
            .limit(BATCH_SIZE)
        ).all()
    if not tickers:
        with session_scope() as db:
            synced, pending, failed = count_status(db)
        print(f'[{datetime.now().isoformat()}] no pending companies left synced={synced} pending={pending} failed={failed}', flush=True)
        break

    with session_scope() as db:
        run = sync_company_baseline(db, tickers=tickers, max_workers=MAX_WORKERS)
        synced, pending, failed = count_status(db)
        print(
            f'[{datetime.now().isoformat()}] run_id={run.id} requested={run.requested_company_count} '
            f'success={run.success_company_count} failed_batch={run.failed_company_count} '
            f'total_synced={synced} total_pending={pending} total_failed={failed}',
            flush=True,
        )
        if run.notes:
            first_line = run.notes.splitlines()[0]
            print(f'[{datetime.now().isoformat()}] note={first_line[:500]}', flush=True)

    import time
    time.sleep(SLEEP_SECONDS)
