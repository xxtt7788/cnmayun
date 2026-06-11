# AI 提取器人名修复 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复两个 AI 提取人名的 bug：(1) 议案标题句不再生成"缺失字段：人员姓名" hint；(2) AI 路径与规则路径共用同一套人名校验，杜绝"经公"类假人名。

**Architecture:** 三处 TDD 改动 — 1 行短路 + 1 个正则扩展 + 1 个委托函数，全部回退友好。

**Tech Stack:** Python 3.11、unittest、re（无新依赖）。

**Spec:** `docs/superpowers/specs/2026-06-11-ai-extractor-person-name-fixes-design.md`

---

## 文件结构

- **Modify** `app/normalization.py` — 加 2 行短路（Issue 1）+ 修改 1 行正则（Issue 2A）
- **Modify** `app/ai_extractor.py` — 加 1 个 import + 替换 1 个函数（Issue 2B）
- **Modify** `tests/test_notice_extraction.py` — 追加 3 个测试
- **Modify** `docs/PROJECT_STATUS.md` — 顶部加一条 entry

---

## Task 1: 议案标题句不再生成 hint（Issue 1 修复）

**Files:**
- Modify: `app/normalization.py:556-602` (在 `extract_review_hints_from_text` 中)
- Modify: `tests/test_notice_extraction.py` (追加测试)

- [ ] **Step 1: 在 `tests/test_notice_extraction.py` 顶部 import 处添加新依赖**

在文件第 5 行 `from app.normalization import extract_events_from_text` 下面追加：

```python
from app.normalization import extract_review_hints_from_text
```

- [ ] **Step 2: 追加测试 `test_vote_summary_without_names_does_not_create_hint`**

在文件末尾 `if __name__ == "__main__":` 之前（即第 77 行的 `class NoticeExtractionTests` 内部最后一个 `test_*` 之后）追加：

```python
    def test_vote_summary_without_names_does_not_create_hint(self) -> None:
        """议案标题句（如"审议通过了《关于提名...的议案》"）含人事关键词但无具体人名，
        不应生成"缺失字段：人员姓名" hint 进入 review 队列。"""
        hints = extract_review_hints_from_text(
            "第十届董事会第十三次会议决议公告",
            "（一）审议通过了《关于提名公司第十一届董事会非独立董事候选人的议案》",
        )
        bad_hints = [
            h for h in hints
            if h.person_name is None and "人员姓名" in h.missing_fields
        ]
        self.assertEqual(bad_hints, [])
```

- [ ] **Step 3: 运行测试确认它失败（红）**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/test_notice_extraction.py::NoticeExtractionTests::test_vote_summary_without_names_does_not_create_hint -v
```

**Expected:** FAIL with `AssertionError: List of bad hints is not empty` — 因为改动还没做。

- [ ] **Step 4: 在 `app/normalization.py` 添加 2 行短路**

打开 `app/normalization.py`，定位到 `extract_review_hints_from_text` 函数（约 556 行起）。找到这行：

```python
        person_names = _extract_hint_person_names(sentence)
```

在它**紧接的下一行**插入以下 2 行：

```python
        # 过滤：句子含人事关键词但无具体人名（如"审议通过了《关于提名...的议案》"），
        # 跳过该句，不生成低信号 hint。
        if not any(person_names):
            continue
```

注意保留函数原有的 4 空格缩进（位于 for 循环内部）。

- [ ] **Step 5: 重新运行测试确认它通过（绿）**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/test_notice_extraction.py::NoticeExtractionTests::test_vote_summary_without_names_does_not_create_hint -v
```

**Expected:** PASS — 议案标题句不再生成 hint。

- [ ] **Step 6: 跑回归套件确认没破其他测试**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/test_notice_extraction.py -v
```

**Expected:** 5 个原有测试 + 1 个新测试全部 PASS。

- [ ] **Step 7: 提交**

```bash
cd /d/myproject/cnmayun
git add app/normalization.py tests/test_notice_extraction.py
git commit -m "fix(review): skip hints with no person name from vote-summary sentences"
```

---

## Task 2: 规则路径拒绝"经公"等假人名（Issue 2A 修复）

**Files:**
- Modify: `app/normalization.py:348` (在 `_normalize_person_name` 中)
- Modify: `tests/test_notice_extraction.py` (追加测试)

- [ ] **Step 1: 追加测试 `test_rule_normalize_rejects_经公`**

在 Task 1 追加的 `test_vote_summary_without_names_does_not_create_hint` 之后追加：

```python
    def test_rule_normalize_rejects_经公(self) -> None:
        """规则路径的 _normalize_person_name 必须拒绝"经公"等由'经'+后随字组成的假人名。
        '经' 作为常见介词不应被当作人名首字。"""
        from app.normalization import _normalize_person_name
        self.assertIsNone(_normalize_person_name("经公"))
        self.assertIsNone(_normalize_person_name("经董事会"))
        self.assertIsNone(_normalize_person_name("经审查"))
        # 真实名字保留
        self.assertEqual(_normalize_person_name("乔胜俊"), "乔胜俊")
        self.assertEqual(_normalize_person_name("张文"), "张文")
```

- [ ] **Step 2: 运行测试确认它失败（红）**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/test_notice_extraction.py::NoticeExtractionTests::test_rule_normalize_rejects_经公 -v
```

**Expected:** FAIL — `assertIsNone(_normalize_person_name("经公"))` 失败，因为当前的正则不含 "经"。

- [ ] **Step 3: 修改 `app/normalization.py` 第 348 行正则**

找到这一行：

```python
        normalized = re.sub(r"^(?:同意|拟|经审查|经审核|经董事会|被提名为|被提名|提名|补选|聘任|任命|选举|选聘|当选|免去|免职|解聘)+", "", normalized).strip()
```

替换为：

```python
        normalized = re.sub(r"^(?:同意|拟|经董事会|经审查|经审核|经|被提名为|被提名|提名|补选|聘任|任命|选举|选聘|当选|免去|免职|解聘)+", "", normalized).strip()
```

**关键改动**：把 `经` 加入备选项，并置于 `经董事会|经审查|经审核` 之后（避免 `经` 提前吃掉三个长前缀的首字符）。

- [ ] **Step 4: 重新运行测试确认它通过（绿）**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/test_notice_extraction.py::NoticeExtractionTests::test_rule_normalize_rejects_经公 -v
```

**Expected:** PASS。

- [ ] **Step 5: 跑回归套件确认没破其他测试**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/ -v
```

**Expected:** 全部 PASS。如果 `test_notice_extraction` 中的 `test_nomination_list_supports_independent_and_english_names` 等含"经公司..."的 case 失败，回滚 Step 3 把 `经` 移除，然后停下分析 — `经` 不应破坏这些 case（这些 case 的"经公司..."在句子中，捕获的 name 是"王振滔"/"张文"/"曹锐"/"李一芃"等，捕获组不含"经"），但若异常需要调查。

- [ ] **Step 6: 提交**

```bash
cd /d/myproject/cnmayun
git add app/normalization.py tests/test_notice_extraction.py
git commit -m "fix(normalization): reject 经-prefixed false names like '经公' in rule path"
```

---

## Task 3: AI 路径委托规则路径校验（Issue 2B 修复）

**Files:**
- Modify: `app/ai_extractor.py:12-20` (加 import)
- Modify: `app/ai_extractor.py:227-235` (替换函数)
- Modify: `tests/test_notice_extraction.py` (追加测试)

- [ ] **Step 1: 追加测试 `test_ai_path_delegates_to_rule_normalize`**

在 Task 2 追加的 `test_rule_normalize_rejects_经公` 之后追加：

```python
    def test_ai_path_delegates_to_rule_normalize(self) -> None:
        """AI 路径的 _normalize_person_name 必须和规则路径完全等价。
        这保证 '经公' 等假人名在 AI 路径下也被拒绝。"""
        from app.ai_extractor import _normalize_person_name as ai_normalize
        from app.normalization import _normalize_person_name as rule_normalize

        # 假人名 — 两条路径都必须返回 None
        for value in ["经公", "经董事会", "经审查", "经审核", "经公司", ""]:
            self.assertIsNone(ai_normalize(value), f"AI path should reject {value!r}")
            self.assertEqual(ai_normalize(value), rule_normalize(value))

        # 真实名字 — 两条路径都必须返回相同的合法名字
        for value in ["乔胜俊", "杜若榕", "王浩", "刘松", "张文", "曹锐"]:
            self.assertEqual(ai_normalize(value), "经".join(value.split("经")) or value)
            self.assertEqual(ai_normalize(value), rule_normalize(value))
```

> 注：`ai_normalize("乔胜俊")` 应等于 `"乔胜俊"`，不是 `"经".join(...)`。最后一条 assert 中 `"经".join(value.split("经")) or value` 仅在 `value` 不含 "经" 时等于 `value` 本身 — 对所有真实名字都成立，所以是个间接 sanity check。如果失败，说明 AI 路径对真实名字有意外处理。

- [ ] **Step 2: 运行测试确认它失败（红）**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/test_notice_extraction.py::NoticeExtractionTests::test_ai_path_delegates_to_rule_normalize -v
```

**Expected:** FAIL — `ai_normalize("经公")` 当前返回 `"经公"`（不是 None），因为 AI 路径的本地函数不含 INVALID_PERSON_TOKENS 检查。

- [ ] **Step 3: 在 `app/ai_extractor.py` 顶部 import 块添加 `_normalize_person_name`**

打开 `app/ai_extractor.py`，找到第 12-20 行的 import 块：

```python
from app.normalization import (
    ExtractedEventCandidate,
    body_has_management_motion,
    extract_canonical_roles,
    extract_events_from_text,
    extract_person_name_from_title,
    infer_event_type_from_title,
    normalize_title_text,
)
```

在 `normalize_title_text,` 之后追加一行：

```python
    normalize_title_text,
    _normalize_person_name,
)
```

- [ ] **Step 4: 替换 `app/ai_extractor.py` 第 227-235 行的 `_normalize_person_name` 函数**

找到这一段：

```python
def _normalize_person_name(raw_name: Any) -> str | None:
    name = normalize_title_text(str(raw_name or ""))
    name = name.replace("先生", "").replace("女士", "").strip()
    if re.fullmatch(r"[一-龥]{2,4}", name):
        return name
    name = re.sub(r"\s+", " ", name)
    if re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{1,40}[A-Za-z]", name):
        return name
    return None
```

**整段替换**为：

```python
def _normalize_person_name(raw_name: Any) -> str | None:
    """委托 app.normalization._normalize_person_name — 统一两路径的人名校验。

    包含前缀剥离（"经"、"经审查"、"经审核"、"经董事会"、"提名"、"聘任"等）、
    INVALID_PERSON_TOKENS 检查、"经理/董事/委员" 后缀检查、
    "声明/名单/议案/报告" 检查、拉丁名 fallback。
    """
    from app.normalization import _normalize_person_name as _rule_normalize
    return _rule_normalize(str(raw_name or ""))
```

**为什么本地函数名仍叫 `_normalize_person_name`？**
- 调用方 (`_candidate_from_ai_payload`) 已用这个名字
- 内部通过 `as _rule_normalize` 别名避免自引用

- [ ] **Step 5: 重新运行测试确认它通过（绿）**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/test_notice_extraction.py::NoticeExtractionTests::test_ai_path_delegates_to_rule_normalize -v
```

**Expected:** PASS。

- [ ] **Step 6: 跑全量回归**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/ -v
```

**Expected:** 全部测试 PASS。

- [ ] **Step 7: 提交**

```bash
cd /d/myproject/cnmayun
git add app/ai_extractor.py tests/test_notice_extraction.py
git commit -m "fix(ai): delegate _normalize_person_name to rule path for unified validation"
```

---

## Task 4: 更新文档 + 最终验证

**Files:**
- Modify: `docs/PROJECT_STATUS.md` (顶部加一条)

- [ ] **Step 1: 在 `docs/PROJECT_STATUS.md` 顶部追加新条目**

打开 `docs/PROJECT_STATUS.md`。在文件最顶部（标题行之后）找到"最新变更"或类似的区块（如果没有则在第一段末尾追加）。追加：

```markdown
- **2026-06-11** — AI 提取器人名修复：议案标题句不再生成低信号 hint；AI 与规则路径共用同一套人名校验，杜绝"经公"类假人名。spec 见 `docs/superpowers/specs/2026-06-11-ai-extractor-person-name-fixes-design.md`。
```

- [ ] **Step 2: 最终全量验证**

```bash
cd /d/myproject/cnmayun
python -m pytest tests/ -v
```

**Expected:** 全部测试 PASS（包括 3 个新测试 + 5 个原有 `test_notice_extraction` + 其他模块测试）。

- [ ] **Step 3: 提交**

```bash
cd /d/myproject/cnmayun
git add docs/PROJECT_STATUS.md
git commit -m "docs: note AI extractor person-name fixes in PROJECT_STATUS"
```

- [ ] **Step 4: 查看最终 git log 确认 3 次功能 commit 落地**

```bash
cd /d/myproject/cnmayun
git log --oneline -5
```

**Expected:** 看到 3 个本次 fix 的 commit + 之前的 spec commits。

---

## 自检（已在我写完后自检过）

- **Spec 覆盖**：3 个 fix（Issue 1 短路、Issue 2A 正则、Issue 2B 委托）— Task 1/2/3 各对应一个
- **占位符扫描**：无 TBD / TODO / "implement later" / "类似 Task N" 等
- **类型一致性**：`_normalize_person_name` 在三处（normalization.py 本地、ai_extractor.py 本地、ai_extractor.py import 别名）一致；测试文件 import 行一致
- **每步可独立运行**：每步都有具体的 `python -m pytest` 命令 + 预期输出
- **回滚路径清晰**：Task 1 Step 4 的 2 行删除即可；Task 2 Step 3 的正则恢复即可；Task 3 Step 4 整段恢复即可
