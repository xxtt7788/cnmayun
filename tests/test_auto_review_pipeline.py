from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.cninfo import AnnouncementEntry
from app.db import Base
from app.models import Company, Event, Person, ReviewQueue, SourceDocument, SyncJob
from app.normalization import ExtractedEventCandidate
from app.notice_pipeline import _process_announcement, evaluate_notice_auto_review, reset_review_document
from app.services import list_review_document_groups
from tests.test_notice_extraction import DOC_882_BODY, DOC_882_TITLE, DOC_904_BODY, DOC_904_TITLE, DOC_912_BODY, DOC_912_TITLE


class AutoReviewDecisionTests(unittest.TestCase):
    def test_single_person_appointment_can_auto_publish(self) -> None:
        decision = evaluate_notice_auto_review(DOC_904_TITLE, DOC_904_BODY)
        self.assertEqual(decision.decision, "auto_publish")
        self.assertEqual(len(decision.candidates), 1)
        self.assertEqual(decision.candidates[0].person_name, "曹锐")

    def test_non_management_notice_can_auto_reject(self) -> None:
        decision = evaluate_notice_auto_review(DOC_912_TITLE, DOC_912_BODY)
        self.assertEqual(decision.decision, "auto_reject")
        self.assertEqual(decision.candidates, [])

    def test_multi_person_nomination_keeps_manual_review(self) -> None:
        decision = evaluate_notice_auto_review(DOC_882_TITLE, DOC_882_BODY)
        self.assertEqual(decision.decision, "manual_review")
        self.assertGreaterEqual(len(decision.candidates), 2)
        self.assertIn("多人公告", decision.risk_flags)

    def test_multi_person_simple_appointments_can_auto_publish_when_ai_agrees(self) -> None:
        candidates = [
            ExtractedEventCandidate("王亮", "senior_management", "appointment", "同意聘任王亮先生担任公司副总经理", 0.96),
            ExtractedEventCandidate("李明", "cfo_equivalent", "appointment", "同意聘任李明先生担任公司财务总监", 0.96),
        ]
        with (
            patch("app.notice_pipeline.extract_events_from_text", return_value=candidates),
            patch("app.notice_pipeline.ai_extraction_available", return_value=True),
            patch("app.notice_pipeline.extract_events_with_ai", return_value=candidates),
        ):
            decision = evaluate_notice_auto_review("关于聘任高级管理人员的公告", "同意聘任王亮先生、李明先生担任公司高级管理人员。")

        self.assertEqual(decision.decision, "auto_publish")
        self.assertEqual(len(decision.candidates), 2)

    def test_multi_person_rule_only_high_confidence_can_auto_publish(self) -> None:
        candidates = [
            ExtractedEventCandidate("王亮", "senior_management", "appointment", "聘任王亮为公司副总经理", 0.96),
            ExtractedEventCandidate("李明", "cfo_equivalent", "appointment", "聘任李明为公司财务总监", 0.96),
        ]
        with (
            patch("app.notice_pipeline.extract_events_from_text", return_value=candidates),
            patch("app.notice_pipeline.ai_extraction_available", return_value=True),
            patch("app.notice_pipeline.extract_events_with_ai", return_value=[]),
        ):
            decision = evaluate_notice_auto_review("关于聘任高级管理人员的公告", "聘任王亮、李明为公司高级管理人员。")

        self.assertEqual(decision.decision, "auto_publish")
        self.assertEqual(len(decision.candidates), 2)

    def test_ai_available_no_candidate_management_motion_can_auto_reject(self) -> None:
        with (
            patch("app.notice_pipeline.extract_events_from_text", return_value=[]),
            patch("app.notice_pipeline.ai_extraction_available", return_value=True),
            patch("app.notice_pipeline.extract_events_with_ai", return_value=[]),
        ):
            decision = evaluate_notice_auto_review("关于聘任公司副总经理的议案", "审议通过关于聘任公司副总经理的议案。")

        self.assertEqual(decision.decision, "auto_reject")


class NoticePipelineFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_company_and_job(self):
        db = self.SessionLocal()
        company = Company(
            exchange="SZSE",
            ticker="000001",
            current_ticker="000001",
            company_name="测试公司",
            is_active=True,
        )
        sync_job = SyncJob(job_type="notice_sync", scope="global", status="running")
        db.add(company)
        db.add(sync_job)
        db.commit()
        db.refresh(company)
        db.refresh(sync_job)
        return db, company, sync_job

    def test_process_announcement_publishes_low_risk_event(self) -> None:
        db, company, sync_job = self._seed_company_and_job()
        item = AnnouncementEntry(
            announcement_id="doc-904",
            sec_code=company.ticker,
            sec_name=company.company_name,
            org_id=None,
            title=DOC_904_TITLE,
            announcement_date=date(2026, 4, 25),
            adjunct_url="/mock.pdf",
            source_url="https://example.com/doc-904",
            column_id=None,
            announcement_type="board_resolution",
        )
        with patch("app.notice_pipeline._load_document_text", return_value=DOC_904_BODY):
            created_count, review_count = _process_announcement(db, sync_job, item)

        self.assertEqual((created_count, review_count), (1, 0))
        db.flush()
        events = db.scalars(select(Event)).all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_status, "published")
        self.assertIn("自动审核判定：直接发布", events[0].event_reason_raw or "")
        pending_review = db.scalars(select(ReviewQueue).where(ReviewQueue.status == "pending")).all()
        self.assertEqual(pending_review, [])
        db.close()

    def test_process_announcement_routes_high_risk_notice_to_review(self) -> None:
        db, company, sync_job = self._seed_company_and_job()
        item = AnnouncementEntry(
            announcement_id="doc-882",
            sec_code=company.ticker,
            sec_name=company.company_name,
            org_id=None,
            title=DOC_882_TITLE,
            announcement_date=date(2026, 4, 25),
            adjunct_url="/mock.pdf",
            source_url="https://example.com/doc-882",
            column_id=None,
            announcement_type="board_resolution",
        )
        with patch("app.notice_pipeline._load_document_text", return_value=DOC_882_BODY):
            created_count, review_count = _process_announcement(db, sync_job, item)

        self.assertEqual(created_count, 7)
        self.assertEqual(review_count, 7)
        db.flush()
        events = db.scalars(select(Event)).all()
        self.assertTrue(events)
        self.assertTrue(all(event.event_status == "review_required" for event in events))
        pending_review = db.scalars(select(ReviewQueue).where(ReviewQueue.status == "pending")).all()
        self.assertEqual(len(pending_review), 7)
        self.assertTrue(all("人工复核" in item.reason for item in pending_review))
        db.close()

    def test_review_queue_groups_multiple_events_under_one_document(self) -> None:
        db, company, _sync_job = self._seed_company_and_job()
        document = SourceDocument(
            company_id=company.id,
            source_type="announcement",
            source_platform="CNINFO",
            external_doc_id="doc-group",
            title="关于聘任高级管理人员的公告",
            announcement_date=date(2026, 4, 25),
            source_url="https://example.com/doc-group",
            raw_text="聘任王亮先生担任董事长。聘任张鹏先生担任副总经理。",
        )
        person_a = Person(canonical_name="王亮")
        person_b = Person(canonical_name="张鹏")
        db.add_all([document, person_a, person_b])
        db.flush()
        event_a = Event(
            company_id=company.id,
            person_id=person_a.id,
            source_document_id=document.id,
            role_raw="董事长",
            role_canonical="chairman",
            event_type="appointment",
            event_status="review_required",
            announcement_date=date(2026, 4, 25),
            excerpt="聘任王亮先生担任董事长",
            confidence=Decimal("0.8200"),
        )
        event_b = Event(
            company_id=company.id,
            person_id=person_b.id,
            source_document_id=document.id,
            role_raw="副总经理",
            role_canonical="senior_management",
            event_type="appointment",
            event_status="review_required",
            announcement_date=date(2026, 4, 25),
            excerpt="聘任张鹏先生担任副总经理",
            confidence=Decimal("0.8100"),
        )
        db.add_all([event_a, event_b])
        db.flush()
        db.add_all(
            [
                ReviewQueue(
                    event_id=event_a.id,
                    source_document_id=document.id,
                    review_type="event_validation",
                    status="pending",
                    reason="多人公告需人工复核。",
                ),
                ReviewQueue(
                    event_id=event_b.id,
                    source_document_id=document.id,
                    review_type="event_validation",
                    status="pending",
                    reason="多人公告需人工复核。",
                ),
            ]
        )
        db.commit()

        groups = list_review_document_groups(db)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["source_document_id"], document.id)
        self.assertEqual(groups[0]["review_count"], 2)
        self.assertEqual(groups[0]["event_count"], 2)
        self.assertEqual(len(groups[0]["reasons"]), 1)
        db.close()

    def test_reset_review_document_resolves_all_pending_items(self) -> None:
        db, company, _sync_job = self._seed_company_and_job()
        document = SourceDocument(
            company_id=company.id,
            source_type="announcement",
            source_platform="CNINFO",
            external_doc_id="doc-reset",
            title="关于聘任财务总监的公告",
            announcement_date=date(2026, 4, 25),
            source_url="https://example.com/doc-reset",
            raw_text="聘任李明先生担任财务总监。",
        )
        person = Person(canonical_name="李明")
        db.add_all([document, person])
        db.flush()
        event = Event(
            company_id=company.id,
            person_id=person.id,
            source_document_id=document.id,
            role_raw="财务总监",
            role_canonical="cfo_equivalent",
            event_type="appointment",
            event_status="review_required",
            announcement_date=date(2026, 4, 25),
            excerpt="聘任李明先生担任财务总监",
            confidence=Decimal("0.7800"),
        )
        db.add(event)
        db.flush()
        db.add(
            ReviewQueue(
                event_id=event.id,
                source_document_id=document.id,
                review_type="event_validation",
                status="pending",
                reason="置信度不足需人工复核。",
            )
        )
        db.commit()

        resolved_count = reset_review_document(db, document.id, status="approved", notes="测试通过")
        db.commit()

        self.assertEqual(resolved_count, 1)
        self.assertEqual(db.get(Event, event.id).event_status, "published")
        self.assertEqual(db.scalar(select(ReviewQueue.status)), "approved")
        db.close()


if __name__ == "__main__":
    unittest.main()
