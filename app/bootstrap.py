from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.cninfo import (
    StockListEntry,
    build_company_source_url,
    fetch_company_executives,
    fetch_company_introduction,
    fetch_stock_universe,
    infer_exchange,
    normalize_market_segment,
    resolve_bse_current_ticker,
)
from app.models import BaselineRun, Company, ExecutiveSnapshot, Person, RoleTenure
from app.normalization import extract_canonical_roles, is_core_role, role_priority


@dataclass(slots=True)
class ZeroSnapshotRepairResult:
    requested_company_count: int
    requested_issuer_count: int
    repaired_issuer_count: int
    remaining_zero_snapshot_issuers: int
    run: BaselineRun


def ensure_company_universe(db: Session) -> int:
    entries = fetch_stock_universe()
    for entry in entries:
        upsert_company_from_stock_entry(db, entry)
    db.flush()
    return db.scalar(select(func.count()).select_from(Company)) or len(entries)


def _is_current_listing_candidate(entry: StockListEntry) -> bool:
    short_name = entry.short_name or ""
    if "退" in short_name or short_name.upper().startswith("PT"):
        return False
    return True


def upsert_company_from_stock_entry(db: Session, entry: StockListEntry) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == entry.code))
    if not company and entry.org_id:
        company = db.scalar(select(Company).where(Company.org_id == entry.org_id))
    is_current_candidate = _is_current_listing_candidate(entry)
    if not company:
        company = Company(
            exchange=infer_exchange(entry.code),
            ticker=entry.code,
            current_ticker=entry.code if entry.code.startswith("920") else None,
            company_name=entry.short_name,
            short_name=entry.short_name,
            org_id=entry.org_id,
            market_segment=normalize_market_segment(entry.code),
            is_active=is_current_candidate,
            source_url=build_company_source_url(entry.code, entry.org_id),
        )
        db.add(company)
        db.flush()
        return company

    if company.ticker != entry.code:
        if company.ticker.startswith("920") and not entry.code.startswith("920") and not company.current_ticker:
            company.current_ticker = company.ticker
        company.ticker = entry.code
    company.short_name = entry.short_name
    company.company_name = company.company_name or entry.short_name
    if entry.code.startswith("920"):
        company.current_ticker = entry.code
    company.org_id = entry.org_id
    company.exchange = infer_exchange(entry.code)
    company.market_segment = company.market_segment or normalize_market_segment(entry.code)
    company.source_url = build_company_source_url(entry.code, entry.org_id)
    company.is_active = is_current_candidate
    return company


def _parse_birth_year(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 4:
        return int(digits[:4])
    return None


def _upsert_person(db: Session, row: dict) -> Person:
    external_person_id = row.get("F001V")
    person = None
    if external_person_id:
        person = db.scalar(select(Person).where(Person.external_person_id == external_person_id))
    if not person:
        person = Person(
            canonical_name=row.get("F002V") or "未知人物",
            external_person_id=external_person_id,
        )
        db.add(person)
        db.flush()

    person.canonical_name = row.get("F002V") or person.canonical_name
    person.gender = row.get("F010V") or person.gender
    person.birth_year = _parse_birth_year(row.get("F012V")) or person.birth_year
    person.education = row.get("F017V") or person.education
    return person


def _mark_company_sync_failed(db: Session, company_id: int) -> None:
    company = db.get(Company, company_id)
    if company:
        company.baseline_status = "failed"
        company.baseline_last_synced_at = datetime.utcnow()


def _mark_company_synced_minimal(company: Company) -> None:
    company.baseline_status = "synced"
    company.baseline_last_synced_at = datetime.utcnow()
    company.source_url = build_company_source_url(company.current_ticker or company.ticker, company.org_id)


def _resolve_sync_ticker(company: Company) -> str:
    if company.current_ticker:
        return company.current_ticker
    if company.exchange == "BSE" and not company.ticker.startswith("920"):
        current_ticker = resolve_bse_current_ticker(company.ticker)
        if current_ticker:
            return current_ticker
    return company.ticker


def _ensure_intro_fallback_snapshot(
    db: Session,
    *,
    company: Company,
    run_id: int | None,
    snapshot_date: date,
) -> bool:
    existing_snapshot_count = db.scalar(
        select(func.count()).select_from(ExecutiveSnapshot).where(ExecutiveSnapshot.company_id == company.id)
    ) or 0
    if existing_snapshot_count > 0 or not company.general_manager_name:
        return False

    person = db.scalar(select(Person).where(Person.canonical_name == company.general_manager_name))
    if not person:
        person = Person(canonical_name=company.general_manager_name)
        db.add(person)
        db.flush()

    db.add(
        ExecutiveSnapshot(
            company_id=company.id,
            person_id=person.id,
            baseline_run_id=run_id,
            snapshot_date=snapshot_date,
            source_platform="CNINFO",
            source_api="/data20/companyOverview/getCompanyIntroduction",
            source_url=company.source_url or build_company_source_url(company.current_ticker or company.ticker, company.org_id),
            human_id="intro-general-manager",
            person_name_raw=person.canonical_name,
            title_raw="总经理(公司概况回填)",
            role_canonical="ceo_equivalent",
            role_priority=role_priority("ceo_equivalent"),
            compensation=None,
            gender=person.gender,
            birth_year=person.birth_year,
            education=person.education,
            is_core_role=True,
            confidence=Decimal("0.7200"),
        )
    )
    db.add(
        RoleTenure(
            company_id=company.id,
            person_id=person.id,
            role_canonical="ceo_equivalent",
            role_raw_latest="总经理(公司概况回填)",
            start_date=None,
            end_date=None,
            is_active=True,
            inferred_flag=True,
            confidence=Decimal("0.7200"),
        )
    )
    return True


def _apply_company_payload(
    db: Session,
    company_id: int,
    sync_ticker: str,
    intro_payload: dict,
    executives_payload: dict,
    run_id: int | None,
    snapshot_date: date,
) -> None:
    company = db.get(Company, company_id)
    if not company:
        return

    intro_records = intro_payload.get("data", {}).get("records", [])
    if intro_records is None:
        intro_records = []
    basic_info = {}
    listing_info = {}
    if intro_records:
        basic_information = intro_records[0].get("basicInformation") or [{}]
        listing_information = intro_records[0].get("listingInformation") or [{}]
        basic_info = basic_information[0] if basic_information else {}
        listing_info = listing_information[0] if listing_information else {}

    company.company_name = basic_info.get("ORGNAME") or company.company_name
    company.short_name = basic_info.get("ASECNAME") or company.short_name
    company.company_name_en = basic_info.get("F001V") or company.company_name_en
    company.industry_l1 = basic_info.get("F032V") or company.industry_l1
    company.market_segment = basic_info.get("MARKET") or company.market_segment
    website = basic_info.get("F011V") or company.website
    if website and not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    company.website = website
    company.legal_representative = basic_info.get("F003V") or company.legal_representative
    company.general_manager_name = basic_info.get("F042V") or basic_info.get("F018V") or company.general_manager_name
    company.office_address = basic_info.get("F004V") or company.office_address
    company.registered_address = basic_info.get("F005V") or company.registered_address
    company.business_scope = basic_info.get("F016V") or company.business_scope
    _mark_company_synced_minimal(company)
    listed_date = basic_info.get("F006D")
    if listed_date:
        company.listed_date = date.fromisoformat(listed_date)
    if listing_info.get("SECCODE"):
        resolved_sec_code = listing_info["SECCODE"]
        if resolved_sec_code != company.ticker:
            company.current_ticker = resolved_sec_code
    elif sync_ticker != company.ticker:
        company.current_ticker = sync_ticker

    records = executives_payload.get("data", {}).get("records") or []
    if not records:
        _ensure_intro_fallback_snapshot(db, company=company, run_id=run_id, snapshot_date=snapshot_date)
        return

    db.execute(delete(ExecutiveSnapshot).where(ExecutiveSnapshot.company_id == company.id))
    db.execute(
        delete(RoleTenure).where(
            RoleTenure.company_id == company.id,
            RoleTenure.inferred_flag.is_(True),
        )
    )

    for row in records:
        person = _upsert_person(db, row)
        title_raw = row.get("F009V") or ""
        canonical_roles = extract_canonical_roles(title_raw)
        if not canonical_roles:
            continue
        for canonical_role in canonical_roles:
            db.add(
                ExecutiveSnapshot(
                    company_id=company.id,
                    person_id=person.id,
                    baseline_run_id=run_id,
                    snapshot_date=snapshot_date,
                    source_platform="CNINFO",
                    source_api="/data20/companyOverview/getCompanyExecutives",
                    source_url=company.source_url or build_company_source_url(company.ticker, company.org_id),
                    human_id=row.get("F001V"),
                    person_name_raw=person.canonical_name,
                    title_raw=title_raw,
                    role_canonical=canonical_role,
                    role_priority=role_priority(canonical_role),
                    compensation=row.get("F012N"),
                    gender=row.get("F010V"),
                    birth_year=_parse_birth_year(row.get("F012V")),
                    education=row.get("F017V"),
                    is_core_role=is_core_role(canonical_role),
                    confidence=Decimal("1.0000"),
                )
            )
            db.add(
                RoleTenure(
                    company_id=company.id,
                    person_id=person.id,
                    role_canonical=canonical_role,
                    role_raw_latest=title_raw,
                    start_date=None,
                    end_date=None,
                    is_active=True,
                    inferred_flag=True,
                    confidence=Decimal("1.0000"),
                )
            )


def _fetch_company_payload(company: Company) -> tuple[int, str, dict, dict, list[str]]:
    errors: list[str] = []
    intro_payload: dict = {}
    executives_payload: dict = {"data": {"records": []}}
    sync_ticker = _resolve_sync_ticker(company)

    try:
        intro_payload = fetch_company_introduction(sync_ticker)
    except Exception as exc:
        errors.append(f"intro:{exc}")

    try:
        executives_payload = fetch_company_executives(sync_ticker)
    except Exception as exc:
        errors.append(f"exec:{exc}")

    return company.id, sync_ticker, intro_payload, executives_payload, errors


def sync_company_baseline(
    db: Session,
    limit: int | None = None,
    tickers: Iterable[str] | None = None,
    max_workers: int = 6,
) -> BaselineRun:
    query = select(Company).order_by(Company.baseline_last_synced_at.is_not(None), Company.ticker)
    if tickers:
        query = query.where(Company.ticker.in_(list(tickers)))
    else:
        query = query.where(Company.baseline_status != "synced")
    companies = list(db.scalars(query).all())
    if limit is not None:
        companies = companies[:limit]

    archival_companies = [company for company in companies if not company.is_active]
    remote_companies = [company for company in companies if company.is_active]

    run = BaselineRun(
        run_type="current_executive_baseline",
        source_platform="CNINFO",
        status="running",
        requested_company_count=len(companies),
    )
    db.add(run)
    db.flush()

    snapshot_date = date.today()
    for company in archival_companies:
        _mark_company_synced_minimal(company)
        run.processed_company_count += 1
        run.success_company_count += 1
    db.flush()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_company_payload, company): company for company in remote_companies}
        for future in as_completed(future_map):
            company = future_map[future]
            run.processed_company_count += 1
            try:
                _, sync_ticker, intro_payload, executives_payload, errors = future.result()
                _apply_company_payload(db, company.id, sync_ticker, intro_payload, executives_payload, run.id, snapshot_date)
                run.success_company_count += 1
                if errors:
                    run.notes = f"{run.notes or ''}\n{company.ticker}=>{sync_ticker}: {'; '.join(errors)}".strip()
            except Exception as exc:
                run.failed_company_count += 1
                _mark_company_sync_failed(db, company.id)
                run.notes = f"{run.notes or ''}\n{company.ticker}: {exc}".strip()
            db.flush()

    run.status = "completed" if run.failed_company_count == 0 else "completed_with_errors"
    run.completed_at = datetime.utcnow()
    return run


def list_unsynced_tickers(db: Session, limit: int) -> list[str]:
    query = (
        select(Company.ticker)
        .where(Company.baseline_status != "synced")
        .order_by(Company.baseline_last_synced_at.is_not(None), Company.ticker)
        .limit(limit)
    )
    return list(db.scalars(query))


def count_unsynced_companies(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Company).where(Company.baseline_status != "synced")) or 0


def count_zero_snapshot_issuers(db: Session, *, active_only: bool = False) -> int:
    snapshot_company_ids = set(db.scalars(select(ExecutiveSnapshot.company_id).distinct()).all())
    companies = db.scalars(select(Company)).all()
    issuers: dict[str, dict[str, bool]] = {}
    for company in companies:
        issuer_key = company.org_id or company.ticker
        state = issuers.setdefault(issuer_key, {"has_snapshot": False, "is_active": False})
        state["has_snapshot"] = state["has_snapshot"] or company.id in snapshot_company_ids
        state["is_active"] = state["is_active"] or bool(company.is_active)
    return sum(1 for state in issuers.values() if not state["has_snapshot"] and (state["is_active"] or not active_only))


def list_zero_snapshot_tickers(db: Session, limit: int | None = None, *, active_only: bool = True) -> list[str]:
    snapshot_company_ids = set(db.scalars(select(ExecutiveSnapshot.company_id).distinct()).all())
    companies = db.scalars(
        select(Company).order_by(
            Company.is_active.desc(),
            Company.current_ticker.is_not(None).desc(),
            Company.baseline_last_synced_at.is_(None).desc(),
            Company.baseline_last_synced_at,
            Company.ticker,
        )
    ).all()
    issuers: dict[str, dict[str, object]] = {}
    for company in companies:
        issuer_key = company.org_id or company.ticker
        state = issuers.setdefault(issuer_key, {"has_snapshot": False, "companies": []})
        state["has_snapshot"] = bool(state["has_snapshot"]) or company.id in snapshot_company_ids
        state["companies"].append(company)

    targets: list[str] = []
    for state in issuers.values():
        issuer_companies: list[Company] = state["companies"]  # type: ignore[assignment]
        if state["has_snapshot"]:
            continue
        if active_only and not any(company.is_active for company in issuer_companies):
            continue
        preferred = sorted(
            issuer_companies,
            key=lambda company: (
                0 if company.is_active else 1,
                0 if company.current_ticker else 1,
                0 if company.exchange == "BSE" else 1,
                company.ticker,
            ),
        )[0]
        targets.append(preferred.ticker)
    if limit is not None:
        return targets[:limit]
    return targets


def repair_zero_snapshot_companies(
    db: Session,
    *,
    limit: int | None = None,
    max_workers: int = 6,
    active_only: bool = True,
) -> ZeroSnapshotRepairResult | None:
    before_zero = count_zero_snapshot_issuers(db, active_only=active_only)
    tickers = list_zero_snapshot_tickers(db, limit=limit, active_only=active_only)
    if not tickers:
        return None
    run = sync_company_baseline(db, tickers=tickers, max_workers=max_workers)
    after_zero = count_zero_snapshot_issuers(db, active_only=active_only)
    return ZeroSnapshotRepairResult(
        requested_company_count=len(tickers),
        requested_issuer_count=len(tickers),
        repaired_issuer_count=max(before_zero - after_zero, 0),
        remaining_zero_snapshot_issuers=after_zero,
        run=run,
    )
