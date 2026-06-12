# Continuation Event + 2-Char Non-Person Token Rejection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two bugs in the AI extraction pipeline exposed by doc 18686: (A) 2-char adverbs like "不再" treated as person names, (B) "继续担任X" / "仍担任X" continuing-in-role relationships not extracted. Also add a new `continuation` event type (label: 续任).

**Architecture:**
- Bug A: Add `_NON_PERSON_2CHAR_TOKENS` set in `app/normalization.py`; reject exact 2-char match in `_normalize_person_name`.
- Bug B: Add `EVENT_PATTERNS` entry for "继续|仍)担任" mapping to new `continuation` event_type. Add `"continuation": "续任"` to `EVENT_TYPE_LABELS`. Add `"continuation"` to `ALLOWED_EVENT_TYPES`. Update AI system prompt.

**Tech Stack:** Python 3.11+, regex, pytest + unittest.

**Reference spec:** `docs/superpowers/specs/2026-06-12-continuation-event-and-adverb-rejection-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/normalization.py` | Modify (~90, 112-168, 290-310) | Add `_NON_PERSON_2CHAR_TOKENS`, new EVENT_PATTERN, EVENT_TYPE_LABELS entry, infer_event_type_from_title branch |
| `app/ai_extractor.py` | Modify (~40-76) | Add `continuation` to ALLOWED_EVENT_TYPES, update _SYSTEM_PROMPT |
| `tests/test_refactor_modules.py` | Modify | Add ~9 new test cases across 2 new test classes |

---

### Task 1: Add failing tests for Bug A (2-char non-person token rejection)

**Files:**
- Modify: `tests/test_refactor_modules.py` (add a new test class for `_normalize_person_name`)

- [ ] **Step 1: Add the new test class**

Find the `IsBotUserAgentTests` class (around line 186) and add a new test class AFTER it (before the existing `ReclassifySqlBuilderTests` class). Insert this section header and class:

```python
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
```

- [ ] **Step 2: Run the new test class to verify failure**

```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py::NormalizePersonNameRejectionTests -v
```

Expected: 3 new tests FAIL (`test_rejects_bu_zai`, `test_rejects_xu_ren`, `test_rejects_ji_xu`); 2 sanity tests PASS (`test_still_accepts_real_2char_name`, `test_still_accepts_3char_name`).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_refactor_modules.py
git commit -m "test(extraction): add failing tests for 2-char non-person token rejection"
```

---

### Task 2: Implement Bug A in `app/normalization.py`

**Files:**
- Modify: `app/normalization.py:85-92` (add `_NON_PERSON_2CHAR_TOKENS` near `INVALID_PERSON_TOKENS`)
- Modify: `app/normalization.py:346-365` (add rejection check in `_normalize_person_name`)

- [ ] **Step 1: Add the token set**

In `app/normalization.py`, immediately after the existing `INVALID_PERSON_TOKENS` tuple at line 92, add:

```python
INVALID_PERSON_TOKENS = ("第", "届", "董事会", "监事会", "委员会", "公司", "议案", "公告", "候选人", "专门会议")

# 2-char non-person tokens: exact-match rejection. These are common 2-char
# adverbs / function words that look like Chinese names (2 Chinese chars)
# but are never actually person names. Doc 18686 / 2026-06-12 bug surfaced
# "不再" being accepted as a person name.
_NON_PERSON_2CHAR_TOKENS: frozenset[str] = frozenset({
    # 否定 / 继续类副词
    "不再", "续任", "仍在", "继续", "持续",
    "原有", "原任", "原系", "原拟", "原为",
    "前为", "前述",
    # 仍 X 系
    "仍由", "仍将", "仍任", "仍系",
    # 易误识的虚词
    "本人", "该等", "其他", "其余",
    "上述", "如下", "如上",
    "本次", "本届", "本期", "本项",
    "该人", "对方", "他人",
})
```

- [ ] **Step 2: Add the rejection check in `_normalize_person_name`**

In `_normalize_person_name` (around line 346-365), find the block:

```python
    if re.fullmatch(r"[一-龥]{2,4}", normalized):
        if any(token in normalized for token in INVALID_PERSON_TOKENS):
            return None
        if any(token in normalized for token in ("经理", "董事", "委员", "主席", "主持", "列席")):
            return None
        if any(token in normalized for token in ("声明", "名单", "议案", "报告")):
            return None
        return normalized
```

Add a new check between `INVALID_PERSON_TOKENS` and the "经理/董事" check:

```python
    if re.fullmatch(r"[一-龥]{2,4}", normalized):
        if any(token in normalized for token in INVALID_PERSON_TOKENS):
            return None
        # Bug A fix: reject 2-char adverbs / function words that are
        # valid Chinese chars but never person names. Exact match
        # (only when length == 2) to avoid false positives on 3+ char names.
        if len(normalized) == 2 and normalized in _NON_PERSON_2CHAR_TOKENS:
            return None
        if any(token in normalized for token in ("经理", "董事", "委员", "主席", "主持", "列席")):
            return None
        if any(token in normalized for token in ("声明", "名单", "议案", "报告")):
            return None
        return normalized
```

- [ ] **Step 3: Run the test class to verify all 5 pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py::NormalizePersonNameRejectionTests -v
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add app/normalization.py
git commit -m "fix(extraction): reject 2-char adverbs/function words as person names"
```

---

### Task 3: Add failing tests for Bug B (continuation event)

**Files:**
- Modify: `tests/test_refactor_modules.py` (add a second new test class after `NormalizePersonNameRejectionTests`)

- [ ] **Step 1: Add the new test class**

After the `NormalizePersonNameRejectionTests` class (around line 232 after Task 1/2), add:

```python
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
        from app.normalization import extract_events_from_text
        events = extract_events_from_text("", "李四先生仍担任公司副董事长。")
        cont = [e for e in events if e.event_type == "continuation"]
        self.assertEqual(len(cont), 1, f"expected 1 continuation event, got {events}")
        self.assertEqual(cont[0].person_name, "李四")
        self.assertEqual(cont[0].role_canonical, "chairperson")
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
```

- [ ] **Step 2: Run the new test class to verify all fail (RED phase)**

```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py::ContinuationEventTests -v
```

Expected: ALL 6 tests FAIL (event_type "continuation" doesn't exist yet, so label test fails, ALLOWED_EVENT_TYPES missing it, AI prompt missing it, EVENT_PATTERNS missing the pattern). The end-to-end test will fail because (王宏向, continuation) isn't produced.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_refactor_modules.py
git commit -m "test(events): add failing tests for continuation event type"
```

---

### Task 4: Implement Bug B (continuation event)

**Files:**
- Modify: `app/normalization.py:17-27` (add to `EVENT_TYPE_LABELS`)
- Modify: `app/normalization.py:112-168` (add new EVENT_PATTERNS entry)
- Modify: `app/normalization.py:285-310` (add to `infer_event_type_from_title`)
- Modify: `app/ai_extractor.py:40-50` (add to `ALLOWED_EVENT_TYPES`)
- Modify: `app/ai_extractor.py:73-76` (update `_SYSTEM_PROMPT`)

- [ ] **Step 1: Add `continuation` to `EVENT_TYPE_LABELS`**

In `app/normalization.py` around line 17-27, add a new line in alphabetical / logical order:

```python
EVENT_TYPE_LABELS = {
    "appointment": "任命",
    "continuation": "续任",        # ← new (Bug B)
    "resignation": "辞职",
    "removal": "免职",
    "reelection": "换届连任",
    "interim_assignment": "代行职责",
    "title_change": "职务调整",
    "nomination": "提名",
    "non_renewal": "未续任",
    "retirement": "退休离任",
}
```

- [ ] **Step 2: Add the new EVENT_PATTERNS entry**

After the last `EVENT_PATTERNS` entry (the `retirement` pattern at line 164-167), add a new entry:

```python
    (
        "continuation",
        r"(?P<name>[一-龥]{2,4})(先生|女士)?(?:继续|仍)担任(?P<role>[^，,。.;；\n]{0,24})",
        0.92,
    ),
```

- [ ] **Step 3: Update `infer_event_type_from_title`**

Around line 285-310 in `app/normalization.py`, find the function. Add a branch for continuation. The simplest insertion is right after the `reelection` check (or wherever fits logically):

```python
    if "继续担任" in normalized or "仍担任" in normalized or "续任" in normalized:
        return "continuation"
```

- [ ] **Step 4: Add `continuation` to `ALLOWED_EVENT_TYPES`**

In `app/ai_extractor.py:40-50`, add `"continuation"` to the set:

```python
ALLOWED_EVENT_TYPES = {
    "appointment",
    "continuation",       # ← new
    "resignation",
    "removal",
    "reelection",
    "interim_assignment",
    "title_change",
    "nomination",
    "non_renewal",
    "retirement",
}
```

- [ ] **Step 5: Update `_SYSTEM_PROMPT`**

In `app/ai_extractor.py:73-76`, update the event list:

```python
_SYSTEM_PROMPT = """从A股公告提取人事变动。忽略列席/委员会/担保/章程/分红等。
角色:chairperson|ceo_equivalent|cfo_equivalent|board_secretary|senior_management|director|independent_director
事件:appointment|continuation|resignation|removal|reelection|interim_assignment|title_change|nomination|non_renewal|retirement
返:{"events":[{"p":"名","r":"原职","c":"角色","e":"事件","x":"原文片段"}]}"""
```

- [ ] **Step 6: Run the new test class to verify all 6 pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_refactor_modules.py::ContinuationEventTests -v
```

Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add app/normalization.py app/ai_extractor.py
git commit -m "feat(events): add continuation event type for '继续担任/仍担任' patterns"
```

---

### Task 5: Full regression + PROJECT_STATUS update

**Files:**
- Modify: `tests/` (no edits, just run)
- Modify: `docs/PROJECT_STATUS.md` (add milestone row)

- [ ] **Step 1: Run the full test suite**

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: ALL tests PASS. Original 56 + 5 new (Task 1 sanity + 2 char rejections) + 1 sanity (3-char still works) = 58, then + 6 from Task 3 = 64? Actually let me recount:
- Original: 38 in test_refactor_modules + 18 elsewhere = 56
- Task 1: +5 (3 reject + 2 sanity)
- Task 3: +6 (continuation tests)
- New total: 56 + 5 + 6 = 67

If anything fails, STOP and debug.

- [ ] **Step 2: Add milestone to PROJECT_STATUS.md**

In `docs/PROJECT_STATUS.md`, find the latest 2026-06-12 row (around line 48 — the data/ cleanup row) and add a new row after it:

```markdown
| 2026-06-12 | 审核队列 bug 修复：`_normalize_person_name` 拒绝 2-字常见虚词（"不再"等不再被当人名）；新增 `continuation` 事件类型（标签"续任"）识别"继续担任X/仍担任X"保留关系。源 bug：doc 18686（海南橡胶决议公告）。 | ✅ |
```

- [ ] **Step 3: Commit**

```bash
git add docs/PROJECT_STATUS.md
git commit -m "docs(status): record extraction bug fix milestone"
```

---

### Task 6: Deploy + verify on production

**Files:**
- Use the existing `_prod_deploy.py` approach (recreate the pattern, or use the same script flow as today's ClaudeBot filter deploy)

- [ ] **Step 1: Build deploy zip locally** (Python equivalent of `package_for_server.ps1`, with the same exclusion list updated in today's work)

Use the deploy script pattern from today's ClaudeBot filter work. The Python script excludes `.git`, `.pyc.NNN` lock files, `data/`, etc. It builds a ~10MB zip and uploads via SFTP.

- [ ] **Step 2: Extract on server via rsync (as china-succession, no --delete)**

- [ ] **Step 3: Restart service**

```bash
sudo systemctl restart china-succession-web.service
```

- [ ] **Step 4: Verify on production**

Upload a small verify script via SFTP, run on production:

```python
# Expected: 0 hints with person_name="不再"
# Expected: doc 18686 now has hint (王宏向, director, continuation)
```

Run the same `extract_review_hints_from_text` call that was used to reproduce the bug locally, and assert the new outputs.

- [ ] **Step 5: Commit the deployment verification (if a verify script was used)**

---

## Self-Review

**1. Spec coverage:**
- ✅ Bug A: 2-char non-person token rejection — Tasks 1, 2
- ✅ Bug B: continuation event type — Tasks 3, 4
- ✅ EVENT_TYPE_LABELS / ALLOWED_EVENT_TYPES / AI prompt updated — Task 4
- ✅ End-to-end test for doc 18686 — Task 3
- ✅ Deploy + verify on production — Task 6
- ✅ PROJECT_STATUS update — Task 5

**2. Placeholder scan:** No TBD/TODO. All code blocks are complete and runnable.

**3. Type consistency:** 
- `_NON_PERSON_2CHAR_TOKENS` is `frozenset[str]`, consistent with other constants.
- EVENT_PATTERNS tuple structure unchanged.
- `ALLOWED_EVENT_TYPES` set gets one new entry.
- `event_type_label("continuation")` test will pass after Task 4.

**4. No spec gaps found.**
