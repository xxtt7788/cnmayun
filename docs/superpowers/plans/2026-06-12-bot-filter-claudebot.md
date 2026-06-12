# ClaudeBot Filter for /stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the bot detection signature list so ClaudeBot and other AI training crawlers are filtered from `/stats`, and reclassify historical `is_bot=FALSE` rows that should now be bot.

**Architecture:** Single-source-of-truth substring match in `app/normalization._BOT_SIGNATURES` extended with 15 new AI crawler signatures. New operational script `scripts/reclassify_bot_signatures.py` does a one-shot SQL UPDATE for historical cleanup, then triggers `recompute_page_view_daily(days=14)` to refresh the aggregate. No schema changes.

**Tech Stack:** Python 3.11+, SQLAlchemy (text() raw SQL for the bulk update), PostgreSQL 14+ (prod) / SQLite (dev), pytest + unittest.

**Reference spec:** `docs/superpowers/specs/2026-06-12-bot-filter-claudebot-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/normalization.py` | Modify (~614-629) | Add 15 AI crawler signatures to `_BOT_SIGNATURES` |
| `tests/test_refactor_modules.py` | Modify (~186-212) | Add 3 new test cases to `IsBotUserAgentTests` |
| `scripts/reclassify_bot_signatures.py` | Create | One-shot SQL UPDATE + recompute trigger |
| `docs/PROJECT_STATUS.md` | Modify (line ~37) | Add milestone entry |

---

### Task 1: Add failing tests for new bot signatures

**Files:**
- Modify: `tests/test_refactor_modules.py:186-212` (append 3 new test methods to `IsBotUserAgentTests`)

- [ ] **Step 1: Add 3 new test methods to `IsBotUserAgentTests`**

Open `tests/test_refactor_modules.py`. After the existing `test_empty_or_none` method (line 211-212) and before the next `# ===` section header, insert:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run from project root (`D:\myproject\cnmayun`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py::IsBotUserAgentTests -v
```

Expected: 3 new tests FAIL with `AssertionError: False is not true` (because `claudebot`/`perplexitybot`/`google-extended` are not in `_BOT_SIGNATURES` yet). Existing 7 tests in the class still PASS.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_refactor_modules.py
git commit -m "test(bot): add failing cases for ClaudeBot/Perplexity/Google-Extended"
```

---

### Task 2: Extend `_BOT_SIGNATURES` with AI crawlers

**Files:**
- Modify: `app/normalization.py:611-629` (replace the comment + tuple)

- [ ] **Step 1: Replace `_BOT_SIGNATURES` definition**

In `app/normalization.py`, find the existing block (lines 611-629):

```python
# --- Bot detection (shared between middleware write-path and stats read-path) ---
# Substring match (lowercased). Core search engine crawlers (Googlebot, Bingbot,
# Baiduspider, Sogou) are intentionally NOT listed to preserve SEO.
_BOT_SIGNATURES: tuple[str, ...] = (
    "gptbot",                # OpenAI: trains GPT models, no SEO value
    "mj12bot",               # Majestic SEO: link index scraper
    "googleother",           # Google non-search crawler
    "tlm-audit-scanner",     # Unknown scanner
    "ahrefsbot",             # Ahrefs SEO tool
    "semrushbot",            # SEMrush SEO tool
    "dotbot",                # Moz SEO tool
    "yandexbot",             # Yandex (low traffic value for China B2B)
    "exabot",                # Exalead (defunct search engine)
    "facebot",               # Facebook scraper
    "ia_archiver",           # Internet Archive
    "datadog",               # Datadog monitoring crawler
    "uptimerobot",           # Uptime monitoring
    "screaming frog",        # SEO audit tool
)
```

Replace it with:

```python
# --- Bot detection (shared between middleware write-path and stats read-path) ---
# Substring match (lowercased). We follow a "block by default" stance for
# non-SEO crawlers:
#   - AI training / assistant crawlers: no SEO value, train on user content
#   - SEO link-scrapers: no traffic value
# Core search engine crawlers (Googlebot, Bingbot, Baiduspider, Sogou) are
# intentionally NOT listed to preserve SEO.
_BOT_SIGNATURES: tuple[str, ...] = (
    # AI training / assistant crawlers (low/no SEO value)
    "claudebot",              # Anthropic ClaudeBot
    "anthropic-ai",           # Anthropic assistant fetcher
    "perplexitybot",          # Perplexity AI indexer
    "perplexity-user",        # Perplexity user-triggered fetch
    "chatgpt-user",           # OpenAI ChatGPT user-triggered fetch
    "oai-searchbot",          # OpenAI SearchGPT
    "gptbot",                 # OpenAI GPT training crawler
    "google-extended",        # Google Gemini training (NOT a search crawler)
    "applebot-extended",      # Apple Intelligence training
    "amazonbot",              # Amazon AI / Q
    "meta-externalagent",     # Meta AI training
    "ccbot",                  # Common Crawl (feeds many LLM training pipelines)
    "bytespider",             # ByteDance (TikTok) AI training
    "duckassistbot",          # DuckDuckGo AI assist
    "turnitinbot",            # Turnitin (AI-detection crawler)

    # SEO / link-scraping / monitoring bots (no traffic value)
    "mj12bot",                # Majestic SEO link index scraper
    "googleother",            # Google non-search crawler
    "tlm-audit-scanner",      # Unknown scanner
    "ahrefsbot",              # Ahrefs SEO tool
    "semrushbot",             # SEMrush SEO tool
    "dotbot",                 # Moz SEO tool
    "yandexbot",              # Yandex (low traffic value for China B2B)
    "exabot",                 # Exalead (defunct search engine)
    "facebot",                # Facebook scraper
    "ia_archiver",            # Internet Archive
    "datadog",                # Datadog monitoring crawler
    "uptimerobot",            # Uptime monitoring
    "screaming frog",         # SEO audit tool
)
```

- [ ] **Step 2: Run the bot detection tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py::IsBotUserAgentTests -v
```

Expected: all 10 tests PASS (7 original + 3 new). `test_googlebot_is_not_blocked` still passes because `googlebot` is NOT a substring of any new signature.

- [ ] **Step 3: Commit**

```bash
git add app/normalization.py
git commit -m "feat(bot): add 15 AI training crawler signatures to _BOT_SIGNATURES"
```

---

### Task 3: Add failing test for the reclassify SQL builder

**Files:**
- Modify: `tests/test_refactor_modules.py` (add new test class after `IsBotUserAgentTests`)

- [ ] **Step 1: Add the failing test class**

After `IsBotUserAgentTests` and before the next section header, insert:

```python
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
        params = build_reclassify_sql(["claudebot", "gptbot", "perplexitybot"]).bindparams
        # Verify it returns a SQLAlchemy TextClause; the count is exposed via len on the compiled
        # Easier: verify the parameter NAMES are sequential p0..pN
        sql = build_reclassify_sql(["claudebot", "gptbot", "perplexitybot"])
        self.assertIn(":p0", sql)
        self.assertIn(":p1", sql)
        self.assertIn(":p2", sql)
        # AND no spillover to p3
        self.assertNotIn(":p3", sql)
```

- [ ] **Step 2: Run tests to verify the new class fails**

```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py::ReclassifySqlBuilderTests -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.reclassify_bot_signatures'`.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_refactor_modules.py
git commit -m "test(ops): add failing test for reclassify SQL builder"
```

---

### Task 4: Create the reclassify script

**Files:**
- Create: `scripts/reclassify_bot_signatures.py`

- [ ] **Step 1: Create the script**

Create `scripts/reclassify_bot_signatures.py` with the following content (one blank line at end of file):

```python
"""One-off script: reclassify page_views.is_bot from FALSE to TRUE for rows
whose User-Agent now matches an AI training / SEO scraper signature that was
NOT in the original ``_BOT_SIGNATURES`` list at the time the row was written.

Why this exists separately from ``scripts/backfill_is_bot.py``:
  - ``backfill_is_bot.py`` only handles rows where ``is_bot IS NULL``
    (pre-deploy rows that haven't been classified yet).
  - This script handles rows where ``is_bot = FALSE`` but the UA *should* now
    be classified as bot (e.g., ClaudeBot traffic that slipped through before
    we added the signature on 2026-06-12).

Usage:
    cd /opt/china-succession
    source /etc/china-succession/china-succession.env   # loads DATABASE_URL
    /opt/china-succession/.venv/bin/python -m scripts.reclassify_bot_signatures

Idempotent: only flips FALSE -> TRUE. Re-running has no further effect.
"""
from __future__ import annotations

import logging
import os
import sys
import time

from sqlalchemy import text

# Load the production env file before importing app.* (DATABASE_URL lives there).
_ENV_FILE = "/etc/china-succession/china-succession.env"
if os.path.exists(_ENV_FILE) and not os.environ.get("DATABASE_URL"):
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)

# Allow running as a plain script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal  # noqa: E402
from app.normalization import _BOT_SIGNATURES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reclassify_bot_signatures")


def build_reclassify_sql(signatures: tuple[str, ...] | list[str]) -> str:
    """Build a single UPDATE that flips is_bot=FALSE -> TRUE for matching UAs.

    Exposed as a pure function (no DB access) so it can be unit-tested without
    a live database connection. The SQL is dialect-portable: PostgreSQL and
    SQLite both support ``LOWER(x) LIKE :p`` with bound parameters.
    """
    if not signatures:
        raise ValueError("signatures must be non-empty")
    like_clauses = " OR ".join(
        f"LOWER(COALESCE(user_agent, '')) LIKE :p{i}" for i in range(len(signatures))
    )
    return f"""
        UPDATE page_views
        SET is_bot = TRUE
        WHERE is_bot = FALSE
          AND ({like_clauses})
    """.strip()


def main() -> None:
    db = SessionLocal()
    try:
        start = time.monotonic()
        sql = build_reclassify_sql(_BOT_SIGNATURES)
        params = {f"p{i}": f"%{sig}%" for i, sig in enumerate(_BOT_SIGNATURES)}
        log.info(
            "reclassifying with %d signatures (claudebot=%s, gptbot=%s, ...)",
            len(_BOT_SIGNATURES),
            "claudebot" in _BOT_SIGNATURES,
            "gptbot" in _BOT_SIGNATURES,
        )
        result = db.execute(text(sql), params)
        db.commit()
        log.info(
            "re-tagged %d rows as bot (FALSE -> TRUE), took %.1fs",
            result.rowcount,
            time.monotonic() - start,
        )

        # Refresh the daily aggregate so /stats reflects the change immediately,
        # without waiting for the next sync-notices cycle (≤30 min).
        from app.stats_aggregator import recompute_page_view_daily
        agg_start = time.monotonic()
        rows_upserted = recompute_page_view_daily(db, days=14)
        log.info(
            "recomputed page_view_daily (14-day window, %d rows upserted, %.1fs)",
            rows_upserted,
            time.monotonic() - agg_start,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the SQL builder test to verify it passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py::ReclassifySqlBuilderTests -v
```

Expected: both tests in `ReclassifySqlBuilderTests` PASS.

- [ ] **Step 3: Smoke-test the script imports cleanly (no execution)**

```bash
.venv/Scripts/python.exe -c "import scripts.reclassify_bot_signatures; print('OK', len(scripts.reclassify_bot_signatures._BOT_SIGNATURES), 'signatures')"
```

Expected output: `OK 28 signatures` (15 AI + 13 SEO/link — `gptbot` moved from the SEO group to the AI group, so the net add is 14 not 15).

- [ ] **Step 4: Commit**

```bash
git add scripts/reclassify_bot_signatures.py
git commit -m "feat(ops): add reclassify_bot_signatures script for historical cleanup"
```

---

### Task 5: Full regression sweep + PROJECT_STATUS update

**Files:**
- Modify: `docs/PROJECT_STATUS.md` (add milestone row in the timeline table, around line 47)

- [ ] **Step 1: Run the full refactor test suite**

```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py -v
```

Expected: ALL tests PASS, including the 3 new bot cases (test_claudebot, test_perplexitybot, test_google_extended_is_blocked) and 2 new SQL builder cases. No regressions in cache / aggregator / API offset / PV bump-skip tests.

If anything fails: STOP, debug, do not proceed to Step 2.

- [ ] **Step 2: Add milestone to PROJECT_STATUS.md**

In `docs/PROJECT_STATUS.md`, find the timeline table (around line 37) and add a new row after the 2026-06-11 entry:

```markdown
| 2026-06-12 | 访问统计 bot 过滤加固：`_BOT_SIGNATURES` 新增 15 个 AI 训练爬虫签名（含 ClaudeBot/PerplexityBot/Google-Extended），核心 SEO 爬虫保留放行；`scripts/reclassify_bot_signatures.py` 一键回填历史 `is_bot=FALSE` 误判行 + 触发 14 天 rollup 刷新 | ✅ |
```

- [ ] **Step 3: Commit the status update**

```bash
git add docs/PROJECT_STATUS.md
git commit -m "docs(status): record ClaudeBot filter milestone"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ Signatures extended → Task 2
- ✅ Reclassify script + recompute trigger → Task 4
- ✅ Tests for ClaudeBot, Perplexity, Google-Extended, Googlebot preservation → Task 1
- ✅ Operational runbook (deploy steps) → covered in spec, not plan (the plan is the runbook for the engineer)
- ✅ PROJECT_STATUS update → Task 5
- ✅ "显式不做" (403, /stats UI, robots.txt, /feed rate limit) — explicit non-goals, no tasks needed

**2. Placeholder scan:** No TBD/TODO/"implement later". All code blocks are complete and runnable.

**3. Type consistency:**
- `build_reclassify_sql` is defined in Task 4 and tested in Task 3. Signature is `tuple[str, ...] | list[str]` returning `str`. ✓
- `_BOT_SIGNATURES` is `tuple[str, ...]` — `tuple | list` parameter is correct.
- `recompute_page_view_daily(db, days=14)` — matches `app/stats_aggregator.py:69` signature. ✓
- Test class names: `IsBotUserAgentTests`, `ReclassifySqlBuilderTests` — used consistently.

**4. No spec gaps found.**
