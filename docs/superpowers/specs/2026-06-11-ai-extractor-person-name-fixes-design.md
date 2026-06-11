# AI 提取器人名修复 — 设计文档

- **日期**: 2026-06-11
- **作者**: Claude (brainstorming skill)
- **状态**: 已批准，待实施

## 背景与目标

人工审核队列（`/review`）目前积压大量低信号条目，根因是两条人名提取路径在过滤逻辑上不一致：

1. **Issue 1 — "缺失字段：人员姓名" 大量出现**
   句子如 `(一)审议通过了《关于提名公司第六届董事会非独立董事候选人的议案》` 含人事关键词（"提名"），但本身**不包含**任何具体人员姓名。当前的 `extract_review_hints_from_text` 仍会为这种句子创建一个 hint 并标记 `missing_fields=("人员姓名",)`，导致审核队列里出现大量无法通过任何自动手段补全的"假阳性"项。

2. **Issue 2 — "经公" 被接受为人名**
   句子 `...经公司控股股东...推荐...公司董事会提名乔胜俊先生...` 经过 AI 提取后，AI 偶尔会返回 `"经公"` 作为 `person_name`。AI 路径下的 `_normalize_person_name`（在 `app/ai_extractor.py`）**没有**运行规则路径下的 `INVALID_PERSON_TOKENS` 等检查，导致 `经公` 通过校验被接受。规则路径（`app/normalization.py`）的同名校验函数则有这些检查。

本设计目标：

- 让"议案标题句"不再生成无效 hint
- 让 AI 路径与规则路径共用同一套人名校验，杜绝 `经公` 类假人名

## 设计

### 改动 1：跳过无人名的 hint

**文件**：`app/normalization.py`
**函数**：`extract_review_hints_from_text`
**位置**：约 556–602 行

在 `person_names = _extract_hint_person_names(sentence)` 之后立即加一行短路：

```python
person_names = _extract_hint_person_names(sentence)
# 过滤：句子含人事关键词但无具体人名（如"审议通过了《关于提名...的议案》"），
#      不再生成低信号 hint，跳过该句。
if not any(person_names):
    continue
```

**为什么是 `continue` 而非条件性 hint？**
- 这种句子无法通过任何自动手段补全"人员姓名"，留下只会污染队列
- 现有 `extract_events_from_text("", sentence)` 的提前 `continue` 也是同样的过滤哲学

**回归影响**：
- 真正含人名的句子：`person_names` 至少有一个非 None 元素，`any(...)` 为 True，行为不变
- 议案标题句：无 hint 生成

### 改动 2：统一人名校验

**文件 A**：`app/normalization.py`
**函数**：`_normalize_person_name`
**位置**：约 348 行

修改前缀剥离正则，新增 `经`：

```python
# 原：(?:同意|拟|经审查|经审核|经董事会|被提名为|被提名|提名|补选|聘任|任命|选举|选聘|当选|免去|免职|解聘)+
# 新：(?:同意|拟|经董事会|经审查|经审核|经|被提名为|被提名|提名|补选|聘任|任命|选举|选聘|当选|免去|免职|解聘)+
```

把 `经` 放在三个 `经X` 之后，避免被提前吃掉。`经公` → `公`（1 字）→ 不匹配 2-4 字范围 → 返回 `None`。

**文件 B**：`app/ai_extractor.py`
**函数**：模块级 `_normalize_person_name`
**位置**：约 227–235 行

**整段替换**为委托 `app.normalization._normalize_person_name`：

```python
from app.normalization import _normalize_person_name  # 加到顶部 import

def _normalize_person_name(raw_name: Any) -> str | None:
    """委托规则路径的统一校验：包含前缀剥离、INVALID_PERSON_TOKENS、
    '经理/董事/委员' 后缀检查、'声明/名单/议案/报告' 检查、拉丁名 fallback。"""
    from app.normalization import _normalize_person_name as _rule_normalize
    return _rule_normalize(str(raw_name or ""))
```

> 注：模块级函数名相同会产生轻微自引用风险，使用 `_rule_normalize as` 别名规避。

### 改动 3：测试

**文件**：`tests/test_notice_extraction.py`

新增三个测试：

```python
# 1. 议案标题句不再生成"缺失字段：人员姓名" hint
def test_vote_summary_without_names_does_not_create_hint(self) -> None:
    hints = extract_review_hints_from_text(
        "第十届董事会第十三次会议决议公告",
        "（一）审议通过了《关于提名公司第十一届董事会非独立董事候选人的议案》",
    )
    self.assertEqual(
        [h for h in hints if h.person_name is None and "人员姓名" in h.missing_fields],
        []
    )

# 2. AI 路径拒绝"经公"类假人名
def test_ai_path_rejects_false_names(self) -> None:
    from app.ai_extractor import _normalize_person_name as ai_normalize
    self.assertIsNone(ai_normalize("经公"))
    self.assertIsNone(ai_normalize("经董事会"))
    self.assertIsNone(ai_normalize("经审查"))
    self.assertEqual(ai_normalize("乔胜俊"), "乔胜俊")  # 真实名字保留

# 3. 规则路径也拒绝"经公"（回归保护，确保两边都用统一逻辑）
def test_rule_path_rejects_经公(self) -> None:
    from app.normalization import _normalize_person_name
    self.assertIsNone(_normalize_person_name("经公"))
    self.assertEqual(_normalize_person_name("乔胜俊"), "乔胜俊")
```

## 验证步骤

1. **运行新测试**：`python -m pytest tests/test_notice_extraction.py -v`
2. **运行回归套件**：`python -m pytest tests/ -v`
3. **手动验证 SQL 查询**：在 SQLite 中跑一次统计：
   ```sql
   SELECT COUNT(*) FROM review_queue
   WHERE status = 'pending'
     AND reason LIKE '%缺失字段：人员姓名%';
   ```
   预期：计数大幅下降（无新条目产生），但已存在的待审核项不删除（保留供人工清理）。

## 风险与回滚

### 风险

- 改动 2 让 AI 路径更严格，可能**误拒**极个别原本能通过的边界人名。
  缓解：测试 2 明确包含 `assertEqual(ai_normalize("乔胜俊"), "乔胜俊")` 作为正面用例。
- 改动 1 让"议案标题句"无 hint，可能让某条**确实有候选人**但名字在另一段的句子失去提示。
  缓解：`extract_events_from_text`（规则路径）仍正常工作，候选人仍被提取；hint 只是"人工复核提示"层，丢了不会丢事件。

### 回滚

- 改动 1：单行 `if not any(person_names): continue` 删除即可
- 改动 2：把 ai_extractor.py 的 `_normalize_person_name` 恢复成原版；normalization.py 的正则恢复

## 不在本设计范围

- 不清理数据库中已存在的"缺失字段：人员姓名"记录（由人工通过 reject 流程清理）
- 不修改 `extract_events_from_text` 规则路径
- 不修改 AI 提示词
- 不修改 `INVALID_PERSON_TOKENS` 集合（不加 "公" — 太宽，可能误伤）
- 不引入新的依赖、不修改数据模型

## 实施后效果

- 审核队列新增条目中"缺失字段：人员姓名"比例为 0
- AI 提取出的人名 100% 通过规则路径的 `INVALID_PERSON_TOKENS` 等校验
- 规则路径与 AI 路径的人名校验单一真相源（single source of truth）
