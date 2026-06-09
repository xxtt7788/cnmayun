from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.ai_extractor import ai_extraction_available, extract_events_with_ai
from app.cninfo import AnnouncementEntry, fetch_binary, fetch_management_announcements
from app.config import settings
from app.document_parser import extract_pdf_text
from app.models import (
    Alert,
    Company,
    CompanyMetricDaily,
    DocumentProcessingRun,
    Event,
    Person,
    ReviewQueue,
    SourceDocument,
    SyncJob,
    Watchlist,
)
from app.normalization import (
    body_has_management_motion,
    event_type_label,
    extract_events_from_text,
    extract_review_hints_from_text,
    extract_person_name_from_title,
    infer_event_type_from_title,
    normalize_title_text,
    role_label,
    should_skip_notice,
)


ROLE_WEIGHT = {
    "chairperson": 1.0,
    "ceo_equivalent": 0.9,
    "cfo_equivalent": 0.8,
    "board_secretary": 0.7,
    "senior_management": 0.6,
    "director": 0.4,
    "independent_director": 0.3,
}


@dataclass(slots=True)
class NoticeBackfillSummary:
    window_count: int
    requested_count: int
    processed_count: int
    success_count: int
    failed_count: int
    failed_window_count: int
    published_event_count: int
    pending_review_count: int


@dataclass(slots=True)
class CandidateConsensus:
    person_name: str
    role_canonical: str
    event_type: str
    excerpt: str
    confidence: float
    source_tags: tuple[str, ...]
    rule_confidence: float | None = None
    ai_confidence: float | None = None


@dataclass(slots=True)
class AutoReviewDecision:
    decision: str
    candidates: list[CandidateConsensus] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.0
    risk_flags: tuple[str, ...] = ()
    rule_candidate_count: int = 0
    ai_candidate_count: int = 0


def _get_or_create_person_by_name(db: Session, person_name: str) -> Person:
    person = db.scalar(select(Person).where(Person.canonical_name == person_name))
    if person:
        return person
    person = Person(canonical_name=person_name)
    db.add(person)
    db.flush()
    return person


def _get_or_create_source_document(db: Session, company: Company, item: AnnouncementEntry) -> SourceDocument:
    document = db.scalar(select(SourceDocument).where(SourceDocument.external_doc_id == item.announcement_id))
    if document:
        document.title = item.title
        document.announcement_date = item.announcement_date
        document.source_url = item.source_url
        document.company_id = company.id
        return document

    document = SourceDocument(
        company_id=company.id,
        source_type="announcement",
        source_platform="CNINFO",
        external_doc_id=item.announcement_id,
        title=item.title,
        announcement_date=item.announcement_date,
        publish_ts=datetime.combine(item.announcement_date, datetime.min.time()),
        source_url=item.source_url,
        raw_text=None,
    )
    db.add(document)
    db.flush()
    return document


def _ensure_processing_run(db: Session, sync_job: SyncJob, source_document: SourceDocument) -> DocumentProcessingRun:
    processing_run = db.scalar(select(DocumentProcessingRun).where(DocumentProcessingRun.source_document_id == source_document.id))
    if processing_run:
        processing_run.sync_job_id = sync_job.id
        processing_run.status = "discovered"
        processing_run.classification_confidence = None
        processing_run.extracted_event_count = 0
        processing_run.notes = None
        return processing_run

    processing_run = DocumentProcessingRun(sync_job_id=sync_job.id, source_document_id=source_document.id, status="discovered")
    db.add(processing_run)
    db.flush()
    return processing_run


def _clear_derived_records_for_document(db: Session, source_document: SourceDocument) -> None:
    event_ids = db.scalars(select(Event.id).where(Event.source_document_id == source_document.id)).all()
    if event_ids:
        db.execute(delete(Alert).where(Alert.event_id.in_(event_ids)))
        db.execute(delete(ReviewQueue).where(ReviewQueue.event_id.in_(event_ids)))
        db.execute(delete(Event).where(Event.id.in_(event_ids)))
    db.execute(delete(ReviewQueue).where(ReviewQueue.source_document_id == source_document.id))


def _ensure_review_item(
    db: Session,
    *,
    review_type: str,
    reason: str,
    event: Event | None = None,
    source_document: SourceDocument | None = None,
) -> None:
    query = select(ReviewQueue).where(
        ReviewQueue.review_type == review_type,
        ReviewQueue.status == "pending",
    )
    if event:
        query = query.where(ReviewQueue.event_id == event.id)
    if source_document:
        query = query.where(ReviewQueue.source_document_id == source_document.id)
    existing = db.scalar(query)
    if existing:
        existing.reason = reason
        return
    db.add(
        ReviewQueue(
            event_id=event.id if event else None,
            source_document_id=source_document.id if source_document else None,
            review_type=review_type,
            status="pending",
            reason=reason,
        )
    )


def _candidate_key(person_name: str, role_canonical: str, event_type: str) -> tuple[str, str, str]:
    return person_name, role_canonical, event_type


def _merge_candidate_consensus(rule_candidates, ai_candidates) -> list[CandidateConsensus]:
    merged: dict[tuple[str, str, str], CandidateConsensus] = {}
    for source_tag, source_candidates in (("规则", rule_candidates), ("AI", ai_candidates)):
        for candidate in source_candidates:
            key = _candidate_key(candidate.person_name, candidate.role_canonical, candidate.event_type)
            existing = merged.get(key)
            if not existing:
                merged[key] = CandidateConsensus(
                    person_name=candidate.person_name,
                    role_canonical=candidate.role_canonical,
                    event_type=candidate.event_type,
                    excerpt=candidate.excerpt,
                    confidence=candidate.confidence,
                    source_tags=(source_tag,),
                    rule_confidence=candidate.confidence if source_tag == "规则" else None,
                    ai_confidence=candidate.confidence if source_tag == "AI" else None,
                )
                continue
            source_tags = tuple(dict.fromkeys((*existing.source_tags, source_tag)))
            existing.source_tags = source_tags
            existing.rule_confidence = candidate.confidence if source_tag == "规则" else existing.rule_confidence
            existing.ai_confidence = candidate.confidence if source_tag == "AI" else existing.ai_confidence
            if len(candidate.excerpt) > len(existing.excerpt):
                existing.excerpt = candidate.excerpt
            existing.confidence = min(
                0.99,
                max(existing.confidence, candidate.confidence) + (0.02 if len(source_tags) >= 2 else 0.0),
            )
    return sorted(
        merged.values(),
        key=lambda item: (-item.confidence, item.role_canonical, item.person_name, item.event_type),
    )


def _review_risk_flags(
    title: str,
    body_text: str,
    merged_candidates: list[CandidateConsensus],
    rule_candidates,
    ai_candidates,
) -> tuple[str, ...]:
    if not merged_candidates:
        return ()

    normalized = normalize_title_text(f"{title}\n{body_text}")
    flags: list[str] = []
    if len({item.person_name for item in merged_candidates}) > 1:
        flags.append("多人公告")
    if len({item.role_canonical for item in merged_candidates}) > 1:
        flags.append("多角色公告")
    if len({item.event_type for item in merged_candidates}) > 1:
        flags.append("多事件类型")
    if any(item.event_type in {"nomination", "reelection"} for item in merged_candidates):
        flags.append("换届/提名高风险")
    if any(token in normalized for token in ("候选人", "换届", "累积投票")):
        flags.append("候选人或换届语境")
    if "提名委员会" in normalized and any(item.event_type == "nomination" for item in merged_candidates):
        flags.append("提名委员会公告")

    rule_keys = {_candidate_key(item.person_name, item.role_canonical, item.event_type) for item in rule_candidates}
    ai_keys = {_candidate_key(item.person_name, item.role_canonical, item.event_type) for item in ai_candidates}
    if rule_keys and ai_keys and rule_keys != ai_keys:
        flags.append("规则与AI不一致")
    if any("AI" in item.source_tags and "规则" not in item.source_tags for item in merged_candidates):
        flags.append("AI单独命中")
    if any(item.confidence < settings.low_confidence_threshold for item in merged_candidates):
        flags.append("候选置信度不足")

    deduped: list[str] = []
    for flag in flags:
        if flag not in deduped:
            deduped.append(flag)
    return tuple(deduped)


def _candidate_summary_lines(merged_candidates: list[CandidateConsensus]) -> list[str]:
    return [
        (
            f"{index}. {candidate.person_name} / {role_label(candidate.role_canonical)} / "
            f"{event_type_label(candidate.event_type)} / 来源={'+'.join(candidate.source_tags)} / "
            f"置信度={candidate.confidence:.2f} / 证据={candidate.excerpt}"
        )
        for index, candidate in enumerate(merged_candidates, 1)
    ]


def _manual_review_reason(
    title: str,
    body_text: str,
    header: str,
    merged_candidates: list[CandidateConsensus],
    risk_flags: tuple[str, ...],
    *,
    rule_candidate_count: int,
    ai_candidate_count: int,
) -> str:
    lines = [
        header,
        f"规则命中 {rule_candidate_count} 条，AI 命中 {ai_candidate_count} 条。",
    ]
    if risk_flags:
        lines.append(f"触发人工复核原因：{'；'.join(risk_flags)}。")
    if merged_candidates:
        lines.append("候选事件：")
        lines.extend(_candidate_summary_lines(merged_candidates[:6]))
        return "\n".join(lines)

    hints = extract_review_hints_from_text(title, body_text, limit=5)
    if hints:
        lines.append("系统提取到以下待确认线索：")
        for index, hint in enumerate(hints, 1):
            missing = "、".join(hint.missing_fields) if hint.missing_fields else "无"
            lines.append(
                f"{index}. 人员={hint.person_name or '未稳定提取'}；角色={hint.role_raw or '未稳定提取'}；"
                f"事件={hint.event_type or '未稳定提取'}；缺失={missing}；证据={hint.excerpt}"
            )
    return "\n".join(lines)


def evaluate_notice_auto_review(title: str, body_text: str) -> AutoReviewDecision:
    if should_skip_notice(title, body_text):
        return AutoReviewDecision(
            decision="auto_reject",
            reason="自动审核判定：忽略。正文属于非人事变动公告或程序性治理公告。",
            confidence=0.98,
        )

    rule_candidates = extract_events_from_text(title, body_text)
    # Pass max rule confidence and count to AI extractor for smart-skip optimization
    rule_max_conf = max((c.confidence for c in rule_candidates), default=None) if rule_candidates else None
    ai_candidates = extract_events_with_ai(title, body_text, rule_confidence=rule_max_conf, rule_candidate_count=len(rule_candidates)) if ai_extraction_available() else []
    merged_candidates = _merge_candidate_consensus(rule_candidates, ai_candidates)
    title_event_type = infer_event_type_from_title(title)
    title_person_name = extract_person_name_from_title(title)
    risk_flags = _review_risk_flags(title, body_text, merged_candidates, rule_candidates, ai_candidates)

    if not merged_candidates:
        if ai_extraction_available() and (body_has_management_motion(body_text) or title_event_type or title_person_name):
            return AutoReviewDecision(
                decision="auto_reject",
                reason="自动审核判定：忽略。正文出现人事议案线索，但规则与AI均未形成包含人员、角色、事件类型的可发布事件。",
                confidence=0.82,
                rule_candidate_count=len(rule_candidates),
                ai_candidate_count=len(ai_candidates),
            )
        if body_has_management_motion(body_text) or title_event_type or title_person_name:
            return AutoReviewDecision(
                decision="manual_review",
                reason=_manual_review_reason(
                    title,
                    body_text,
                    "自动审核判定：需人工复核。正文出现人事议案线索，但未能稳定形成事件。",
                    merged_candidates,
                    risk_flags,
                    rule_candidate_count=len(rule_candidates),
                    ai_candidate_count=len(ai_candidates),
                ),
                confidence=0.45,
                risk_flags=risk_flags,
                rule_candidate_count=len(rule_candidates),
                ai_candidate_count=len(ai_candidates),
            )
        return AutoReviewDecision(
            decision="auto_reject",
            reason="自动审核判定：忽略。正文未发现可落地的人事变动事件。",
            confidence=0.72,
            rule_candidate_count=len(rule_candidates),
            ai_candidate_count=len(ai_candidates),
        )

    simple_event_types = {"appointment", "resignation", "removal", "interim_assignment", "title_change", "non_renewal", "retirement"}
    simple_document = all(candidate.event_type in simple_event_types for candidate in merged_candidates)
    single_candidate = len(merged_candidates) == 1
    high_confidence = all(candidate.confidence >= settings.low_confidence_threshold for candidate in merged_candidates)
    high_support = bool(ai_candidates) and all(len(candidate.source_tags) >= 2 for candidate in merged_candidates)
    rule_only_high_confidence = bool(rule_candidates) and not ai_candidates and all(candidate.confidence >= 0.95 for candidate in merged_candidates)
    severe_risk_flags = set(risk_flags) - {"多人公告", "多角色公告"}

    if simple_document and high_confidence and not severe_risk_flags and (high_support or rule_only_high_confidence):
        return AutoReviewDecision(
            decision="auto_publish",
            candidates=merged_candidates,
            reason="自动审核判定：直接发布。普通任免事件风险较低，且规则与AI结果一致或单事件规则命中极高置信。",
            confidence=max(candidate.confidence for candidate in merged_candidates),
            risk_flags=risk_flags,
            rule_candidate_count=len(rule_candidates),
            ai_candidate_count=len(ai_candidates),
        )

    return AutoReviewDecision(
        decision="manual_review",
        candidates=merged_candidates,
        reason=_manual_review_reason(
            title,
            body_text,
            "自动审核判定：需人工复核。候选事件已形成，但存在歧义或风险，不自动发布。",
            merged_candidates,
            risk_flags,
            rule_candidate_count=len(rule_candidates),
            ai_candidate_count=len(ai_candidates),
        ),
        confidence=sum(candidate.confidence for candidate in merged_candidates) / len(merged_candidates),
        risk_flags=risk_flags,
        rule_candidate_count=len(rule_candidates),
        ai_candidate_count=len(ai_candidates),
    )


def _create_alerts_for_event(db: Session, event: Event) -> None:
    watchlists = db.scalars(select(Watchlist)).all()
    for watchlist in watchlists:
        matched = False
        if watchlist.target_type == "company" and watchlist.company_id == event.company_id:
            matched = True
        elif watchlist.target_type == "person" and watchlist.person_id and watchlist.person_id == event.person_id:
            matched = True
        elif watchlist.target_type == "role" and watchlist.role_canonical == event.role_canonical:
            matched = True
        if not matched:
            continue
        exists = db.scalar(select(Alert).where(Alert.watchlist_id == watchlist.id, Alert.event_id == event.id))
        if exists:
            continue
        db.add(Alert(watchlist_id=watchlist.id, event_id=event.id))


def _upsert_event_from_notice(
    db: Session,
    *,
    company: Company,
    source_document: SourceDocument,
    role_canonical: str,
    event_type: str,
    person_name: str,
    excerpt: str,
    confidence: float,
    event_status: str | None = None,
    event_reason_raw: str | None = None,
) -> Event:
    person = _get_or_create_person_by_name(db, person_name)
    existing = db.scalar(
        select(Event).where(
            Event.company_id == company.id,
            Event.source_document_id == source_document.id,
            Event.role_canonical == role_canonical,
            Event.event_type == event_type,
            Event.person_id == person.id,
        )
    )
    final_status = event_status or ("published" if confidence >= settings.low_confidence_threshold else "review_required")
    if existing:
        existing.person_id = person.id
        existing.role_raw = role_canonical
        existing.event_status = final_status
        existing.event_reason_raw = event_reason_raw
        existing.announcement_date = source_document.announcement_date
        existing.effective_date = source_document.announcement_date
        existing.excerpt = excerpt
        existing.confidence = Decimal(f"{confidence:.4f}")
        existing.published_at = datetime.utcnow() if final_status == "published" else None
        return existing

    event = Event(
        company_id=company.id,
        person_id=person.id,
        source_document_id=source_document.id,
        role_raw=role_canonical,
        role_canonical=role_canonical,
        event_type=event_type,
        event_status=final_status,
        event_reason_raw=event_reason_raw,
        announcement_date=source_document.announcement_date,
        effective_date=source_document.announcement_date,
        excerpt=excerpt,
        confidence=Decimal(f"{confidence:.4f}"),
        is_inferred=False,
        published_at=datetime.utcnow() if final_status == "published" else None,
    )
    db.add(event)
    db.flush()
    return event


def _load_document_text(source_document: SourceDocument) -> str:
    pdf_bytes = fetch_binary(source_document.source_url)
    body_text = extract_pdf_text(pdf_bytes)
    source_document.raw_text = body_text or ""
    return body_text


def _mark_processing_for_review(
    db: Session,
    *,
    source_document: SourceDocument,
    processing_run: DocumentProcessingRun,
    reason: str,
    confidence: float,
) -> tuple[int, int]:
    processing_run.status = "review_required"
    processing_run.classification_confidence = Decimal(f"{confidence:.4f}")
    processing_run.notes = reason
    _ensure_review_item(
        db,
        review_type="document_triage",
        reason=reason,
        source_document=source_document,
    )
    return 0, 1


def reprocess_pending_review_documents(db: Session, limit: int = 100) -> tuple[int, int, int]:
    review_ids = list(
        db.scalars(
            select(ReviewQueue.id)
            .where(ReviewQueue.status == "pending", ReviewQueue.source_document_id.is_not(None))
            .order_by(desc(ReviewQueue.created_at))
            .limit(limit)
        ).all()
    )
    processed_count = 0
    created_count = 0
    review_count = 0
    for review_id in review_ids:
        result = reprocess_review_item(db, review_id)
        if result is None:
            continue
        processed_count += 1
        created_count += result[0]
        review_count += result[1]
        db.flush()
    recompute_company_metrics(db)
    return processed_count, created_count, review_count


def recompute_company_metrics(db: Session, metric_date: date | None = None) -> None:
    metric_date = metric_date or date.today()
    ninety_days_ago = metric_date - timedelta(days=90)
    thirty_days_ago = metric_date - timedelta(days=30)
    companies = db.scalars(select(Company).where(Company.is_active.is_(True))).all()
    for company in companies:
        events = db.scalars(
            select(Event).where(
                Event.company_id == company.id,
                Event.announcement_date >= ninety_days_ago,
                Event.event_status == "published",
            )
        ).all()
        count_90d = len(events)
        count_30d = len([event for event in events if event.announcement_date and event.announcement_date >= thirty_days_ago])
        weighted_sum = sum(ROLE_WEIGHT.get(event.role_canonical, 0.3) for event in events)
        stability_score = max(20.0, round(100 - weighted_sum * 12, 2))
        abnormal_turnover = count_30d >= 4 or weighted_sum >= 4.0

        metric = db.scalar(
            select(CompanyMetricDaily).where(
                CompanyMetricDaily.company_id == company.id,
                CompanyMetricDaily.metric_date == metric_date,
            )
        )
        if not metric:
            metric = CompanyMetricDaily(company_id=company.id, metric_date=metric_date)
            db.add(metric)
        metric.change_count_30d = count_30d
        metric.change_count_90d = count_90d
        metric.mom_change_rate = Decimal("0.0000")
        metric.yoy_change_rate = Decimal("0.0000")
        metric.stability_score = Decimal(f"{stability_score:.4f}")
        metric.abnormal_turnover_flag = abnormal_turnover


def sync_management_notices(
    db: Session,
    days_back: int | None = None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    page_limit: int | None = None,
    keywords: tuple[str, ...] | list[str] | None = None,
) -> SyncJob:
    notices = fetch_management_announcements(
        days_back=days_back,
        start_date=start_date,
        end_date=end_date,
        page_limit=page_limit,
        keywords=keywords,
    )
    sync_job = SyncJob(
        job_type="notice_ingest",
        scope="management_announcements",
        status="running",
        requested_count=len(notices),
    )
    db.add(sync_job)
    db.flush()

    for item in notices:
        sync_job.processed_count += 1
        try:
            _process_announcement(db, sync_job, item)
        except Exception as exc:
            sync_job.failed_count += 1
            sync_job.notes = f"{(sync_job.notes or '').strip()}\n{item.announcement_id}: {exc}".strip()
        db.flush()

    recompute_company_metrics(db)
    sync_job.status = "completed_with_errors" if sync_job.failed_count else "completed"
    sync_job.completed_at = datetime.utcnow()
    return sync_job


def backfill_management_notices(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    window_days: int = 30,
    page_limit: int | None = None,
    keywords: tuple[str, ...] | list[str] | None = None,
) -> NoticeBackfillSummary:
    requested_count = 0
    processed_count = 0
    success_count = 0
    failed_count = 0
    window_count = 0
    failed_window_count = 0
    cursor = start_date
    while cursor <= end_date:
        window_end = min(cursor + timedelta(days=window_days - 1), end_date)
        try:
            run = sync_management_notices(
                db,
                start_date=cursor,
                end_date=window_end,
                page_limit=page_limit,
                keywords=keywords,
            )
            requested_count += run.requested_count
            processed_count += run.processed_count
            success_count += run.success_count
            failed_count += run.failed_count
        except Exception:
            failed_window_count += 1
            db.rollback()
        window_count += 1
        cursor = window_end + timedelta(days=1)
    published_event_count = db.scalar(select(func.count()).select_from(Event).where(Event.event_status == "published")) or 0
    pending_review_count = db.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.status == "pending")) or 0
    return NoticeBackfillSummary(
        window_count=window_count,
        requested_count=requested_count,
        processed_count=processed_count,
        success_count=success_count,
        failed_count=failed_count,
        failed_window_count=failed_window_count,
        published_event_count=published_event_count,
        pending_review_count=pending_review_count,
    )


def retry_failed_company(db: Session, ticker: str) -> bool:
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if not company:
        return False
    company.baseline_status = "pending"
    company.baseline_last_synced_at = None
    return True


def reset_review_item(db: Session, review_id: int, *, status: str, notes: str | None = None) -> ReviewQueue | None:
    item = db.get(ReviewQueue, review_id)
    if not item:
        return None
    item.status = status
    item.resolution_notes = notes
    item.resolved_at = datetime.utcnow()
    if item.event:
        item.event.event_status = "published" if status == "approved" else "rejected"
        if status == "approved":
            item.event.published_at = datetime.utcnow()
    return item


def reset_review_document(db: Session, source_document_id: int, *, status: str, notes: str | None = None) -> int:
    items = db.scalars(
        select(ReviewQueue)
        .where(ReviewQueue.source_document_id == source_document_id, ReviewQueue.status == "pending")
        .order_by(desc(ReviewQueue.created_at))
    ).all()
    resolved_count = 0
    for item in items:
        reset_review_item(db, item.id, status=status, notes=notes)
        resolved_count += 1
    return resolved_count


def reprocess_review_document(db: Session, source_document_id: int) -> tuple[int, int] | None:
    review_id = db.scalar(
        select(ReviewQueue.id)
        .where(ReviewQueue.source_document_id == source_document_id, ReviewQueue.status == "pending")
        .order_by(desc(ReviewQueue.created_at))
    )
    if not review_id:
        return None
    return reprocess_review_item(db, review_id)


def _process_announcement(db: Session, sync_job: SyncJob, item: AnnouncementEntry) -> tuple[int, int]:
    company = db.scalar(select(Company).where(Company.ticker == item.sec_code))
    if not company:
        sync_job.failed_count += 1
        notes = (sync_job.notes or "").strip()
        sync_job.notes = f"{notes}\n{item.sec_code}: 未找到公司主表记录".strip()
        return 0, 0

    source_document = _get_or_create_source_document(db, company, item)
    processing_run = _ensure_processing_run(db, sync_job, source_document)
    _clear_derived_records_for_document(db, source_document)

    try:
        body_text = _load_document_text(source_document)
    except Exception as exc:
        sync_job.success_count += 1
        return _mark_processing_for_review(
            db,
            source_document=source_document,
            processing_run=processing_run,
            reason=f"公告命中候选范围，但 PDF 正文解析失败，需人工查看原文。错误：{exc}",
            confidence=0.20,
        )

    processing_run.status = "parsed"
    decision = evaluate_notice_auto_review(item.title, body_text)

    if decision.decision == "auto_reject":
        processing_run.status = "ignored"
        processing_run.classification_confidence = Decimal(f"{decision.confidence:.4f}")
        processing_run.notes = decision.reason
        sync_job.success_count += 1
        return 0, 0

    if not decision.candidates:
        sync_job.success_count += 1
        return _mark_processing_for_review(
            db,
            source_document=source_document,
            processing_run=processing_run,
            reason=decision.reason,
            confidence=decision.confidence,
        )

    created_count = 0
    review_count = 0
    publish_directly = decision.decision == "auto_publish"
    event_status = "published" if publish_directly else "review_required"
    for candidate in decision.candidates:
        event = _upsert_event_from_notice(
            db,
            company=company,
            source_document=source_document,
            role_canonical=candidate.role_canonical,
            event_type=candidate.event_type,
            person_name=candidate.person_name,
            excerpt=candidate.excerpt,
            confidence=candidate.confidence,
            event_status=event_status,
            event_reason_raw=decision.reason,
        )
        created_count += 1
        if event.event_status == "published":
            _create_alerts_for_event(db, event)
            continue
        review_count += 1
        _ensure_review_item(
            db,
            review_type="event_validation",
            reason=decision.reason,
            event=event,
            source_document=source_document,
        )

    processing_run.status = "published" if publish_directly else "review_required"
    processing_run.classification_confidence = Decimal(f"{decision.confidence:.4f}")
    processing_run.extracted_event_count = created_count
    processing_run.notes = decision.reason
    sync_job.success_count += 1
    return created_count, review_count


def reprocess_review_item(db: Session, review_id: int) -> tuple[int, int] | None:
    review_item = db.get(ReviewQueue, review_id)
    if not review_item or not review_item.source_document:
        return None

    source_document = review_item.source_document
    company = source_document.company
    body_text = source_document.raw_text or ""
    if not body_text:
        body_text = _load_document_text(source_document)

    _clear_derived_records_for_document(db, source_document)
    decision = evaluate_notice_auto_review(source_document.title, body_text)

    if decision.decision == "auto_reject":
        review_item.status = "resolved"
        review_item.resolution_notes = decision.reason
        review_item.resolved_at = datetime.utcnow()
        return 0, 0

    if not decision.candidates:
        _ensure_review_item(
            db,
            review_type="document_triage",
            reason=decision.reason,
            source_document=source_document,
        )
        return 0, 1

    created_count = 0
    review_count = 0
    publish_directly = decision.decision == "auto_publish"
    event_status = "published" if publish_directly else "review_required"
    for candidate in decision.candidates:
        event = _upsert_event_from_notice(
            db,
            company=company,
            source_document=source_document,
            role_canonical=candidate.role_canonical,
            event_type=candidate.event_type,
            person_name=candidate.person_name,
            excerpt=candidate.excerpt,
            confidence=candidate.confidence,
            event_status=event_status,
            event_reason_raw=decision.reason,
        )
        created_count += 1
        if event.event_status == "published":
            _create_alerts_for_event(db, event)
            continue
        review_count += 1
        _ensure_review_item(
            db,
            review_type="event_validation",
            reason=decision.reason,
            event=event,
            source_document=source_document,
        )

    review_item.status = "resolved"
    review_item.resolution_notes = f"重新抽取完成，结果：{decision.decision}"
    review_item.resolved_at = datetime.utcnow()
    return created_count, review_count
