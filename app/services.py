from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import case, desc, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import (
    Alert,
    AIUsageLog,
    BaselineRun,
    Company,
    CompanyMetricDaily,
    DocumentProcessingRun,
    Event,
    ExecutiveSnapshot,
    Person,
    ReviewQueue,
    RoleTenure,
    PersonProfile,
    SourceDocument,
    SyncJob,
    Watchlist,
)
from app.normalization import event_type_label, extract_review_hints_from_text, role_label
from app.project_memory import load_project_memory
from app.schemas import (
    AlertOut,
    BaselineRunOut,
    BaselineSummaryOut,
    CompanyDetailOut,
    CompanyListItemOut,
    CompanyMetricOut,
    CompanySearchOut,
    CompanyTenureOut,
    CoverageBucketOut,
    CoverageDashboardOut,
    EventOut,
    ExecutiveSnapshotOut,
    FeedQueryOut,
    LaunchReadinessOut,
    OverviewOut,
    PersonDetailOut,
    PersonListItemOut,
    PersonProfileOut,
    PersonSearchOut,
    PersonTenureOut,
    ProjectMemoryOut,
    ReviewQueueItemOut,
    ReviewExtractionHintOut,
    RoleCoverageItemOut,
    RuntimeCheckOut,
    RuntimePreflightOut,
    StatusBreakdownItemOut,
    SyncJobOut,
    WatchlistOut,
)


def _event_to_out(event: Event) -> EventOut:
    return EventOut(
        id=event.id,
        company_name=event.company.short_name or event.company.company_name,
        company_ticker=event.company.current_ticker or event.company.ticker,
        person_id=event.person.id if event.person else None,
        person_name=event.person.canonical_name if event.person else None,
        role_canonical=role_label(event.role_canonical),
        event_type=event_type_label(event.event_type),
        event_status=event.event_status,
        event_reason_raw=event.event_reason_raw,
        announcement_date=event.announcement_date,
        effective_date=event.effective_date,
        confidence=float(event.confidence),
        excerpt=event.excerpt,
        source_url=event.source_document.source_url,
        created_at=event.created_at,
        published_at=event.published_at,
    )


def _metric_to_out(metric: CompanyMetricDaily) -> CompanyMetricOut:
    return CompanyMetricOut(
        metric_date=metric.metric_date,
        change_count_30d=metric.change_count_30d,
        change_count_90d=metric.change_count_90d,
        mom_change_rate=float(metric.mom_change_rate) if metric.mom_change_rate is not None else None,
        yoy_change_rate=float(metric.yoy_change_rate) if metric.yoy_change_rate is not None else None,
        stability_score=float(metric.stability_score) if metric.stability_score is not None else None,
        abnormal_turnover_flag=metric.abnormal_turnover_flag,
    )


def _compact_text(value: str | None, max_chars: int = 160) -> str | None:
    if not value:
        return None
    compacted = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if not compacted:
        return None
    return compacted if len(compacted) <= max_chars else f"{compacted[:max_chars].rstrip()}..."


def _profile_to_out(profile: PersonProfile) -> PersonProfileOut:
    return PersonProfileOut(
        profile_name=profile.profile_name,
        gender=profile.gender,
        birth_year=profile.birth_year,
        education=profile.education,
        current_positions_raw=_compact_text(profile.current_positions_raw, 600),
        career_history_raw=_compact_text(profile.career_history_raw, 900),
        resume_raw=_compact_text(profile.resume_raw, 1200) or "",
        source_url=profile.source_url,
        confidence=float(profile.confidence),
    )


def _profile_intro(profile: PersonProfile | None, fallback_notes: str | None = None, max_chars: int = 180) -> str | None:
    if profile:
        for value in (profile.current_positions_raw, profile.resume_raw, profile.career_history_raw):
            intro = _compact_text(value, max_chars)
            if intro:
                return intro
    return _compact_text(fallback_notes, max_chars)


def _snapshot_to_out(snapshot: ExecutiveSnapshot) -> ExecutiveSnapshotOut:
    return ExecutiveSnapshotOut(
        person_id=snapshot.person_id,
        person_name=snapshot.person.canonical_name if snapshot.person else snapshot.person_name_raw,
        gender=snapshot.gender,
        birth_year=snapshot.birth_year,
        education=snapshot.education,
        title_raw=snapshot.title_raw,
        role_canonical=role_label(snapshot.role_canonical),
        is_core_role=snapshot.is_core_role,
        compensation=float(snapshot.compensation) if snapshot.compensation is not None else None,
    )


def _company_snapshot_counts_subquery():
    return (
        select(
            func.coalesce(Company.org_id, Company.ticker).label("issuer_key"),
            func.count(ExecutiveSnapshot.id).label("current_executive_count"),
            func.sum(case((ExecutiveSnapshot.is_core_role.is_(True), 1), else_=0)).label("core_executive_count"),
        )
        .join(Company, Company.id == ExecutiveSnapshot.company_id)
        .group_by(func.coalesce(Company.org_id, Company.ticker))
        .subquery()
    )


def _company_listing_query():
    snapshot_counts = _company_snapshot_counts_subquery()
    issuer_key = func.coalesce(Company.org_id, Company.ticker)
    ranked = (
        select(
            Company.id.label("company_id"),
            issuer_key.label("issuer_key"),
            func.row_number()
            .over(
                partition_by=issuer_key,
                order_by=(
                    case((Company.is_active.is_(True), 1), else_=0).desc(),
                    case((Company.baseline_status == "synced", 1), else_=0).desc(),
                    func.coalesce(snapshot_counts.c.current_executive_count, 0).desc(),
                    case((Company.current_ticker.is_not(None), 1), else_=0).desc(),
                    Company.baseline_last_synced_at.desc(),
                    Company.id.desc(),
                ),
            )
            .label("row_num"),
        )
        .outerjoin(snapshot_counts, snapshot_counts.c.issuer_key == issuer_key)
        .subquery()
    )
    canonical_company_ids = select(ranked.c.company_id).where(ranked.c.row_num == 1).subquery()
    return (
        select(
            Company,
            func.coalesce(snapshot_counts.c.current_executive_count, 0).label("current_executive_count"),
            func.coalesce(snapshot_counts.c.core_executive_count, 0).label("core_executive_count"),
        )
        .join(canonical_company_ids, canonical_company_ids.c.company_id == Company.id)
        .outerjoin(snapshot_counts, snapshot_counts.c.issuer_key == issuer_key)
    )


def _company_list_item_from_row(row) -> CompanyListItemOut:
    company = row.Company
    return CompanyListItemOut(
        exchange=company.exchange,
        ticker=company.ticker,
        current_ticker=company.current_ticker,
        org_id=company.org_id,
        company_name=company.company_name,
        short_name=company.short_name,
        industry_l1=company.industry_l1,
        market_segment=company.market_segment,
        baseline_status=company.baseline_status,
        baseline_last_synced_at=company.baseline_last_synced_at,
        current_executive_count=int(row.current_executive_count or 0),
        core_executive_count=int(row.core_executive_count or 0),
    )


def _baseline_run_to_out(run: BaselineRun) -> BaselineRunOut:
    return BaselineRunOut(
        id=run.id,
        run_type=run.run_type,
        status=run.status,
        requested_company_count=run.requested_company_count,
        processed_company_count=run.processed_company_count,
        success_company_count=run.success_company_count,
        failed_company_count=run.failed_company_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _sync_job_to_out(job: SyncJob) -> SyncJobOut:
    return SyncJobOut(
        id=job.id,
        job_type=job.job_type,
        scope=job.scope,
        status=job.status,
        requested_count=job.requested_count,
        processed_count=job.processed_count,
        success_count=job.success_count,
        failed_count=job.failed_count,
        started_at=job.started_at,
        completed_at=job.completed_at,
        notes=job.notes,
    )


def get_project_memory() -> ProjectMemoryOut:
    return ProjectMemoryOut(**load_project_memory())


def get_baseline_summary(db: Session) -> BaselineSummaryOut:
    total_companies = db.scalar(select(func.count()).select_from(Company)) or 0
    active_companies = db.scalar(select(func.count()).select_from(Company).where(Company.is_active.is_(True))) or 0
    synced_companies = db.scalar(select(func.count()).select_from(Company).where(Company.baseline_status == "synced")) or 0
    current_snapshot_rows = db.scalar(select(func.count()).select_from(ExecutiveSnapshot)) or 0
    core_snapshot_rows = (
        db.scalar(select(func.count()).select_from(ExecutiveSnapshot).where(ExecutiveSnapshot.is_core_role.is_(True))) or 0
    )
    latest_run = db.scalar(select(BaselineRun).order_by(desc(BaselineRun.started_at)).limit(1))
    return BaselineSummaryOut(
        total_companies=total_companies,
        active_companies=active_companies,
        synced_companies=synced_companies,
        unsynced_companies=max(total_companies - synced_companies, 0),
        current_snapshot_rows=current_snapshot_rows,
        core_snapshot_rows=core_snapshot_rows,
        last_run_status=latest_run.status if latest_run else None,
        last_run_completed_at=latest_run.completed_at if latest_run else None,
    )


def get_overview(db: Session) -> OverviewOut:
    total_companies = db.scalar(select(func.count()).select_from(Company)) or 0
    total_people = db.scalar(select(func.count()).select_from(Person)) or 0
    total_events = db.scalar(select(func.count()).select_from(Event).where(Event.event_status == "published")) or 0
    added_at = func.coalesce(Event.published_at, Event.created_at)
    today_start = datetime.combine(date.today(), time.min)
    today_end = datetime.combine(date.today(), time.max)
    today_changes = db.scalar(
        select(func.count()).select_from(Event).where(
            Event.event_status == "published",
            added_at >= today_start,
            added_at <= today_end,
        )
    ) or 0
    watchlist_count = db.scalar(select(func.count()).select_from(Watchlist)) or 0
    unread_alert_count = db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "new")) or 0
    pending_review_count = db.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.status == "pending")) or 0

    latest_metric_date = db.scalar(select(func.max(CompanyMetricDaily.metric_date)))
    rankings: list[dict] = []
    if latest_metric_date:
        rows = db.execute(
            select(Company.short_name, Company.ticker, CompanyMetricDaily.change_count_30d, CompanyMetricDaily.stability_score)
            .join(CompanyMetricDaily, CompanyMetricDaily.company_id == Company.id)
            .where(CompanyMetricDaily.metric_date == latest_metric_date)
            .order_by(desc(CompanyMetricDaily.change_count_30d), CompanyMetricDaily.stability_score)
            .limit(5)
        ).all()
        rankings = [
            {
                "company_name": row.short_name,
                "ticker": row.ticker,
                "change_count_30d": row.change_count_30d,
                "stability_score": float(row.stability_score) if row.stability_score is not None else None,
            }
            for row in rows
        ]

    recent_feed = list_events(db, limit=8)
    return OverviewOut(
        total_companies=total_companies,
        total_people=total_people,
        total_events=total_events,
        today_changes=today_changes,
        baseline=get_baseline_summary(db),
        top_churn_companies=rankings,
        recent_events=recent_feed.items,
        watchlist_count=watchlist_count,
        unread_alert_count=unread_alert_count,
        pending_review_count=pending_review_count,
    )


def list_events(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    role: str | None = None,
    event_type: str | None = None,
    ticker: str | None = None,
    q: str | None = None,
    include_review: bool = False,
) -> FeedQueryOut:
    query = (
        select(Event)
        .options(joinedload(Event.company), joinedload(Event.person), joinedload(Event.source_document))
        .order_by(desc(Event.announcement_date), desc(Event.id))
    )
    if include_review:
        query = query.where(Event.event_status.in_(("published", "review_required")))
    else:
        query = query.where(Event.event_status == "published")
    if role:
        query = query.where(Event.role_canonical == role)
    if event_type:
        query = query.where(Event.event_type == event_type)
    if ticker:
        query = query.where(Event.company.has(or_(Company.ticker == ticker, Company.current_ticker == ticker)))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Event.company.has(Company.company_name.like(pattern)),
                Event.company.has(Company.short_name.like(pattern)),
                Event.company.has(Company.ticker.like(pattern)),
                Event.company.has(Company.current_ticker.like(pattern)),
                Event.person.has(Person.canonical_name.like(pattern)),
                Event.excerpt.like(pattern),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.limit(limit).offset(offset)).all()
    return FeedQueryOut(total=total, limit=limit, offset=offset, items=[_event_to_out(item) for item in items])


def list_recent_companies(db: Session) -> list[Company]:
    rows = db.execute(
        _company_listing_query().order_by(desc(Company.baseline_last_synced_at), Company.exchange, Company.ticker).limit(20)
    ).all()
    return [row.Company for row in rows]


def _resolve_canonical_company(db: Session, ticker: str) -> Company | None:
    matched = db.scalar(select(Company).where(or_(Company.ticker == ticker, Company.current_ticker == ticker)))
    if not matched:
        return None
    if not matched.org_id:
        return matched
    row = db.execute(
        _company_listing_query()
        .where(Company.org_id == matched.org_id)
        .limit(1)
    ).first()
    return row.Company if row else matched


def search_companies(
    db: Session,
    q: str | None = None,
    exchange: str | None = None,
    baseline_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CompanySearchOut:
    query = _company_listing_query()
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Company.ticker.like(pattern),
                Company.current_ticker.like(pattern),
                Company.company_name.like(pattern),
                Company.short_name.like(pattern),
            )
        )
    if exchange:
        query = query.where(Company.exchange == exchange)
    if baseline_status:
        query = query.where(Company.baseline_status == baseline_status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(desc(Company.baseline_last_synced_at), Company.exchange, Company.ticker).limit(limit).offset(offset)
    ).all()
    return CompanySearchOut(total=total, limit=limit, offset=offset, items=[_company_list_item_from_row(row) for row in rows])


def search_people(
    db: Session,
    q: str | None = None,
    role: str | None = None,
    active_only: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> PersonSearchOut:
    pattern = f"%{q.strip()}%" if q else None
    if active_only:
        id_query = (
            select(Person.id)
            .join(RoleTenure, RoleTenure.person_id == Person.id)
            .where(RoleTenure.is_active.is_(True))
            .group_by(Person.id)
        )
        if pattern:
            id_query = id_query.where(Person.canonical_name.like(pattern))
        if role:
            id_query = id_query.where(RoleTenure.role_canonical == role)
        total = db.scalar(select(func.count()).select_from(id_query.subquery())) or 0
        person_ids = list(db.scalars(id_query.order_by(Person.canonical_name).limit(limit).offset(offset)).all())
        if not person_ids:
            return PersonSearchOut(total=total, limit=limit, offset=offset, items=[])
        people = db.scalars(select(Person).where(Person.id.in_(person_ids)).order_by(Person.canonical_name)).all()
    else:
        query = select(Person)
        if pattern:
            query = query.where(Person.canonical_name.like(pattern))
        if role:
            tenure_exists = select(RoleTenure.id).where(RoleTenure.person_id == Person.id, RoleTenure.role_canonical == role)
            query = query.where(exists(tenure_exists))
        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        people = db.scalars(query.order_by(Person.canonical_name).limit(limit).offset(offset)).all()
    if not people:
        return PersonSearchOut(total=total, limit=limit, offset=offset, items=[])
    person_ids = [person.id for person in people]
    profiles = db.scalars(
        select(PersonProfile)
        .where(PersonProfile.person_id.in_(person_ids))
        .order_by(PersonProfile.person_id, desc(PersonProfile.updated_at), desc(PersonProfile.id))
    ).all()
    profile_by_person: dict[int, PersonProfile] = {}
    for profile in profiles:
        profile_by_person.setdefault(profile.person_id, profile)
    active_tenures = db.scalars(
        select(RoleTenure)
        .options(joinedload(RoleTenure.company))
        .where(RoleTenure.person_id.in_(person_ids), RoleTenure.is_active.is_(True))
        .order_by(RoleTenure.person_id, RoleTenure.role_canonical)
    ).all()
    active_by_person: dict[int, list[RoleTenure]] = {}
    for tenure in active_tenures:
        active_by_person.setdefault(tenure.person_id, []).append(tenure)
    items: list[PersonListItemOut] = []
    for person in people:
        tenures = active_by_person.get(person.id, [])
        role_summary = [
            f"{role_label(item.role_canonical)} · {item.company.short_name or item.company.company_name}" for item in tenures[:3]
        ]
        profile = profile_by_person.get(person.id)
        fallback_intro = person.notes or (f"当前任职：{'；'.join(role_summary)}" if role_summary else None)
        items.append(
            PersonListItemOut(
                id=person.id,
                canonical_name=person.canonical_name,
                education=person.education or (profile.education if profile else None),
                gender=person.gender or (profile.gender if profile else None),
                birth_year=person.birth_year or (profile.birth_year if profile else None),
                profile_intro=_profile_intro(profile, fallback_intro),
                active_role_count=len(tenures),
                active_company_count=len({item.company_id for item in tenures}),
                active_roles_summary=role_summary,
            )
        )
    return PersonSearchOut(total=total, limit=limit, offset=offset, items=items)


def get_coverage_dashboard(db: Session, pending_limit: int = 20) -> CoverageDashboardOut:
    baseline = get_baseline_summary(db)
    total_people = db.scalar(select(func.count()).select_from(Person)) or 0
    active_companies = baseline.active_companies or 0
    coverage_rate = round((baseline.synced_companies / baseline.total_companies), 4) if baseline.total_companies else 0.0
    status_rows = db.execute(
        select(Company.baseline_status, func.count()).select_from(Company).group_by(Company.baseline_status).order_by(desc(func.count()))
    ).all()
    status_breakdown = [
        StatusBreakdownItemOut(
            label=row[0] or "unknown",
            count=int(row[1]),
            ratio=round((int(row[1]) / baseline.total_companies), 4) if baseline.total_companies else 0.0,
        )
        for row in status_rows
    ]
    exchange_rows = db.execute(
        select(
            Company.exchange,
            func.count().label("total_count"),
            func.sum(case((Company.baseline_status == "synced", 1), else_=0)).label("synced_count"),
        )
        .where(Company.is_active.is_(True))
        .group_by(Company.exchange)
        .order_by(Company.exchange)
    ).all()
    exchange_breakdown = [
        CoverageBucketOut(
            label=row.exchange or "UNKNOWN",
            total_count=int(row.total_count or 0),
            synced_count=int(row.synced_count or 0),
            coverage_rate=round((int(row.synced_count or 0) / max(int(row.total_count or 1), 1)), 4),
        )
        for row in exchange_rows
    ]
    segment_rows = db.execute(
        select(
            Company.market_segment,
            func.count().label("total_count"),
            func.sum(case((Company.baseline_status == "synced", 1), else_=0)).label("synced_count"),
        )
        .where(Company.is_active.is_(True))
        .group_by(Company.market_segment)
        .order_by(desc(func.count()))
    ).all()
    segment_breakdown = [
        CoverageBucketOut(
            label=row.market_segment or "未识别板块",
            total_count=int(row.total_count or 0),
            synced_count=int(row.synced_count or 0),
            coverage_rate=round((int(row.synced_count or 0) / max(int(row.total_count or 1), 1)), 4),
        )
        for row in segment_rows
    ]
    role_rows = db.execute(
        select(
            ExecutiveSnapshot.role_canonical,
            func.count(func.distinct(ExecutiveSnapshot.company_id)).label("company_count"),
            func.min(ExecutiveSnapshot.role_priority).label("sort_priority"),
        )
        .where(ExecutiveSnapshot.is_core_role.is_(True))
        .group_by(ExecutiveSnapshot.role_canonical)
        .order_by(func.min(ExecutiveSnapshot.role_priority), ExecutiveSnapshot.role_canonical)
    ).all()
    role_coverage = [
        RoleCoverageItemOut(
            role_canonical=role_label(row.role_canonical),
            company_count=int(row.company_count or 0),
            coverage_rate=round((int(row.company_count or 0) / active_companies), 4) if active_companies else 0.0,
        )
        for row in role_rows
    ]
    recent_runs = db.scalars(select(BaselineRun).order_by(desc(BaselineRun.started_at)).limit(10)).all()
    pending_rows = db.execute(
        _company_listing_query()
        .where(Company.is_active.is_(True), Company.baseline_status != "synced")
        .order_by(Company.baseline_last_synced_at.is_not(None), Company.baseline_last_synced_at, Company.ticker)
        .limit(pending_limit)
    ).all()
    return CoverageDashboardOut(
        total_companies=baseline.total_companies,
        active_companies=baseline.active_companies,
        synced_companies=baseline.synced_companies,
        unsynced_companies=baseline.unsynced_companies,
        coverage_rate=coverage_rate,
        total_people=total_people,
        current_snapshot_rows=baseline.current_snapshot_rows,
        core_snapshot_rows=baseline.core_snapshot_rows,
        status_breakdown=status_breakdown,
        exchange_breakdown=exchange_breakdown,
        segment_breakdown=segment_breakdown,
        role_coverage=role_coverage,
        recent_runs=[_baseline_run_to_out(run) for run in recent_runs],
        pending_companies=[_company_list_item_from_row(row) for row in pending_rows],
    )


def get_launch_readiness(db: Session) -> LaunchReadinessOut:
    raw_total_companies = db.scalar(select(func.count()).select_from(Company)) or 0
    synced_companies = db.scalar(select(func.count()).select_from(Company).where(Company.baseline_status == "synced")) or 0
    canonical_rows = db.execute(_company_listing_query()).all()
    canonical_companies = len(canonical_rows)
    canonical_zero_snapshot_companies = sum(1 for row in canonical_rows if int(row.current_executive_count or 0) == 0)
    duplicate_org_id_count = (
        db.scalar(
            select(func.count())
            .select_from(
                select(Company.org_id)
                .where(Company.org_id.is_not(None))
                .group_by(Company.org_id)
                .having(func.count() > 1)
                .subquery()
            )
        )
        or 0
    )
    published_event_count = db.scalar(select(func.count()).select_from(Event).where(Event.event_status == "published")) or 0
    pending_review_count = db.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.status == "pending")) or 0

    blocking_issues: list[str] = []
    ready_items: list[str] = []

    if synced_companies == raw_total_companies:
        ready_items.append("公司原始全集已完成 6100/6100 同步。")
    else:
        blocking_issues.append("公司原始全集尚未全量同步完成。")

    if duplicate_org_id_count > 0:
        ready_items.append(f"系统已识别到 {duplicate_org_id_count} 组重复 org_id，并在公司库查询与详情页按发行人聚合展示。")

    if settings.database_url.startswith("sqlite"):
        blocking_issues.append("当前仍使用 SQLite，且已出现锁库现象。正式公网运营前应迁移到 PostgreSQL 或其他服务端数据库。")

    if canonical_zero_snapshot_companies > 120:
        blocking_issues.append(
            f"去重后的发行人视图里仍有 {canonical_zero_snapshot_companies} 家零快照公司，需继续收窄‘当前在市’口径后再做大范围外部运营。"
        )
    else:
        ready_items.append("去重后的发行人视图零快照缺口已收敛到可控范围。")

    if published_event_count >= 20:
        ready_items.append("事件层已经具备基础可用性。")
    else:
        blocking_issues.append(
            f"当前已发布事件仅 {published_event_count} 条，事件流覆盖仍偏薄，更适合种子客户试运营，不适合对外宣称成熟事件数据库。"
        )

    if pending_review_count <= 20:
        ready_items.append("人工审核队列规模可控。")
    else:
        blocking_issues.append("人工审核队列仍偏大，会拖慢正式运营中的事件交付。")

    if settings.admin_password:
        ready_items.append("后台登录保护已启用。")
    else:
        blocking_issues.append("尚未设置 APP_ADMIN_PASSWORD，正式部署前必须启用后台登录保护。")

    if settings.secret_key_is_default:
        blocking_issues.append("APP_SECRET_KEY 仍是默认值，正式部署前必须替换为自定义随机密钥。")
    else:
        ready_items.append("应用签名密钥已自定义。")

    overall_status = "ready_for_seed_operation" if not blocking_issues else "seed_operation_with_blockers"
    return LaunchReadinessOut(
        raw_total_companies=raw_total_companies,
        synced_companies=synced_companies,
        canonical_companies=canonical_companies,
        canonical_zero_snapshot_companies=canonical_zero_snapshot_companies,
        duplicate_org_id_count=duplicate_org_id_count,
        published_event_count=published_event_count,
        pending_review_count=pending_review_count,
        auth_enabled=bool(settings.admin_password),
        overall_status=overall_status,
        blocking_issues=blocking_issues,
        ready_items=ready_items,
    )


def get_runtime_preflight(db: Session) -> RuntimePreflightOut:
    canonical_rows = db.execute(_company_listing_query()).all()
    canonical_zero_snapshot_companies = sum(1 for row in canonical_rows if int(row.current_executive_count or 0) == 0)
    pending_review_count = db.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.status == "pending")) or 0
    published_event_count = db.scalar(select(func.count()).select_from(Event).where(Event.event_status == "published")) or 0

    checks: list[RuntimeCheckOut] = [
        RuntimeCheckOut(
            name="database_backend",
            status="blocked" if settings.uses_sqlite else "ready",
            level="blocking" if settings.uses_sqlite else "ready",
            detail="当前仍使用 SQLite，正式公网运行前必须迁移到 PostgreSQL。"
            if settings.uses_sqlite
            else "已使用服务端数据库。",
        ),
        RuntimeCheckOut(
            name="admin_password",
            status="blocked" if not settings.auth_enabled else "ready",
            level="blocking" if not settings.auth_enabled else "ready",
            detail="尚未设置 APP_ADMIN_PASSWORD，后台和导出接口不能裸奔上线。"
            if not settings.auth_enabled
            else "后台登录保护已启用。",
        ),
        RuntimeCheckOut(
            name="secret_key",
            status="blocked" if settings.secret_key_is_default else "ready",
            level="blocking" if settings.secret_key_is_default else "ready",
            detail="APP_SECRET_KEY 仍是默认值，正式上线前必须替换。"
            if settings.secret_key_is_default
            else "应用签名密钥已自定义。",
        ),
        RuntimeCheckOut(
            name="public_base_url",
            status="warning" if not settings.public_base_url else "ready",
            level="warning" if not settings.public_base_url else "ready",
            detail="尚未设置 APP_PUBLIC_BASE_URL，外部回调、邮件跳转和部署校验会受影响。"
            if not settings.public_base_url
            else f"已配置站点地址：{settings.public_base_url}",
        ),
        RuntimeCheckOut(
            name="external_alerting",
            status="warning" if not settings.external_alerting_configured else "ready",
            level="warning" if not settings.external_alerting_configured else "ready",
            detail="尚未配置邮件或 webhook 送达通道，提醒功能只能停留在站内。"
            if not settings.external_alerting_configured
            else "已检测到可用的站外提醒配置。",
        ),
        RuntimeCheckOut(
            name="canonical_zero_snapshot_companies",
            status="warning" if canonical_zero_snapshot_companies > 50 else "ready",
            level="warning" if canonical_zero_snapshot_companies > 50 else "ready",
            detail=f"当前去重后零快照发行人仍有 {canonical_zero_snapshot_companies} 家，正式上线前建议压到 50 家以下。"
            if canonical_zero_snapshot_companies > 50
            else "去重后零快照发行人已压到可上线区间。",
        ),
        RuntimeCheckOut(
            name="published_events",
            status="warning" if published_event_count < 500 else "ready",
            level="warning" if published_event_count < 500 else "ready",
            detail=f"当前已发布事件只有 {published_event_count} 条，正式运营前建议至少建立 500 条以上历史事件底座。"
            if published_event_count < 500
            else "事件底座已达到正式运营建议值。",
        ),
        RuntimeCheckOut(
            name="pending_review_queue",
            status="warning" if pending_review_count > 20 else "ready",
            level="warning" if pending_review_count > 20 else "ready",
            detail=f"当前待审核队列有 {pending_review_count} 条，正式运营前建议稳定压到 20 条以内。"
            if pending_review_count > 20
            else "审核队列处于可控范围。",
        ),
    ]

    if any(item.level == "blocking" for item in checks):
        overall_status = "blocked"
    elif any(item.level == "warning" for item in checks):
        overall_status = "warning"
    else:
        overall_status = "ready"

    return RuntimePreflightOut(
        environment=settings.app_env,
        database_backend="sqlite" if settings.uses_sqlite else "postgresql",
        public_base_url=settings.public_base_url or None,
        overall_status=overall_status,
        checks=checks,
    )


def get_company_detail(db: Session, ticker: str) -> CompanyDetailOut | None:
    company = _resolve_canonical_company(db, ticker)
    if not company:
        return None
    company_ids = (
        list(db.scalars(select(Company.id).where(Company.org_id == company.org_id)).all())
        if company.org_id
        else [company.id]
    )
    metrics = db.scalars(
        select(CompanyMetricDaily).where(CompanyMetricDaily.company_id == company.id).order_by(desc(CompanyMetricDaily.metric_date)).limit(5)
    ).all()
    tenures = db.scalars(
        select(RoleTenure)
        .options(joinedload(RoleTenure.person))
        .where(RoleTenure.company_id.in_(company_ids), RoleTenure.is_active.is_(True))
        .order_by(RoleTenure.role_canonical, RoleTenure.start_date)
    ).all()
    snapshots = db.scalars(
        select(ExecutiveSnapshot)
        .options(joinedload(ExecutiveSnapshot.person))
        .where(ExecutiveSnapshot.company_id.in_(company_ids))
        .order_by(ExecutiveSnapshot.role_priority, ExecutiveSnapshot.person_name_raw)
    ).all()
    events = db.scalars(
        select(Event)
        .options(joinedload(Event.company), joinedload(Event.person), joinedload(Event.source_document))
        .where(Event.company_id.in_(company_ids), Event.event_status == "published")
        .order_by(desc(Event.announcement_date), desc(Event.id))
        .limit(20)
    ).all()
    return CompanyDetailOut(
        company_name=company.company_name,
        short_name=company.short_name,
        ticker=company.ticker,
        current_ticker=company.current_ticker,
        exchange=company.exchange,
        org_id=company.org_id,
        industry_l1=company.industry_l1,
        website=company.website,
        listed_date=company.listed_date,
        legal_representative=company.legal_representative,
        general_manager_name=company.general_manager_name,
        baseline_status=company.baseline_status,
        baseline_last_synced_at=company.baseline_last_synced_at,
        state_owned_flag=company.state_owned_flag,
        metrics=[_metric_to_out(item) for item in metrics],
        active_tenures=[
            CompanyTenureOut(
                person_name=item.person.canonical_name,
                role_canonical=role_label(item.role_canonical),
                start_date=item.start_date,
                end_date=item.end_date,
                is_active=item.is_active,
            )
            for item in tenures
        ],
        current_executives=[_snapshot_to_out(item) for item in snapshots],
        recent_events=[_event_to_out(event) for event in events],
    )


def get_person_detail(db: Session, person_id: int) -> PersonDetailOut | None:
    person = db.scalar(select(Person).where(Person.id == person_id))
    if not person:
        return None
    profiles = db.scalars(
        select(PersonProfile)
        .where(PersonProfile.person_id == person.id)
        .order_by(desc(PersonProfile.updated_at), desc(PersonProfile.id))
        .limit(5)
    ).all()
    primary_profile = profiles[0] if profiles else None
    tenures = db.scalars(
        select(RoleTenure)
        .options(joinedload(RoleTenure.company))
        .where(RoleTenure.person_id == person.id)
        .order_by(desc(RoleTenure.is_active), desc(RoleTenure.start_date))
    ).all()
    events = db.scalars(
        select(Event)
        .options(joinedload(Event.company), joinedload(Event.person), joinedload(Event.source_document))
        .where(Event.person_id == person.id, Event.event_status == "published")
        .order_by(desc(Event.announcement_date), desc(Event.id))
        .limit(20)
    ).all()
    history = [
        PersonTenureOut(
            company_name=item.company.short_name or item.company.company_name,
            ticker=item.company.ticker,
            role_canonical=role_label(item.role_canonical),
            start_date=item.start_date,
            end_date=item.end_date,
            is_active=item.is_active,
        )
        for item in tenures
    ]
    active_roles = [item for item in history if item.is_active]
    active_intro = "；".join(f"{item.company_name} {item.role_canonical}" for item in active_roles[:5])
    fallback_intro = person.notes or (f"当前任职：{active_intro}" if active_intro else None)
    return PersonDetailOut(
        id=person.id,
        canonical_name=person.canonical_name,
        gender=person.gender or (primary_profile.gender if primary_profile else None),
        birth_year=person.birth_year or (primary_profile.birth_year if primary_profile else None),
        education=person.education or (primary_profile.education if primary_profile else None),
        notes=person.notes,
        profile_intro=_profile_intro(primary_profile, fallback_intro, max_chars=360),
        current_positions_raw=_compact_text(primary_profile.current_positions_raw, 900) if primary_profile else None,
        career_history_raw=_compact_text(primary_profile.career_history_raw, 1200) if primary_profile else None,
        profiles=[_profile_to_out(profile) for profile in profiles],
        active_roles=active_roles,
        history=history,
        recent_events=[_event_to_out(event) for event in events],
    )


def get_churn_rankings(db: Session) -> list[dict]:
    latest_metric_date = db.scalar(select(func.max(CompanyMetricDaily.metric_date)))
    if not latest_metric_date:
        return []
    rows = db.execute(
        select(
            Company.company_name,
            Company.short_name,
            Company.ticker,
            CompanyMetricDaily.change_count_30d,
            CompanyMetricDaily.change_count_90d,
            CompanyMetricDaily.stability_score,
            CompanyMetricDaily.abnormal_turnover_flag,
        )
        .join(CompanyMetricDaily, CompanyMetricDaily.company_id == Company.id)
        .where(CompanyMetricDaily.metric_date == latest_metric_date)
        .order_by(desc(CompanyMetricDaily.change_count_30d), CompanyMetricDaily.stability_score)
    ).all()
    return [
        {
            "company_name": row.short_name or row.company_name,
            "ticker": row.ticker,
            "change_count_30d": row.change_count_30d,
            "change_count_90d": row.change_count_90d,
            "stability_score": float(row.stability_score) if row.stability_score is not None else None,
            "abnormal_turnover_flag": row.abnormal_turnover_flag,
        }
        for row in rows
    ]


def list_watchlists(db: Session, session_id: str | None = None) -> list[WatchlistOut]:
    query = (
        select(Watchlist)
        .options(joinedload(Watchlist.company), joinedload(Watchlist.person), joinedload(Watchlist.alerts))
        .order_by(desc(Watchlist.created_at))
    )
    if session_id:
        query = query.where(Watchlist.session_id == session_id)
    else:
        query = query.where(Watchlist.session_id.is_(None))
    watchlists = db.execute(query).unique().scalars().all()
    items: list[WatchlistOut] = []
    for item in watchlists:
        items.append(
            WatchlistOut(
                id=item.id,
                target_type=item.target_type,
                display_name=item.display_name,
                role_canonical=role_label(item.role_canonical) if item.role_canonical else None,
                company_ticker=(item.company.current_ticker or item.company.ticker) if item.company else None,
                person_id=item.person_id,
                notes=item.notes,
                created_at=item.created_at,
                alert_count=len(item.alerts),
                unread_alert_count=len([alert for alert in item.alerts if alert.status == "new"]),
            )
        )
    return items


def create_watchlist(
    db: Session,
    *,
    session_id: str | None = None,
    target_type: str,
    ticker: str | None = None,
    person_id: int | None = None,
    role_canonical: str | None = None,
    notes: str | None = None,
) -> WatchlistOut:
    company = _resolve_canonical_company(db, ticker) if ticker else None
    person = db.get(Person, person_id) if person_id else None
    if target_type == "company" and not company:
        raise ValueError("公司不存在")
    if target_type == "person" and not person:
        raise ValueError("人物不存在")
    if target_type == "role" and not role_canonical:
        raise ValueError("角色不能为空")
    if target_type == "company":
        display_name = f"公司 · {company.short_name or company.company_name}"
    elif target_type == "person":
        display_name = f"人物 · {person.canonical_name}"
    else:
        display_name = f"角色 · {role_label(role_canonical or '')}"
    existing_where = [
        Watchlist.target_type == target_type,
        Watchlist.company_id == (company.id if company else None),
        Watchlist.person_id == (person.id if person else None),
        Watchlist.role_canonical == role_canonical,
    ]
    if session_id:
        existing_where.append(Watchlist.session_id == session_id)
    else:
        existing_where.append(Watchlist.session_id.is_(None))
    existing = db.scalar(select(Watchlist).where(*existing_where))
    if existing:
        if notes:
            existing.notes = notes
        db.flush()
        return WatchlistOut(
            id=existing.id,
            target_type=existing.target_type,
            display_name=existing.display_name,
            role_canonical=role_label(existing.role_canonical) if existing.role_canonical else None,
            company_ticker=(existing.company.current_ticker or existing.company.ticker) if existing.company else None,
            person_id=existing.person_id,
            notes=existing.notes,
            created_at=existing.created_at,
        )
    watchlist = Watchlist(
        session_id=session_id,
        target_type=target_type,
        company_id=company.id if company else None,
        person_id=person.id if person else None,
        role_canonical=role_canonical,
        display_name=display_name,
        notes=notes,
    )
    db.add(watchlist)
    db.flush()
    return WatchlistOut(
        id=watchlist.id,
        target_type=watchlist.target_type,
        display_name=watchlist.display_name,
        role_canonical=role_label(watchlist.role_canonical) if watchlist.role_canonical else None,
        company_ticker=(company.current_ticker or company.ticker) if company else None,
        person_id=watchlist.person_id,
        notes=watchlist.notes,
        created_at=watchlist.created_at,
    )


def delete_watchlist(db: Session, watchlist_id: int, session_id: str | None = None) -> bool:
    watchlist = db.get(Watchlist, watchlist_id)
    if not watchlist:
        return False
    if session_id and watchlist.session_id != session_id:
        return False
    db.delete(watchlist)
    return True


def list_alerts(db: Session, *, session_id: str | None = None, status: str | None = None, limit: int = 100) -> list[AlertOut]:
    query = (
        select(Alert)
        .join(Watchlist, Alert.watchlist_id == Watchlist.id)
        .options(
            joinedload(Alert.watchlist),
            joinedload(Alert.event).joinedload(Event.company),
            joinedload(Alert.event).joinedload(Event.person),
            joinedload(Alert.event).joinedload(Event.source_document),
        )
        .order_by(desc(Alert.created_at))
    )
    if session_id:
        query = query.where(Watchlist.session_id == session_id)
    if status:
        query = query.where(Alert.status == status)
    alerts = db.execute(query.limit(limit)).unique().scalars().all()
    return [
        AlertOut(
            id=item.id,
            status=item.status,
            created_at=item.created_at,
            delivery_channel=item.delivery_channel,
            watchlist_name=item.watchlist.display_name,
            event=_event_to_out(item.event),
        )
        for item in alerts
    ]


def mark_alert_read(db: Session, alert_id: int, session_id: str | None = None) -> bool:
    alert = (
        select(Alert)
        .join(Watchlist, Alert.watchlist_id == Watchlist.id)
        .where(Alert.id == alert_id)
    )
    if session_id:
        alert = alert.where(Watchlist.session_id == session_id)
    alert = db.execute(alert).scalar_one_or_none()
    if not alert:
        return False
    alert.status = "read"
    alert.read_at = datetime.utcnow()
    return True


def list_review_queue(db: Session, *, status: str = "pending", limit: int = 100) -> list[ReviewQueueItemOut]:
    query = (
        select(ReviewQueue)
        .options(
            joinedload(ReviewQueue.event).joinedload(Event.company),
            joinedload(ReviewQueue.event).joinedload(Event.person),
            joinedload(ReviewQueue.event).joinedload(Event.source_document),
            joinedload(ReviewQueue.source_document),
        )
        .order_by(desc(ReviewQueue.created_at))
    )
    if status:
        query = query.where(ReviewQueue.status == status)
    rows = db.scalars(query.limit(limit)).all()
    items: list[ReviewQueueItemOut] = []
    for row in rows:
        source_document = row.source_document or (row.event.source_document if row.event else None)
        extraction_hints: list[ReviewExtractionHintOut] = []
        source_excerpt = None
        if source_document:
            raw_text = source_document.raw_text or ""
            source_excerpt = raw_text[:500] if raw_text else None
            for hint in extract_review_hints_from_text(source_document.title, raw_text, limit=6):
                extraction_hints.append(
                    ReviewExtractionHintOut(
                        person_name=hint.person_name,
                        role_canonical=role_label(hint.role_canonical) if hint.role_canonical else None,
                        role_raw=hint.role_raw,
                        event_type=event_type_label(hint.event_type) if hint.event_type else None,
                        excerpt=hint.excerpt,
                        confidence=hint.confidence,
                        source=hint.source,
                        missing_fields=list(hint.missing_fields),
                    )
                )
            if not extraction_hints:
                extraction_hints.append(
                    ReviewExtractionHintOut(
                        person_name=None,
                        role_canonical=None,
                        role_raw=None,
                        event_type=None,
                        excerpt=source_excerpt or source_document.title,
                        confidence=0.30,
                        source="待人工查看原文",
                        missing_fields=["人员姓名", "角色职位", "事件类型"],
                    )
                )
        items.append(
            ReviewQueueItemOut(
                id=row.id,
                source_document_id=source_document.id if source_document else None,
                review_type=row.review_type,
                status=row.status,
                reason=row.reason,
                created_at=row.created_at,
                resolved_at=row.resolved_at,
                event=_event_to_out(row.event) if row.event else None,
                source_document_title=source_document.title if source_document else None,
                source_url=source_document.source_url if source_document else None,
                source_document_excerpt=source_excerpt,
                extraction_hints=extraction_hints,
            )
        )
    return items


def list_review_document_groups(db: Session, *, status: str = "pending", limit: int = 500) -> list[dict]:
    """Group pending review items by announcement to avoid duplicate review cards."""
    items = list_review_queue(db, status=status, limit=limit)
    groups: dict[str, dict] = {}
    for item in items:
        key = str(item.source_document_id) if item.source_document_id else f"review:{item.id}"
        group = groups.get(key)
        if not group:
            event = item.event
            group = {
                "key": key,
                "source_document_id": item.source_document_id,
                "title": item.source_document_title or (event.company_name if event else "未知公告"),
                "source_url": item.source_url or (event.source_url if event else None),
                "source_document_excerpt": item.source_document_excerpt,
                "company_name": event.company_name if event else None,
                "company_ticker": event.company_ticker if event else None,
                "review_ids": [],
                "review_count": 0,
                "event_count": 0,
                "document_review_count": 0,
                "reasons": [],
                "items": [],
                "events": [],
                "extraction_hints": item.extraction_hints,
                "created_at_latest": item.created_at,
            }
            groups[key] = group

        group["review_ids"].append(item.id)
        group["review_count"] += 1
        if item.review_type == "document_triage":
            group["document_review_count"] += 1
        if item.event:
            group["event_count"] += 1
            group["events"].append(item.event)
            group["company_name"] = group["company_name"] or item.event.company_name
            group["company_ticker"] = group["company_ticker"] or item.event.company_ticker
        if item.reason and item.reason not in group["reasons"]:
            group["reasons"].append(item.reason)
        if not group["extraction_hints"] and item.extraction_hints:
            group["extraction_hints"] = item.extraction_hints
        if item.created_at > group["created_at_latest"]:
            group["created_at_latest"] = item.created_at
        group["items"].append(item)

    return sorted(groups.values(), key=lambda group: group["created_at_latest"], reverse=True)


def list_recent_sync_jobs(db: Session, limit: int = 20) -> list[SyncJobOut]:
    jobs = db.scalars(select(SyncJob).order_by(desc(SyncJob.started_at)).limit(limit)).all()
    return [_sync_job_to_out(job) for job in jobs]


def _sync_status_label(status: str, failed_count: int) -> str:
    if status == "completed" and failed_count == 0:
        return "正常完成"
    if status == "completed_with_errors":
        return "部分失败，后续会重试"
    if status == "running":
        return "正在执行"
    return "执行异常"


def list_recent_notice_sync_cards(db: Session, limit: int = 8) -> list[dict]:
    jobs = db.scalars(
        select(SyncJob)
        .where(SyncJob.job_type == "notice_ingest")
        .order_by(desc(SyncJob.started_at))
        .limit(limit)
    ).all()
    cards: list[dict] = []
    for job in jobs:
        published_event_count = db.scalar(
            select(func.count(func.distinct(Event.id)))
            .select_from(Event)
            .join(DocumentProcessingRun, DocumentProcessingRun.source_document_id == Event.source_document_id)
            .where(DocumentProcessingRun.sync_job_id == job.id, Event.event_status == "published")
        ) or 0
        review_document_count = db.scalar(
            select(func.count())
            .select_from(DocumentProcessingRun)
            .where(DocumentProcessingRun.sync_job_id == job.id, DocumentProcessingRun.status == "review_required")
        ) or 0
        ignored_document_count = db.scalar(
            select(func.count())
            .select_from(DocumentProcessingRun)
            .where(DocumentProcessingRun.sync_job_id == job.id, DocumentProcessingRun.status == "ignored")
        ) or 0
        cards.append(
            {
                "title": "公告同步",
                "status_label": _sync_status_label(job.status, job.failed_count),
                "needs_attention": job.failed_count > 0 or job.status not in {"completed", "completed_with_errors"},
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "requested_count": job.requested_count,
                "processed_count": job.processed_count,
                "success_count": job.success_count,
                "failed_count": job.failed_count,
                "published_event_count": int(published_event_count),
                "review_document_count": int(review_document_count),
                "ignored_document_count": int(ignored_document_count),
                "summary": (
                    f"发现 {job.requested_count} 篇候选公告，处理 {job.processed_count} 篇，"
                    f"已发布事件 {int(published_event_count)} 条，待审核公告 {int(review_document_count)} 篇。"
                ),
                "failure_note": (
                    f"{job.failed_count} 篇处理失败。系统每 30 分钟回看最近 3 天公告，通常会在后续任务中重试。"
                    if job.failed_count
                    else ""
                ),
            }
        )
    return cards


def get_daily_new_events(db: Session, *, day: date | None = None, days: int = 14, limit: int = 200) -> dict:
    added_at = func.coalesce(Event.published_at, Event.created_at)
    day_expr = func.date(added_at)
    count_rows = db.execute(
        select(day_expr.label("day"), func.count(Event.id).label("event_count"))
        .where(Event.event_status == "published")
        .group_by(day_expr)
        .order_by(desc(day_expr))
        .limit(days)
    ).all()
    daily_counts = [{"date": str(row.day), "event_count": int(row.event_count or 0)} for row in count_rows]
    selected_date = day or (date.fromisoformat(daily_counts[0]["date"]) if daily_counts else date.today())
    start_at = datetime.combine(selected_date, time.min)
    end_at = datetime.combine(selected_date, time.max)
    events = db.scalars(
        select(Event)
        .options(joinedload(Event.company), joinedload(Event.person), joinedload(Event.source_document))
        .where(
            Event.event_status == "published",
            added_at >= start_at,
            added_at <= end_at,
        )
        .order_by(desc(added_at), desc(Event.id))
        .limit(limit)
    ).all()
    return {
        "selected_date": selected_date,
        "selected_date_str": selected_date.isoformat(),
        "daily_counts": daily_counts,
        "events": [
            {
                "event": _event_to_out(event),
                "added_at": event.published_at or event.created_at,
                "source_title": event.source_document.title,
            }
            for event in events
        ],
    }


def export_events_rows(
    db: Session,
    *,
    role: str | None = None,
    event_type: str | None = None,
    ticker: str | None = None,
    include_review: bool = False,
) -> list[dict[str, str]]:
    feed = list_events(db, limit=2000, role=role, event_type=event_type, ticker=ticker, include_review=include_review)
    rows: list[dict[str, str]] = []
    for item in feed.items:
        rows.append(
            {
                "公司": item.company_name,
                "代码": item.company_ticker,
                "人物": item.person_name or "",
                "角色": item.role_canonical,
                "事件": item.event_type,
                "状态": item.event_status,
                "公告日期": item.announcement_date.isoformat() if item.announcement_date else "",
                "生效日期": item.effective_date.isoformat() if item.effective_date else "",
                "置信度": f"{item.confidence:.2f}",
                "证据": item.excerpt,
                "来源": item.source_url,
            }
        )
    return rows


def record_page_view(
    db: Session,
    *,
    path: str,
    referrer: str | None = None,
    user_agent: str | None = None,
    ip_hash: str | None = None,
    session_id: str | None = None,
) -> None:
    from app.models import PageView
    db.add(
        PageView(
            path=path,
            referrer=referrer,
            user_agent=user_agent,
            ip_hash=ip_hash,
            session_id=session_id,
        )
    )
    db.commit()


def get_stats(db: Session) -> dict:
    from app.models import PageView, AIUsageLog
    from datetime import datetime, timedelta

    # Exclude known bots from historical data.
    # NOTE: Search engine crawlers (Googlebot, Bingbot, Baiduspider, Sogou) are
    # intentionally NOT filtered here to preserve SEO visibility in stats.
    bot_patterns = [
        "%GPTBot%", "%MJ12bot%", "%GoogleOther%", "%TLM-Audit-Scanner%",
        "%AhrefsBot%", "%SemrushBot%", "%DotBot%", "%YandexBot%",
        "%Exabot%", "%Facebot%", "%ia_archiver%",
        "%Datadog%", "%UptimeRobot%", "%Screaming%",
    ]
    from sqlalchemy import true
    bot_filter = true()
    for pat in bot_patterns:
        bot_filter = bot_filter & (~PageView.user_agent.ilike(pat))

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)
    five_min_ago = now - timedelta(minutes=5)

    total_pv = db.scalar(select(func.count()).select_from(PageView).where(bot_filter)) or 0
    total_uv = db.scalar(select(func.count(func.distinct(PageView.session_id))).select_from(PageView).where(bot_filter)) or 0

    today_pv = db.scalar(
        select(func.count()).select_from(PageView).where(bot_filter, PageView.created_at >= today_start)
    ) or 0
    today_uv = db.scalar(
        select(func.count(func.distinct(PageView.session_id))).select_from(PageView).where(bot_filter, PageView.created_at >= today_start)
    ) or 0

    week_pv = db.scalar(
        select(func.count()).select_from(PageView).where(bot_filter, PageView.created_at >= week_start)
    ) or 0
    week_uv = db.scalar(
        select(func.count(func.distinct(PageView.session_id))).select_from(PageView).where(bot_filter, PageView.created_at >= week_start)
    ) or 0

    # Realtime online (last 5 minutes)
    realtime_online = db.scalar(
        select(func.count(func.distinct(PageView.session_id))).select_from(PageView).where(bot_filter, PageView.created_at >= five_min_ago)
    ) or 0

    # New vs returning visitors (today)
    today_sessions = db.execute(
        select(func.distinct(PageView.session_id)).where(bot_filter, PageView.created_at >= today_start)
    ).scalars().all()
    if today_sessions:
        returning = db.scalar(
            select(func.count(func.distinct(PageView.session_id)))
            .select_from(PageView)
            .where(bot_filter, PageView.session_id.in_(today_sessions), PageView.created_at < today_start)
        ) or 0
        new_visitors = len(today_sessions) - returning
    else:
        new_visitors = 0
        returning = 0

    # Session depth & bounce rate (today)
    session_stats = db.execute(
        select(func.count(PageView.session_id), func.count(func.distinct(PageView.session_id)))
        .select_from(PageView)
        .where(bot_filter, PageView.created_at >= today_start)
    ).first()
    if session_stats:
        total_today_pages, total_today_sessions = session_stats
        avg_depth = round(total_today_pages / total_today_sessions, 2) if total_today_sessions else 0
    else:
        avg_depth = 0

    single_page_sessions = db.scalar(
        select(func.count())
        .select_from(
            select(PageView.session_id)
            .where(bot_filter, PageView.created_at >= today_start)
            .group_by(PageView.session_id)
            .having(func.count() == 1)
            .subquery()
        )
    ) or 0
    bounce_rate = round((single_page_sessions / today_uv) * 100, 1) if today_uv else 0

    # Hourly distribution (today)
    hourly_rows = db.execute(
        select(
            func.extract("hour", PageView.created_at).label("hour"),
            func.count().label("pv"),
        )
        .where(bot_filter, PageView.created_at >= today_start)
        .group_by("hour")
        .order_by("hour")
    ).all()
    hourly = [{"hour": int(row.hour), "pv": row.pv} for row in hourly_rows]

    # Browser distribution (today)
    ua_rows = db.execute(
        select(PageView.user_agent)
        .where(bot_filter, PageView.created_at >= today_start, PageView.user_agent.is_not(None))
    ).scalars().all()
    browsers: dict[str, int] = {}
    for ua in ua_rows:
        ua_lower = ua.lower()
        if "chrome" in ua_lower and "edg" not in ua_lower:
            browsers["Chrome"] = browsers.get("Chrome", 0) + 1
        elif "safari" in ua_lower and "chrome" not in ua_lower:
            browsers["Safari"] = browsers.get("Safari", 0) + 1
        elif "firefox" in ua_lower:
            browsers["Firefox"] = browsers.get("Firefox", 0) + 1
        elif "edg" in ua_lower:
            browsers["Edge"] = browsers.get("Edge", 0) + 1
        elif "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
            browsers["Mobile"] = browsers.get("Mobile", 0) + 1
        else:
            browsers["Other"] = browsers.get("Other", 0) + 1
    browser_dist = sorted([{"name": k, "pv": v} for k, v in browsers.items()], key=lambda x: x["pv"], reverse=True)

    # Top pages
    top_pages_rows = db.execute(
        select(PageView.path, func.count().label("pv"))
        .where(bot_filter)
        .group_by(PageView.path)
        .order_by(desc("pv"))
        .limit(10)
    ).all()
    top_pages = [{"path": row.path, "pv": row.pv} for row in top_pages_rows]

    # Top referrers
    top_refs_rows = db.execute(
        select(PageView.referrer, func.count().label("pv"))
        .where(PageView.referrer.is_not(None), bot_filter)
        .group_by(PageView.referrer)
        .order_by(desc("pv"))
        .limit(10)
    ).all()
    top_referrers = [{"referrer": row.referrer, "pv": row.pv} for row in top_refs_rows]

    # Daily trend (last 14 days)
    day_col = func.date(PageView.created_at).label("day")
    daily_rows = db.execute(
        select(
            day_col,
            func.count().label("pv"),
            func.count(func.distinct(PageView.session_id)).label("uv"),
        )
        .where(bot_filter)
        .group_by(day_col)
        .order_by(desc(day_col))
        .limit(14)
    ).all()
    daily_trend = [{"day": str(row.day), "pv": row.pv, "uv": row.uv} for row in daily_rows]

    # AI Usage stats
    ai_total = db.scalar(select(func.count()).select_from(AIUsageLog).where(AIUsageLog.success == True)) or 0
    ai_today_tokens = db.scalar(
        select(func.coalesce(func.sum(AIUsageLog.total_tokens), 0)).select_from(AIUsageLog)
        .where(AIUsageLog.success == True, AIUsageLog.created_at >= today_start)
    ) or 0
    ai_today_calls = db.scalar(
        select(func.count()).select_from(AIUsageLog)
        .where(AIUsageLog.success == True, AIUsageLog.created_at >= today_start)
    ) or 0
    ai_failures = db.scalar(
        select(func.count()).select_from(AIUsageLog)
        .where(AIUsageLog.success == False, AIUsageLog.created_at >= today_start)
    ) or 0

    # Recent visitor details (last 50 real visitors, bot-filtered)
    visitor_rows = db.execute(
        select(PageView)
        .where(bot_filter)
        .order_by(desc(PageView.created_at))
        .limit(50)
    ).scalars().all()
    visitors = []
    for row in visitor_rows:
        ua = row.user_agent or ""
        ua_lower = ua.lower()
        if "chrome" in ua_lower and "edg" not in ua_lower:
            browser = "Chrome"
        elif "safari" in ua_lower and "chrome" not in ua_lower:
            browser = "Safari"
        elif "firefox" in ua_lower:
            browser = "Firefox"
        elif "edg" in ua_lower:
            browser = "Edge"
        elif "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
            browser = "Mobile"
        else:
            browser = "Other"
        ip_display = row.ip_hash[:12] + "..." if row.ip_hash else "-"
        visitors.append({
            "time": row.created_at.strftime("%m-%d %H:%M") if row.created_at else "-",
            "ip": ip_display,
            "path": row.path,
            "browser": browser,
            "ua": (ua[:80] + "...") if len(ua) > 80 else ua,
            "referrer": (row.referrer[:60] + "...") if row.referrer and len(row.referrer) > 60 else (row.referrer or "-"),
            "session": row.session_id[:8] + "..." if row.session_id else "-",
        })

    return {
        "total_pv": total_pv,
        "total_uv": total_uv,
        "today_pv": today_pv,
        "today_uv": today_uv,
        "week_pv": week_pv,
        "week_uv": week_uv,
        "realtime_online": realtime_online,
        "new_visitors": new_visitors,
        "returning_visitors": returning,
        "avg_depth": avg_depth,
        "bounce_rate": bounce_rate,
        "hourly": hourly,
        "browser_dist": browser_dist,
        "top_pages": top_pages,
        "top_referrers": top_referrers,
        "daily_trend": daily_trend,
        "ai_total_calls": ai_total,
        "ai_today_tokens": ai_today_tokens,
        "ai_today_calls": ai_today_calls,
        "ai_today_failures": ai_failures,
        "visitors": visitors,
    }


def get_token_monitor_stats(db: Session) -> dict:
    from datetime import timedelta

    from app.ai_extractor import get_optimization_stats

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)
    month_start = today_start - timedelta(days=29)

    # Period summaries
    def _period_stats(start: datetime | None = None) -> dict:
        filters = [AIUsageLog.success == True]
        if start:
            filters.append(AIUsageLog.created_at >= start)
        q = select(
            func.count().label("calls"),
            func.coalesce(func.sum(AIUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(AIUsageLog.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("total_tokens"),
        ).where(*filters)
        row = db.execute(q).one()
        fail_q = select(func.count()).select_from(AIUsageLog).where(
            AIUsageLog.success == False, *(f for f in filters if f is not filters[0])
        )
        if start:
            fail_q = fail_q.where(AIUsageLog.created_at >= start)
        failures = db.scalar(fail_q) or 0
        return {
            "calls": row.calls,
            "prompt_tokens": int(row.prompt_tokens),
            "completion_tokens": int(row.completion_tokens),
            "total_tokens": int(row.total_tokens),
            "failures": failures,
            "avg_tokens_per_call": round(int(row.total_tokens) / row.calls, 1) if row.calls else 0,
        }

    # Daily trend (14 days)
    day_col = func.date(AIUsageLog.created_at).label("day")
    daily_rows = db.execute(
        select(
            day_col,
            func.count().label("calls"),
            func.coalesce(func.sum(AIUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(AIUsageLog.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("total_tokens"),
        )
        .where(AIUsageLog.success == True)
        .group_by(day_col)
        .order_by(desc(day_col))
        .limit(14)
    ).all()
    daily_trend = [
        {
            "day": str(row.day),
            "calls": row.calls,
            "prompt_tokens": int(row.prompt_tokens),
            "completion_tokens": int(row.completion_tokens),
            "total_tokens": int(row.total_tokens),
        }
        for row in daily_rows
    ]

    # Hourly trend (24 hours)
    hour_col = func.date_trunc("hour", AIUsageLog.created_at).label("hour") if not settings.uses_sqlite else func.strftime("%Y-%m-%d %H:00", AIUsageLog.created_at).label("hour")
    hourly_rows = db.execute(
        select(
            hour_col,
            func.count().label("calls"),
            func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("total_tokens"),
        )
        .where(AIUsageLog.success == True, AIUsageLog.created_at >= now - timedelta(hours=24))
        .group_by(hour_col)
        .order_by(hour_col)
    ).all()
    hourly_trend = [
        {
            "hour": str(row.hour) if not settings.uses_sqlite else str(row.hour),
            "calls": row.calls,
            "total_tokens": int(row.total_tokens),
        }
        for row in hourly_rows
    ]

    # By source breakdown
    source_rows = db.execute(
        select(
            func.coalesce(AIUsageLog.request_source, "unknown").label("source"),
            func.count().label("calls"),
            func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("total_tokens"),
        )
        .where(AIUsageLog.success == True)
        .group_by("source")
        .order_by(desc("total_tokens"))
        .limit(20)
    ).all()
    by_source = [
        {"source": row.source[:60], "calls": row.calls, "total_tokens": int(row.total_tokens)}
        for row in source_rows
    ]

    # Recent calls (last 50)
    recent_rows = db.scalars(
        select(AIUsageLog).order_by(desc(AIUsageLog.created_at)).limit(50)
    ).all()
    recent_calls = [
        {
            "time": row.created_at.strftime("%m-%d %H:%M") if row.created_at else "-",
            "model": row.model_name,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
            "source": (row.request_source or "")[:60],
            "success": row.success,
            "error": (row.error_message or "")[:80] if not row.success else "",
        }
        for row in recent_rows
    ]

    # By model breakdown
    model_rows = db.execute(
        select(
            AIUsageLog.model_name.label("model"),
            func.count().label("calls"),
            func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("total_tokens"),
        )
        .where(AIUsageLog.success == True)
        .group_by("model")
        .order_by(desc("total_tokens"))
    ).all()
    by_model = [
        {"model": row.model, "calls": row.calls, "total_tokens": int(row.total_tokens)}
        for row in model_rows
    ]

    # Estimated cost (Moonshot/Kimi pricing: input ¥0.012/1K, output ¥0.012/1K)
    cumulative = _period_stats(None)
    estimated_cost_cny = round(
        (cumulative["prompt_tokens"] * 0.012 + cumulative["completion_tokens"] * 0.012) / 1000, 2
    )

    # Monthly cost projection based on current 7-day average
    week_stats = _period_stats(week_start)
    daily_avg_tokens = week_stats["total_tokens"] / 7 if week_stats["calls"] > 0 else 0
    daily_avg_cost = daily_avg_tokens * 0.012 / 1000
    projected_monthly_cost_cny = round(daily_avg_cost * 30, 2)

    # Token rate: tokens per hour (last 24h)
    last_24h = _period_stats(now - timedelta(hours=24))
    tokens_per_hour = round(last_24h["total_tokens"] / 24, 1) if last_24h["calls"] > 0 else 0

    # Budget status
    today_stats = _period_stats(today_start)
    budget_status = {
        "daily_budget": settings.ai_daily_token_budget,
        "daily_used": today_stats["total_tokens"],
        "daily_remaining": max(0, settings.ai_daily_token_budget - today_stats["total_tokens"]) if settings.ai_daily_token_budget > 0 else -1,
        "hourly_budget": settings.ai_hourly_token_budget,
        "hourly_used": last_24h["total_tokens"],
        "hourly_remaining": -1,
    }
    if settings.ai_hourly_token_budget > 0:
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        hourly_used = db.scalar(
            select(func.coalesce(func.sum(AIUsageLog.total_tokens), 0)).where(
                AIUsageLog.success == True, AIUsageLog.created_at >= current_hour_start
            )
        ) or 0
        budget_status["hourly_used"] = int(hourly_used)
        budget_status["hourly_remaining"] = max(0, settings.ai_hourly_token_budget - int(hourly_used))

    # Optimization stats from ai_extractor in-memory counters
    opt_stats = get_optimization_stats()

    return {
        "today": today_stats,
        "week": week_stats,
        "month": _period_stats(month_start),
        "cumulative": cumulative,
        "daily_trend": daily_trend,
        "hourly_trend": hourly_trend,
        "by_source": by_source,
        "by_model": by_model,
        "recent_calls": recent_calls,
        "estimated_cost_cny": estimated_cost_cny,
        "projected_monthly_cost_cny": projected_monthly_cost_cny,
        "tokens_per_hour": tokens_per_hour,
        "budget_status": budget_status,
        "optimization": opt_stats,
    }
