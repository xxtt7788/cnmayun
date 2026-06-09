from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class EventOut(BaseModel):
    id: int
    company_name: str
    company_ticker: str
    person_id: int | None
    person_name: str | None
    role_canonical: str
    event_type: str
    event_status: str
    event_reason_raw: str | None
    announcement_date: date | None
    effective_date: date | None
    confidence: float
    excerpt: str
    source_url: str
    created_at: datetime
    published_at: datetime | None


class CompanyMetricOut(BaseModel):
    metric_date: date
    change_count_30d: int
    change_count_90d: int
    mom_change_rate: float | None
    yoy_change_rate: float | None
    stability_score: float | None
    abnormal_turnover_flag: bool


class CompanyTenureOut(BaseModel):
    person_name: str
    role_canonical: str
    start_date: date | None
    end_date: date | None
    is_active: bool


class ExecutiveSnapshotOut(BaseModel):
    person_id: int | None
    person_name: str
    gender: str | None
    birth_year: int | None
    education: str | None
    title_raw: str
    role_canonical: str
    is_core_role: bool
    compensation: float | None


class CompanyListItemOut(BaseModel):
    exchange: str
    ticker: str
    current_ticker: str | None
    org_id: str | None
    company_name: str
    short_name: str | None
    industry_l1: str | None
    market_segment: str | None
    baseline_status: str
    baseline_last_synced_at: datetime | None
    current_executive_count: int
    core_executive_count: int


class CompanySearchOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CompanyListItemOut]


class PersonListItemOut(BaseModel):
    id: int
    canonical_name: str
    education: str | None
    gender: str | None
    birth_year: int | None
    profile_intro: str | None
    active_role_count: int
    active_company_count: int
    active_roles_summary: list[str]


class PersonSearchOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PersonListItemOut]


class StatusBreakdownItemOut(BaseModel):
    label: str
    count: int
    ratio: float


class CoverageBucketOut(BaseModel):
    label: str
    total_count: int
    synced_count: int
    coverage_rate: float


class RoleCoverageItemOut(BaseModel):
    role_canonical: str
    company_count: int
    coverage_rate: float


class BaselineRunOut(BaseModel):
    id: int
    run_type: str
    status: str
    requested_company_count: int
    processed_company_count: int
    success_company_count: int
    failed_company_count: int
    started_at: datetime
    completed_at: datetime | None


class SyncJobOut(BaseModel):
    id: int
    job_type: str
    scope: str
    status: str
    requested_count: int
    processed_count: int
    success_count: int
    failed_count: int
    started_at: datetime
    completed_at: datetime | None
    notes: str | None


class BaselineSummaryOut(BaseModel):
    total_companies: int
    active_companies: int
    synced_companies: int
    unsynced_companies: int
    current_snapshot_rows: int
    core_snapshot_rows: int
    last_run_status: str | None
    last_run_completed_at: datetime | None


class CompanyDetailOut(BaseModel):
    company_name: str
    short_name: str | None
    ticker: str
    current_ticker: str | None
    exchange: str
    org_id: str | None
    industry_l1: str | None
    website: str | None
    listed_date: date | None
    legal_representative: str | None
    general_manager_name: str | None
    baseline_status: str
    baseline_last_synced_at: datetime | None
    state_owned_flag: bool | None
    metrics: list[CompanyMetricOut]
    active_tenures: list[CompanyTenureOut]
    current_executives: list[ExecutiveSnapshotOut]
    recent_events: list[EventOut]


class PersonTenureOut(BaseModel):
    company_name: str
    ticker: str
    role_canonical: str
    start_date: date | None
    end_date: date | None
    is_active: bool


class PersonProfileOut(BaseModel):
    profile_name: str
    gender: str | None
    birth_year: int | None
    education: str | None
    current_positions_raw: str | None
    career_history_raw: str | None
    resume_raw: str
    source_url: str | None
    confidence: float


class PersonDetailOut(BaseModel):
    id: int
    canonical_name: str
    gender: str | None
    birth_year: int | None
    education: str | None
    notes: str | None
    profile_intro: str | None
    current_positions_raw: str | None
    career_history_raw: str | None
    profiles: list[PersonProfileOut]
    active_roles: list[PersonTenureOut]
    history: list[PersonTenureOut]
    recent_events: list[EventOut]


class OverviewOut(BaseModel):
    total_companies: int
    total_people: int
    total_events: int
    today_changes: int
    baseline: BaselineSummaryOut
    top_churn_companies: list[dict[str, Any]]
    recent_events: list[EventOut]
    watchlist_count: int
    unread_alert_count: int
    pending_review_count: int


class CoverageDashboardOut(BaseModel):
    total_companies: int
    active_companies: int
    synced_companies: int
    unsynced_companies: int
    coverage_rate: float
    total_people: int
    current_snapshot_rows: int
    core_snapshot_rows: int
    status_breakdown: list[StatusBreakdownItemOut]
    exchange_breakdown: list[CoverageBucketOut]
    segment_breakdown: list[CoverageBucketOut]
    role_coverage: list[RoleCoverageItemOut]
    recent_runs: list[BaselineRunOut]
    pending_companies: list[CompanyListItemOut]


class LaunchReadinessOut(BaseModel):
    raw_total_companies: int
    synced_companies: int
    canonical_companies: int
    canonical_zero_snapshot_companies: int
    duplicate_org_id_count: int
    published_event_count: int
    pending_review_count: int
    auth_enabled: bool
    overall_status: str
    blocking_issues: list[str]
    ready_items: list[str]


class RuntimeCheckOut(BaseModel):
    name: str
    status: str
    level: str
    detail: str


class RuntimePreflightOut(BaseModel):
    environment: str
    database_backend: str
    public_base_url: str | None
    overall_status: str
    checks: list[RuntimeCheckOut]


class FeedQueryOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EventOut]


class WatchlistOut(BaseModel):
    id: int
    target_type: str
    display_name: str
    role_canonical: str | None
    company_ticker: str | None
    person_id: int | None
    notes: str | None
    created_at: datetime
    alert_count: int = 0
    unread_alert_count: int = 0


class AlertOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    delivery_channel: str
    watchlist_name: str
    event: EventOut


class ReviewExtractionHintOut(BaseModel):
    person_name: str | None
    role_canonical: str | None
    role_raw: str | None
    event_type: str | None
    excerpt: str
    confidence: float
    source: str
    missing_fields: list[str]


class ReviewQueueItemOut(BaseModel):
    id: int
    source_document_id: int | None = None
    review_type: str
    status: str
    reason: str
    created_at: datetime
    resolved_at: datetime | None
    event: EventOut | None = None
    source_document_title: str | None = None
    source_url: str | None = None
    source_document_excerpt: str | None = None
    extraction_hints: list[ReviewExtractionHintOut] = []


class ProjectMemoryOut(BaseModel):
    version: str
    updated_at: str
    project_name: str
    core_definition: str
    phase_one_product_name: str
    primary_users: list[str]
    core_workflow: list[str]
    product_focus: list[str]
    non_goals: list[str]
    source_of_truth: str


class ExtractionDocumentSummary(BaseModel):
    source_document_id: str
    title: str
    is_management_relevant: bool
    notice_type_raw: str
    notice_type_canonical: str = Field(
        pattern="^(appointment_notice|resignation_notice|board_resolution|shareholder_resolution|reelection_notice|annual_report|other)$"
    )


class ExtractionClassification(BaseModel):
    confidence: float = Field(ge=0, le=1)
    reasons: list[str]


class ExtractionEvent(BaseModel):
    person_name_raw: str
    person_name_normalized: str | None = None
    role_raw: str
    role_canonical: str
    event_type: str
    event_status: str = "confirmed"
    event_reason_raw: str | None = None
    announcement_date: date | None = None
    effective_date: date | None = None
    board_approval_date: date | None = None
    shareholder_approval_date: date | None = None
    continues_other_roles: bool = False
    other_roles_retained_raw: list[str] = []
    predecessor_or_target_role_raw: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_excerpt: str
    evidence_section: str | None = None
    needs_manual_review: bool = False


class NoticeExtractionContract(BaseModel):
    document_summary: ExtractionDocumentSummary
    classification: ExtractionClassification
    events: list[ExtractionEvent]
