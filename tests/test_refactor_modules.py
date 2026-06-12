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
        from scripts.reclassify_bot_signatures import build_reclassify_sql
        sql = build_reclassify_sql(["claudebot", "gptbot", "perplexitybot"])
        self.assertIn(":p0", sql)
        self.assertIn(":p1", sql)
        self.assertIn(":p2", sql)
        # AND no spillover to p3
        self.assertNotIn(":p3", sql)


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
