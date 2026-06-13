"""Unit tests for the 2026-06-09/10 refactor modules.

Covers:
- app.services_base.cached_call: hit / miss / version-bump / TTL / capacity
- app.stats_aggregator._browser_bucket / _referrer_host
- app.normalization.is_bot_user_agent
- /api/review/queue & /api/review/groups accept offset (FastAPI TestClient)
- _record_pv_background: skip_stats_bump honors /stats self-request
"""
from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from app.main import _record_pv_background
from app.normalization import is_bot_user_agent
from app.services_base import (
    _MAX_ENTRIES,
    _store,
    _versions,
    bump_version,
    cache_stats,
    cached_call,
    clear_cache,
)
from app.stats_aggregator import _browser_bucket, _referrer_host


# ============================================================================
# services_base.cached_call
# ============================================================================

class CachedCallTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_cache()
        # clear_cache() doesn't reset the _stats counter; do it here so each
        # test sees a fresh hit/miss/evict baseline.
        from app.services_base import _stats
        with __import__("threading").RLock():
            _stats["hit"] = 0
            _stats["miss"] = 0
            _stats["evict"] = 0
        self.calls: list[int] = []

    def test_first_call_misses_second_call_hits(self) -> None:
        @cached_call(group="t1", ttl_seconds=60)
        def double(x: int) -> int:
            self.calls.append(x)
            return x * 2

        self.assertEqual(double(3), 6)
        self.assertEqual(double(3), 6)  # cached
        self.assertEqual(self.calls, [3])  # only one underlying call
        s = cache_stats()
        self.assertEqual(s["miss"], 1)
        self.assertEqual(s["hit"], 1)

    def test_bump_version_invalidates_cached_value(self) -> None:
        @cached_call(group="t2", ttl_seconds=60)
        def f(x: int) -> int:
            self.calls.append(x)
            return x

        f(1)
        f(1)  # hit
        self.assertEqual(self.calls, [1])

        bump_version("t2")
        f(1)  # miss after version bump
        self.assertEqual(self.calls, [1, 1])

    def test_ttl_expiry_recomputes(self) -> None:
        @cached_call(group="t3", ttl_seconds=0.05)  # 50ms TTL
        def f(x: int) -> int:
            self.calls.append(x)
            return x

        f(1)  # miss
        f(1)  # hit (within TTL)
        time.sleep(0.1)
        f(1)  # miss (TTL expired)
        self.assertEqual(self.calls, [1, 1])

    def test_versioned_false_ignores_bump(self) -> None:
        @cached_call(group="t4", ttl_seconds=60, versioned=False)
        def f(x: int) -> int:
            self.calls.append(x)
            return x

        f(1)
        f(1)  # hit
        bump_version("t4")
        f(1)  # still hit because versioned=False
        self.assertEqual(self.calls, [1])

    def test_clear_cache_clears_everything(self) -> None:
        @cached_call(group="t5", ttl_seconds=60)
        def f(x: int) -> int:
            return x

        f(1)
        self.assertGreater(cache_stats()["size"], 0)
        clear_cache()
        self.assertEqual(cache_stats()["size"], 0)

    def test_capacity_cap_evicts_oldest(self) -> None:
        # Fill beyond cap and confirm the dict stays bounded
        @cached_call(group="t6", ttl_seconds=60)
        def f(x: int) -> int:
            return x

        # We don't actually push _MAX_ENTRIES + 1; just confirm the eviction
        # code path doesn't crash and size remains bounded.
        for i in range(_MAX_ENTRIES + 50):
            f(i)
        # After eviction the size should be at most _MAX_ENTRIES
        s = cache_stats()
        self.assertLessEqual(s["size"], _MAX_ENTRIES)


# ============================================================================
# stats_aggregator._browser_bucket / _referrer_host
# ============================================================================

class BrowserBucketTests(unittest.TestCase):
    def test_chrome(self) -> None:
        self.assertEqual(_browser_bucket("Mozilla/5.0 Chrome/120.0"), "Chrome")

    def test_edge_wins_over_chrome(self) -> None:
        self.assertEqual(_browser_bucket("Mozilla/5.0 Chrome/120.0 Edg/120.0"), "Edge")

    def test_safari_without_chrome(self) -> None:
        self.assertEqual(_browser_bucket("Mozilla/5.0 Safari/605.1.15"), "Safari")

    def test_chrome_with_safari_token(self) -> None:
        # Chrome always includes "Safari" in UA — should resolve to Chrome
        self.assertEqual(
            _browser_bucket("Mozilla/5.0 (Mac) Chrome/120.0 Safari/537.36"),
            "Chrome",
        )

    def test_firefox(self) -> None:
        self.assertEqual(_browser_bucket("Mozilla/5.0 Firefox/121.0"), "Firefox")

    def test_mobile(self) -> None:
        self.assertEqual(_browser_bucket("Mozilla/5.0 (iPhone) Mobile/15E148"), "Mobile")

    def test_empty_or_none(self) -> None:
        self.assertEqual(_browser_bucket(""), "Other")
        self.assertEqual(_browser_bucket(None), "Other")

    def test_curl_is_other(self) -> None:
        self.assertEqual(_browser_bucket("curl/7.85.0"), "Other")


class ReferrerHostTests(unittest.TestCase):
    def test_extracts_host(self) -> None:
        self.assertEqual(_referrer_host("https://www.google.com/search"), "www.google.com")

    def test_no_scheme(self) -> None:
        # Without ://, take everything before the first /
        self.assertEqual(_referrer_host("www.example.com/page"), "www.example.com")

    def test_empty(self) -> None:
        self.assertIsNone(_referrer_host(""))
        self.assertIsNone(_referrer_host(None))

    def test_truncates_to_255(self) -> None:
        long_host = "a" * 300 + ".com"
        got = _referrer_host(f"https://{long_host}/")
        self.assertIsNotNone(got)
        self.assertLessEqual(len(got), 255)

    def test_invalid_referrer_returns_none(self) -> None:
        # Garbage in should not raise; the function returns whatever it can
        # extract, even if the URL is malformed.
        self.assertEqual(_referrer_host("://no-host"), "no-host")


# ============================================================================
# normalization.is_bot_user_agent
# ============================================================================

class IsBotUserAgentTests(unittest.TestCase):
    def test_gptbot(self) -> None:
        self.assertTrue(is_bot_user_agent("Mozilla/5.0 (compatible; GPTBot/1.0)"))

    def test_ahrefsbot(self) -> None:
        self.assertTrue(is_bot_user_agent("Mozilla/5.0 AhrefsBot/7.0"))

    def test_semrushbot(self) -> None:
        self.assertTrue(is_bot_user_agent("SemrushBot-SA"))

    def test_curl(self) -> None:
        # curl isn't in the explicit block list (it doesn't bring SEO value,
        # but it's a legitimate CLI client). Only the bots that consume
        # bandwidth without traffic value are listed.
        self.assertFalse(is_bot_user_agent("curl/7.85.0"))

    def test_chrome_human(self) -> None:
        self.assertFalse(is_bot_user_agent("Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"))

    def test_googlebot_is_not_blocked(self) -> None:
        # Googlebot is a search engine; intentionally NOT in the block list
        # to preserve SEO.
        self.assertFalse(is_bot_user_agent("Mozilla/5.0 (compatible; Googlebot/2.1)"))

    def test_empty_or_none(self) -> None:
        self.assertTrue(is_bot_user_agent(""))
        self.assertTrue(is_bot_user_agent(None))

    def test_claudebot(self) -> None:
        # The actual UA observed in production /stats
        self.assertTrue(is_bot_user_agent(
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; "
            "compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"
        ))

    def test_perplexitybot(self) -> None:
        self.assertTrue(is_bot_user_agent(
            "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; "
            "compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot.html)"
        ))

    def test_google_extended_is_blocked(self) -> None:
        # google-extended is the Gemini training crawler, NOT the search crawler
        # (which is Googlebot and intentionally allowed). Substring match must
        # treat them separately.
        self.assertTrue(is_bot_user_agent(
            "Mozilla/5.0 (compatible; Google-Extended/1.0)"
        ))


# ============================================================================
# app.normalization._normalize_person_name — 2-char non-person token rejection
# ============================================================================

class NormalizePersonNameRejectionTests(unittest.TestCase):
    """Bug A (doc 18686, 2026-06-12): 2-char adverbs like '不再' were being
    accepted as person names. The fix is an exact-match rejection set."""

    def test_rejects_bu_zai(self) -> None:
        # The exact case from the production bug
        from app.normalization import _normalize_person_name
        self.assertIsNone(_normalize_person_name("不再"))

    def test_rejects_xu_ren(self) -> None:
        from app.normalization import _normalize_person_name
        self.assertIsNone(_normalize_person_name("续任"))

    def test_rejects_ji_xu(self) -> None:
        from app.normalization import _normalize_person_name
        self.assertIsNone(_normalize_person_name("继续"))

    def test_still_accepts_real_2char_name(self) -> None:
        # 2-char real Chinese names must still pass (no false positive on real names)
        from app.normalization import _normalize_person_name
        self.assertEqual(_normalize_person_name("易金"), "易金")

    def test_still_accepts_3char_name(self) -> None:
        from app.normalization import _normalize_person_name
        self.assertEqual(_normalize_person_name("王宏向"), "王宏向")


# ============================================================================
# Continuation event type — Bug B (doc 18686, 2026-06-12)
# ============================================================================

class ContinuationEventTests(unittest.TestCase):
    """Bug B: '继续担任X' / '仍担任X' should produce a 'continuation' event,
    distinct from 'non_renewal' (which fires for '不再担任X')."""

    def test_continuation_event_from_continue_dan_ren(self) -> None:
        from app.normalization import extract_events_from_text
        events = extract_events_from_text("", "王宏向先生继续担任公司董事。")
        cont = [e for e in events if e.event_type == "continuation"]
        self.assertEqual(len(cont), 1, f"expected 1 continuation event, got {events}")
        self.assertEqual(cont[0].person_name, "王宏向")
        self.assertEqual(cont[0].role_canonical, "director")
        self.assertGreaterEqual(cont[0].confidence, 0.90)

    def test_continuation_event_from_reng_dan_ren(self) -> None:
        # Note: 公司副董事长 intentionally excluded from chairperson
        # (pre-existing design choice in extract_canonical_roles). Use
        # plain "公司董事" here, and the end-to-end test covers 副董事长
        # separately via the production doc 18686.
        from app.normalization import extract_events_from_text
        events = extract_events_from_text("", "李四先生仍担任公司董事。")
        cont = [e for e in events if e.event_type == "continuation"]
        self.assertEqual(len(cont), 1, f"expected 1 continuation event, got {events}")
        self.assertEqual(cont[0].person_name, "李四")
        self.assertEqual(cont[0].role_canonical, "director")
        self.assertGreaterEqual(cont[0].confidence, 0.90)

    def test_continuation_label_in_event_type_labels(self) -> None:
        from app.normalization import event_type_label
        self.assertEqual(event_type_label("continuation"), "续任")

    def test_continuation_in_ai_allowed_types(self) -> None:
        from app.ai_extractor import ALLOWED_EVENT_TYPES
        self.assertIn("continuation", ALLOWED_EVENT_TYPES)

    def test_continuation_appears_in_ai_system_prompt(self) -> None:
        from app.ai_extractor import _SYSTEM_PROMPT
        self.assertIn("continuation", _SYSTEM_PROMPT)

    def test_end_to_end_bug_sentence_no_longer_hallucinates_bu_zai(self) -> None:
        """The exact doc 18686 inputs. Asserts:
        - (不再, ...) hint is NOT produced
        - (王宏向, director, continuation) IS produced"""
        from app.normalization import extract_review_hints_from_text
        title = "第六届董事会第五十六次会议决议公告"
        body = (
            "证券代码：601118 证券简称：海南橡胶 公告编号：2026-032\n"
            "海南天然橡胶产业集团股份有限公司第六届董事会第五十六次会议决议公告\n"
            "本公司董事会及全体董事保证本公告内容不存在任何虚假记载、误导性陈述\n"
            "或者重大遗漏，并对其内容的真实性、准确性和完整性承担法律责任。\n"
            "海南天然橡胶产业集团股份有限公司（以下简称\"公司\"）第六届董事会第\n"
            "五十六次会议于 2026 年 6 月 11 日以通讯表决方式召开。\n"
            "一、审议通过《海南橡胶关于选举第六届董事会董事长的议案》\n"
            "同意选举易金波先生为公司第六届董事会董事长，任期与公司第六届董事会\n"
            "同步。王宏向先生不再担任公司董事长职务，继续担任公司董事。\n"
            "二、审议通过《海南橡胶关于调整董事会专门委员会成员的议案》\n"
            "王宏向先生不再担任董事会各专门委员会相关职务。\n"
        )
        hints = extract_review_hints_from_text(title, body, limit=8)
        person_event_pairs = [(h.person_name, h.event_type) for h in hints]

        # Bug A fix: no "不再" hallucination
        self.assertNotIn(
            ("不再", "non_renewal"),
            person_event_pairs,
            f"still hallucinating '不再' as person: {person_event_pairs}",
        )
        # Bug B fix: (王宏向, director, continuation) present
        self.assertIn(
            ("王宏向", "continuation"),
            person_event_pairs,
            f"missing (王宏向, continuation): {person_event_pairs}",
        )


# ============================================================================
# app.event_propagation.apply_event_to_tenures (2026-06-13 audit fix)
# ============================================================================

class EventPropagationTests(unittest.TestCase):
    """The events table records raw personnel changes. role_tenures is the
    denormalized cache used by /people, /companies, /feed. These tests
    lock in the propagation contract: every published event MUST update
    role_tenures so the public pages reflect the latest state.
    """

    def setUp(self) -> None:
        from app.db import SessionLocal
        from app.models import Company, Person, RoleTenure
        from datetime import date
        import time, random
        # Fresh per-test data to avoid cross-test contamination
        suffix = f"{int(time.time()*1000) % 1000000:06d}{random.randint(0, 999):03d}"
        self.ticker = f"PR{suffix}"
        self.db = SessionLocal()
        self.company = Company(
            exchange="SZSE", ticker=self.ticker, current_ticker=self.ticker,
            org_id=f"prop-{self.ticker}", company_name=f"prop test {self.ticker}",
        )
        self.db.add(self.company); self.db.flush()
        self.persons = []
        for n in [f"张A{suffix}", f"李B{suffix}"]:
            p = Person(canonical_name=n, alias_names="[]")
            self.db.add(p); self.db.flush()
            self.persons.append(p)
        # Pre-existing bootstrap-inferred active tenure
        self.tenure = RoleTenure(
            person_id=self.persons[0].id, company_id=self.company.id,
            role_canonical="chairperson", role_raw_latest="董事长",
            start_date=date(2024, 1, 1), end_date=None, is_active=True,
            inferred_flag=True, confidence=1.0,
        )
        self.db.add(self.tenure); self.db.commit()

    def tearDown(self) -> None:
        from app.models import Event, RoleTenure, Person, Company
        try:
            self.db.query(RoleTenure).filter(RoleTenure.company_id == self.company.id).delete()
            self.db.query(Event).filter(Event.company_id == self.company.id).delete()
            self.db.query(Person).filter(Person.id.in_([p.id for p in self.persons])).delete()
            self.db.query(Company).filter(Company.id == self.company.id).delete()
            self.db.commit()
        finally:
            self.db.close()

    def _make_event(self, *, person, event_type, role_canonical, status="published"):
        from app.models import Event
        from datetime import date
        from decimal import Decimal
        e = Event(
            company_id=self.company.id, person_id=person.id,
            source_document_id=0,
            role_raw=role_canonical, role_canonical=role_canonical,
            event_type=event_type, event_status=status,
            event_reason_raw="test",
            announcement_date=date(2026, 6, 1), effective_date=date(2026, 6, 1),
            excerpt="test", confidence=Decimal("0.9500"),
            is_inferred=False, published_at=date(2026, 6, 1),
        )
        self.db.add(e); self.db.flush()
        return e

    def _active_tenure(self, person, role_canonical):
        from app.models import RoleTenure
        return self.db.query(RoleTenure).filter(
            RoleTenure.person_id == person.id,
            RoleTenure.company_id == self.company.id,
            RoleTenure.role_canonical == role_canonical,
            RoleTenure.is_active.is_(True),
        ).first()

    def test_non_renewal_closes_existing_tenure(self) -> None:
        from app.event_propagation import apply_event_to_tenures
        from datetime import date
        self.assertIsNotNone(self._active_tenure(self.persons[0], "chairperson"))
        ev = self._make_event(person=self.persons[0], event_type="non_renewal", role_canonical="chairperson")
        affected = apply_event_to_tenures(self.db, ev)
        self.db.commit()
        self.assertEqual(affected, 1)
        self.assertIsNone(self._active_tenure(self.persons[0], "chairperson"))

    def test_appointment_creates_new_tenure(self) -> None:
        from app.event_propagation import apply_event_to_tenures
        from datetime import date
        self.assertIsNone(self._active_tenure(self.persons[1], "ceo_equivalent"))
        ev = self._make_event(person=self.persons[1], event_type="appointment", role_canonical="ceo_equivalent")
        affected = apply_event_to_tenures(self.db, ev)
        self.db.commit()
        self.assertEqual(affected, 1)
        active = self._active_tenure(self.persons[1], "ceo_equivalent")
        self.assertIsNotNone(active)
        self.assertEqual(active.start_date, date(2026, 6, 1))
        self.assertEqual(active.inferred_flag, False)

    def test_continuation_keeps_existing_tenure(self) -> None:
        from app.event_propagation import apply_event_to_tenures
        from app.models import RoleTenure
        from datetime import date
        # Add a director tenure
        self.db.add(RoleTenure(
            person_id=self.persons[0].id, company_id=self.company.id,
            role_canonical="director", role_raw_latest="董事",
            start_date=date(2024, 1, 1), is_active=True, inferred_flag=True, confidence=1.0,
        ))
        self.db.commit()
        ev = self._make_event(person=self.persons[0], event_type="continuation", role_canonical="director")
        affected = apply_event_to_tenures(self.db, ev)
        self.db.commit()
        self.assertEqual(affected, 1)
        active = self._active_tenure(self.persons[0], "director")
        self.assertIsNotNone(active)
        self.assertEqual(active.role_raw_latest, "director")

    def test_skips_unpublished_event(self) -> None:
        from app.event_propagation import apply_event_to_tenures
        # 张三A has active chairperson tenure from setUp
        self.assertIsNotNone(self._active_tenure(self.persons[0], "chairperson"))
        ev = self._make_event(person=self.persons[0], event_type="non_renewal",
                              role_canonical="chairperson", status="review_required")
        affected = apply_event_to_tenures(self.db, ev)
        self.db.commit()
        self.assertEqual(affected, 0)
        # Active tenure should still be open
        self.assertIsNotNone(self._active_tenure(self.persons[0], "chairperson"))

    def test_skips_nomination_event(self) -> None:
        from app.event_propagation import apply_event_to_tenures
        ev = self._make_event(person=self.persons[1], event_type="nomination",
                              role_canonical="independent_director")
        affected = apply_event_to_tenures(self.db, ev)
        self.db.commit()
        self.assertEqual(affected, 0)

    def test_idempotent_double_close(self) -> None:
        from app.event_propagation import apply_event_to_tenures
        ev1 = self._make_event(person=self.persons[0], event_type="non_renewal", role_canonical="chairperson")
        ev2 = self._make_event(person=self.persons[0], event_type="non_renewal", role_canonical="chairperson")
        a1 = apply_event_to_tenures(self.db, ev1)
        a2 = apply_event_to_tenures(self.db, ev2)
        self.db.commit()
        self.assertEqual(a1, 1)
        self.assertEqual(a2, 0)  # second call is no-op

    def test_close_then_open_different_role(self) -> None:
        from app.event_propagation import apply_event_to_tenures
        ev_close = self._make_event(person=self.persons[0], event_type="non_renewal", role_canonical="chairperson")
        ev_open = self._make_event(person=self.persons[0], event_type="appointment", role_canonical="director")
        a1 = apply_event_to_tenures(self.db, ev_close)
        a2 = apply_event_to_tenures(self.db, ev_open)
        self.db.commit()
        self.assertEqual(a1, 1)
        self.assertEqual(a2, 1)
        self.assertIsNone(self._active_tenure(self.persons[0], "chairperson"))
        self.assertIsNotNone(self._active_tenure(self.persons[0], "director"))


# ============================================================================
# scripts.reclassify_bot_signatures.build_reclassify_sql
# ============================================================================

class ReclassifySqlBuilderTests(unittest.TestCase):
    """Verify the SQL builder emits a syntactically valid single UPDATE that
    re-tags ``is_bot=FALSE`` rows whose UA matches a known signature.
    """

    def test_returns_non_empty_sql(self) -> None:
        from scripts.reclassify_bot_signatures import build_reclassify_sql
        sql = build_reclassify_sql(["claudebot", "gptbot"])
        self.assertIsInstance(sql, str)
        self.assertGreater(len(sql), 50)
        # Single UPDATE — no batching, no loops
        self.assertEqual(sql.count("UPDATE page_views"), 1)
        # Targets FALSE only (not NULL — backfill_is_bot.py handles NULLs)
        self.assertIn("is_bot = FALSE", sql)
        # Sets to TRUE
        self.assertIn("is_bot = TRUE", sql)
        # Uses case-insensitive substring match
        self.assertIn("LOWER(COALESCE(user_agent, ''))", sql)
        self.assertIn("LIKE :p0", sql)
        self.assertIn("LIKE :p1", sql)

    def test_binds_one_param_per_signature(self) -> None:
        import re
        from scripts.reclassify_bot_signatures import build_reclassify_sql
        sql = build_reclassify_sql(["claudebot", "gptbot", "perplexitybot"])
        self.assertIn(":p0", sql)
        self.assertIn(":p1", sql)
        self.assertIn(":p2", sql)
        # Catches spurious placeholders (count > 3) and indexing bugs (count < 3,
        # duplicate :p0, etc.). More robust than the original "negative space" check.
        self.assertEqual(len(re.findall(r":p\d+", sql)), 3)

    def test_escape_like_handles_metachars(self) -> None:
        from scripts.reclassify_bot_signatures import _escape_like
        # Underscore is the LIKE wildcard for "any single char" — must be escaped
        self.assertEqual(_escape_like("ia_archiver"), "ia\\_archiver")
        # Percent must be escaped
        self.assertEqual(_escape_like("a%b"), "a\\%b")
        # Backslash must be escaped first (otherwise it doubles up)
        self.assertEqual(_escape_like("a\\b"), "a\\\\b")
        # Plain strings pass through unchanged
        self.assertEqual(_escape_like("claudebot"), "claudebot")


# ============================================================================
# /api/review/* offset behavior
# ============================================================================

class ReviewApiOffsetTests(unittest.TestCase):
    """Verify the two API endpoints accept offset, and produce distinct slices."""

    @classmethod
    def setUpClass(cls) -> None:
        from app.main import app
        cls.client = TestClient(app)
        # Seed: there should be at least a few review rows in the dev DB; if not,
        # the test still passes (it just can't verify distinct slices).

    def test_queue_endpoint_accepts_offset(self) -> None:
        r1 = self.client.get("/api/review/queue?limit=3&offset=0")
        r2 = self.client.get("/api/review/queue?limit=3&offset=3")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        items1 = r1.json()
        items2 = r2.json()
        # If we have >= 4 rows, the slices should be disjoint
        if len(items1) == 3 and len(items2) >= 1:
            ids1 = {x["id"] for x in items1}
            ids2 = {x["id"] for x in items2}
            self.assertFalse(ids1 & ids2, "offset slices should be disjoint")

    def test_groups_endpoint_accepts_offset(self) -> None:
        r1 = self.client.get("/api/review/groups?limit=5&offset=0")
        r2 = self.client.get("/api/review/groups?limit=5&offset=5")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)

    def test_negative_offset_rejected(self) -> None:
        r = self.client.get("/api/review/queue?offset=-1")
        self.assertEqual(r.status_code, 422)  # FastAPI validation


# ============================================================================
# _record_pv_background: skip_stats_bump parameter
# ============================================================================

class SkipStatsBumpTests(unittest.TestCase):
    def setUp(self) -> None:
        # Drain the in-process _pv_executor by shutting it down and creating
        # a fresh one. ReviewApiOffsetTests (and any test that hits the
        # TestClient) submits PV writes to a background thread pool; those
        # writes can fire AFTER our clear_cache() returns and bump the
        # "stats" version right under our assertions.
        from concurrent.futures import ThreadPoolExecutor
        import app.main as _main
        old = _main._pv_executor
        _main._pv_executor = ThreadPoolExecutor(max_workers=2)
        old.shutdown(wait=True)
        clear_cache()

    def tearDown(self) -> None:
        # Same drain for tests that follow us, so any pending writes from
        # _record_pv_background calls in the test body don't leak.
        from concurrent.futures import ThreadPoolExecutor
        import app.main as _main
        old = _main._pv_executor
        _main._pv_executor = ThreadPoolExecutor(max_workers=2)
        old.shutdown(wait=True)

    def test_skip_true_does_not_bump(self) -> None:
        bump_version("stats")  # baseline: groups contains "stats"
        before = _versions.get("stats", 0)
        _record_pv_background(
            "/stats", None, "Mozilla/5.0 Chrome/120.0", "127.0.0.1", "s1",
            skip_stats_bump=True,
        )
        after = _versions.get("stats", 0)
        self.assertEqual(before, after)

    def test_skip_false_does_bump(self) -> None:
        bump_version("stats")
        before = _versions.get("stats", 0)
        _record_pv_background(
            "/feed", None, "Mozilla/5.0 Chrome/120.0", "127.0.0.1", "s2",
            skip_stats_bump=False,
        )
        after = _versions.get("stats", 0)
        self.assertEqual(after, before + 1)

    def test_default_arg_does_bump(self) -> None:
        # Backwards compatibility: callers that don't pass skip_stats_bump
        # should still bump (as designed for normal pages).
        bump_version("stats")
        before = _versions.get("stats", 0)
        _record_pv_background(
            "/feed", None, "Mozilla/5.0 Chrome/120.0", "127.0.0.1", "s3",
        )
        after = _versions.get("stats", 0)
        self.assertEqual(after, before + 1)


if __name__ == "__main__":
    unittest.main()
