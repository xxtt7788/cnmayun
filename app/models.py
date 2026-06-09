from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("exchange", "ticker", name="uq_company_exchange_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16))
    ticker: Mapped[str] = mapped_column(String(32))
    current_ticker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_l1: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_l2: Mapped[str | None] = mapped_column(Text, nullable=True)
    province: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_segment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    listed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_representative: Mapped[str | None] = mapped_column(Text, nullable=True)
    general_manager_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    office_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_owned_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    baseline_status: Mapped[str] = mapped_column(String(32), default="pending")
    baseline_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source_documents: Mapped[list["SourceDocument"]] = relationship(back_populates="company")
    events: Mapped[list["Event"]] = relationship(back_populates="company")
    tenures: Mapped[list["RoleTenure"]] = relationship(back_populates="company")
    metrics: Mapped[list["CompanyMetricDaily"]] = relationship(back_populates="company")
    executive_snapshots: Mapped[list["ExecutiveSnapshot"]] = relationship(back_populates="company")
    watchlists: Mapped[list["Watchlist"]] = relationship(back_populates="company")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(Text)
    external_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    alias_names: Mapped[str] = mapped_column(Text, default="[]")
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    events: Mapped[list["Event"]] = relationship(back_populates="person")
    tenures: Mapped[list["RoleTenure"]] = relationship(back_populates="person")
    executive_snapshots: Mapped[list["ExecutiveSnapshot"]] = relationship(back_populates="person")
    watchlists: Mapped[list["Watchlist"]] = relationship(back_populates="person")
    profiles: Mapped[list["PersonProfile"]] = relationship(back_populates="person")


class PersonProfile(Base):
    __tablename__ = "person_profiles"
    __table_args__ = (
        UniqueConstraint("person_id", "source_document_id", "profile_name", name="uq_profile_person_document_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    profile_name: Mapped[str] = mapped_column(Text)
    identity_key: Mapped[str] = mapped_column(String(128))
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nationality: Mapped[str | None] = mapped_column(Text, nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    professional_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_positions_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    career_history_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    shareholding_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationship_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    compliance_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_raw: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0.8)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    person: Mapped["Person"] = relationship(back_populates="profiles")
    company: Mapped["Company | None"] = relationship()
    source_document: Mapped["SourceDocument | None"] = relationship()


class BaselineRun(Base):
    __tablename__ = "baseline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(32))
    source_platform: Mapped[str] = mapped_column(String(32), default="CNINFO")
    status: Mapped[str] = mapped_column(String(32), default="running")
    requested_company_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_company_count: Mapped[int] = mapped_column(Integer, default=0)
    success_company_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_company_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    executive_snapshots: Mapped[list["ExecutiveSnapshot"]] = relationship(back_populates="baseline_run")


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(32), default="global")
    status: Mapped[str] = mapped_column(String(32), default="running")
    requested_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    processing_runs: Mapped[list["DocumentProcessingRun"]] = relationship(back_populates="sync_job")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    source_type: Mapped[str] = mapped_column(String(32))
    source_platform: Mapped[str] = mapped_column(String(64))
    external_doc_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    announcement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    publish_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="source_documents")
    events: Mapped[list["Event"]] = relationship(back_populates="source_document")
    review_items: Mapped[list["ReviewQueue"]] = relationship(back_populates="source_document")
    processing_runs: Mapped[list["DocumentProcessingRun"]] = relationship(back_populates="source_document")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"))
    role_raw: Mapped[str] = mapped_column(Text)
    role_canonical: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    event_status: Mapped[str] = mapped_column(String(32), default="published")
    event_reason_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    announcement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    board_approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shareholder_approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    excerpt: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    is_inferred: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="events")
    person: Mapped["Person"] = relationship(back_populates="events")
    source_document: Mapped["SourceDocument"] = relationship(back_populates="events")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="event")
    review_items: Mapped[list["ReviewQueue"]] = relationship(back_populates="event")


class ExecutiveSnapshot(Base):
    __tablename__ = "executive_snapshots"
    __table_args__ = (
        UniqueConstraint("company_id", "human_id", "role_canonical", "snapshot_date", name="uq_snapshot_company_human_role_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True)
    baseline_run_id: Mapped[int | None] = mapped_column(ForeignKey("baseline_runs.id"), nullable=True)
    snapshot_date: Mapped[date] = mapped_column(Date)
    source_platform: Mapped[str] = mapped_column(String(32), default="CNINFO")
    source_api: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    human_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    person_name_raw: Mapped[str] = mapped_column(Text)
    title_raw: Mapped[str] = mapped_column(Text)
    role_canonical: Mapped[str] = mapped_column(String(64))
    role_priority: Mapped[int] = mapped_column(Integer, default=999)
    compensation: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_core_role: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="executive_snapshots")
    person: Mapped["Person"] = relationship(back_populates="executive_snapshots")
    baseline_run: Mapped["BaselineRun"] = relationship(back_populates="executive_snapshots")


class RoleTenure(Base):
    __tablename__ = "role_tenures"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"))
    role_canonical: Mapped[str] = mapped_column(String(64))
    role_raw_latest: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    inferred_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="tenures")
    person: Mapped["Person"] = relationship(back_populates="tenures")


class CompanyMetricDaily(Base):
    __tablename__ = "company_metrics_daily"
    __table_args__ = (UniqueConstraint("company_id", "metric_date", name="uq_company_metric_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    metric_date: Mapped[date] = mapped_column(Date)
    change_count_30d: Mapped[int] = mapped_column(Integer, default=0)
    change_count_90d: Mapped[int] = mapped_column(Integer, default=0)
    mom_change_rate: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    yoy_change_rate: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    stability_score: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    abnormal_turnover_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="metrics")


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(16))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True)
    role_canonical: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company | None"] = relationship(back_populates="watchlists")
    person: Mapped["Person | None"] = relationship(back_populates="watchlists")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="watchlist")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("watchlist_id", "event_id", name="uq_alert_watchlist_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    status: Mapped[str] = mapped_column(String(16), default="new")
    delivery_channel: Mapped[str] = mapped_column(String(32), default="inbox")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    watchlist: Mapped["Watchlist"] = relationship(back_populates="alerts")
    event: Mapped["Event"] = relationship(back_populates="alerts")


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    review_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    reason: Mapped[str] = mapped_column(Text)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    event: Mapped["Event | None"] = relationship(back_populates="review_items")
    source_document: Mapped["SourceDocument | None"] = relationship(back_populates="review_items")


class DocumentProcessingRun(Base):
    __tablename__ = "document_processing_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_job_id: Mapped[int] = mapped_column(ForeignKey("sync_jobs.id"))
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"))
    status: Mapped[str] = mapped_column(String(32), default="discovered")
    classification_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    extracted_event_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sync_job: Mapped["SyncJob"] = relationship(back_populates="processing_runs")
    source_document: Mapped["SourceDocument"] = relationship(back_populates="processing_runs")


class PageView(Base):
    __tablename__ = "page_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(256))
    referrer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64), default="")
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    request_source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    success: Mapped[bool] = mapped_column(default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
