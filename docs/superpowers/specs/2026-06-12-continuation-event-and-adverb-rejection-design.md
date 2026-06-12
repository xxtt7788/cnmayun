# 2-字虚词人名校验 + 续任事件类型 — 设计文档

- **日期**: 2026-06-12
- **作者**: Claude (systematic-debugging + brainstorming)
- **状态**: 已批准，待实施
- **来源 bug**: doc id=18686（海南橡胶第六届董事会决议公告）— 待审队列中"王宏向先生不再担任公司董事长职务，继续担任公司董事。"

## 背景与目标

系统在生产待审队列里跑出来 3 个 hint（其中 1 错 1 漏）：

| # | 人员 | 角色 | 事件 | 置信度 | 评价 |
|---|------|------|------|--------|------|
| 1 | 易金波 | chairperson | appointment | 0.96 | ✅ |
| 2 | 王宏向 | chairperson | non_renewal | 0.94 | ✅ |
| 3 | **不再** | director | non_renewal | 0.78 | ❌ 假阳性（"不再" 是副词） |
| 缺 | 王宏向 | director | — | — | ❌ 漏报（"继续担任公司董事" 未识别） |

本设计修复**两个 bug**：

- **Bug A**：虚词"不再"被当成人名（假阳性）
- **Bug B**：保留关系"继续担任公司董事"未识别（漏报）

## Bug A 根因

文档 body 里有**两处**"不再担任"：

1. "王宏向先生不再担任公司**董事长**职务" — role="公司董事长职务" → `non_renewal` 命中 `chairperson` → 提为 hint ✅
2. "王宏向先生不再担任**董事会各专门委员会**相关职务" — role="董事会各专门委员会相关职务" → **无角色关键词** → `extract_events_from_text` 候选被丢弃 → 返回空 → 触发 fallback `sentence_pattern` → `_extract_hint_person_names` 用了一个**过宽的 regex** `<name>[一-龥]{2,4}...担任`，从"不再担任"里把"不再"抓出来当人

`_normalize_person_name("不再")` 也漏过 — 2 个合法汉字、不在 `INVALID_PERSON_TOKENS`（"第/届/董事会/监事会/委员会/公司/议案/公告/候选人/专门会议"）里。

## Bug B 根因

句子"王宏向先生不再担任公司董事长职务，**继续担任公司董事**"含两个动作。现有 EVENT_PATTERNS（`app/normalization.py:112-168`）**只有**：
- `non_renewal`（不再担任）
- `reelection`（连任）

**没有**"继续担任X"/"仍担任X"/"续任X"这种**保留**关系。

## 设计

### 改动 1（Bug A）：`_normalize_person_name` 拒绝 2-字常见虚词/副词

在 `app/normalization.py` 增加一个 2-字非人名 token 集合 `_NON_PERSON_2CHAR_TOKENS`，在现有的"经理/董事/委员/主席/主持/列席"和"声明/名单/议案/报告"检查之后加一条：

```python
_NON_PERSON_2CHAR_TOKENS = frozenset({
    # 否定/继续类副词：2 字，绝不可能是中文人名
    "不再", "续任", "仍在", "继续", "持续",
    "原有", "原任", "原系", "原拟", "原为",
    "前为", "前述",
    # 仍 X 系
    "仍由", "仍将", "仍任", "仍系",
    # 其他易误识的虚词
    "本人", "该等", "其他", "其余", "前述",
    "上述", "如下", "如上",
    "本次", "本届", "本期", "本项",
    "该人", "对方", "他人",
})
```

`_normalize_person_name` 内：

```python
if re.fullmatch(r"[一-龥]{2,4}", normalized):
    if any(token in normalized for token in INVALID_PERSON_TOKENS):
        return None
    if any(token in normalized for token in _NON_PERSON_2CHAR_TOKENS):
        return None
    if any(token in normalized for token in ("经理", "董事", "委员", "主席", "主持", "列席")):
        return None
    if any(token in normalized for token in ("声明", "名单", "议案", "报告")):
        return None
    return normalized
```

注：用 `set` 加速 lookup；用 `any(token in normalized ...)` 因为 2-字 token 出现在 2-字人名里仍然 false（集合"包含关系"）。但 3-字人名可能包含 2-字子串（如人名"不再三"）。这种情况概率极低（人名里出现"不再"作前缀几乎不存在中文人名），**先不处理 3+ 字嵌套情况**。如要保险可加 `len(normalized) == 2` 限定。

**更安全版本**：只在 `len(normalized) == 2` 时检查 2-字 token：

```python
if len(normalized) == 2 and normalized in _NON_PERSON_2CHAR_TOKENS:
    return None
```

采用这个安全版本（精确匹配）。

### 改动 2（Bug B）：新增 `continuation` 事件类型

**文件 A**：`app/normalization.py`

1. `EVENT_TYPE_LABELS` 加一行（line 17-27）：
   ```python
   "continuation": "续任",
   ```

2. `EVENT_PATTERNS` 加一个 pattern（line 168 之后）：
   ```python
   (
       "continuation",
       r"(?P<name>[一-龥]{2,4})(先生|女士)?(?:继续|仍)担任(?P<role>[^，,。.;；\n]{0,24})",
       0.92,
   ),
   ```

3. `infer_event_type_from_title`（line 290 附近）加分支：
   ```python
   if "继续担任" in normalized or "仍担任" in normalized or "续任" in normalized:
       return "continuation"
   ```

**文件 B**：`app/ai_extractor.py`

1. `ALLOWED_EVENT_TYPES` 加 `"continuation"`（line 40-50）。

2. `_SYSTEM_PROMPT`（line 73-76）把 `continuation` 加进事件列表：
   ```
   事件:appointment|resignation|removal|reelection|interim_assignment|title_change|nomination|non_renewal|retirement|continuation
   ```

**文件 C**：`app/static/styles.css`（line 807-815 附近）参考 `.pill-reelection` 加一条：
```css
.pill-continuation,
.pill-continuation * {
    ...
}
```

（按现有配色板挑一个色。如没时间可暂用 `.pill-reelection` 同色，留 TODO。）

**文件 D**：`app/notice_pipeline.py`（line 232, 350, 359）— 检查 `continuation` 是否需要特殊处理。

- Line 232 `if any(item.event_type in {"nomination", "reelection"} ...)`：reelection 在合并时需要特别对待。`continuation` 语义更简单（一个人在原岗位继续），应当**不**走 nomination/reelection 合并路径。
- Line 350+ `simple_event_types` 集合：可加 `continuation`。
- Line 359 `has_nomination_reelection` 改名 + 加 `continuation`？需要看是否影响风险判定。

**审慎策略**：先**只**改文件 A、B、C + normalization.py EVENT_PATTERNS；`notice_pipeline.py` 暂不改，看 PR review 再决定。

### 改动 3：测试

**文件**：`tests/test_refactor_modules.py`（已经有的"normalization"测试集）

新增一个 `NormalizationEventExtractionTests` 类（或者扩展现有 `IsBotUserAgentTests` 之外的 normalization 测试）：

1. `test_normalize_rejects_bu_zai` — `_normalize_person_name("不再") is None`
2. `test_normalize_rejects_xu_ren` — `_normalize_person_name("续任") is None`
3. `test_normalize_rejects_ji_xu` — `_normalize_person_name("继续") is None`
4. `test_normalize_still_accepts_real_2char_name` — `_normalize_person_name("易金") == "易金"`（2 字真实人名仍然接受）
5. `test_normalize_still_accepts_王宏向` — `_normalize_person_name("王宏向") == "王宏向"`（3 字不变）

然后是 Bug B 的端到端：

6. `test_continuation_event_from_continue_dan_ren` — `extract_events_from_text` 对 "王宏向先生继续担任公司董事" 返回 `[(王宏向, director, continuation, conf>=0.90)]`
7. `test_continuation_event_from_reng_dan_ren` — 对 "李四先生仍担任公司副董事长" 返回 `[(李四, chairperson, continuation, conf>=0.90)]`
8. `test_continuation_in_event_type_labels` — `event_type_label("continuation") == "续任"`
9. `test_end_to_end_bug_sentence` — 对 doc 18686 的实际 title + 实际 sentence 跑 `extract_review_hints_from_text`，断言生成的 hints 是：
   - (易金波, chairperson, appointment)
   - (王宏向, chairperson, non_renewal)
   - (王宏向, director, continuation)  ← 新增
   - **不**应包含 (不再, director, non_renewal)  ← 修 Bug A

## 显式不做

- 不动 `_extract_hint_person_names` 的 regex（用 `_normalize_person_name` 拦截更稳，不破坏其他合法 match）
- 不改 `notice_pipeline.py`（先观察）
- 不改 UI 模板（CSS 之后再说）
- 不动 invalid_event_type 之外的 AI prompt 优化

## 部署

跟今天 ClaudeBot filter 一样的流程：
1. 改 `app/normalization.py` + `app/ai_extractor.py` + 跑测试
2. `package_for_server.ps1` 的 Python 端口跑：build zip (排除 `.git`/`.pyc.NNN`/data 等)
3. SFTP upload → 服务器解压覆盖（rsync as china-succession + no --delete）
4. `sudo systemctl restart china-succession-web.service`
5. 验证 doc 18686 在 `/review` 队列里 hints 已经修正

## 风险

- 改动 EVENT_TYPE_LABELS / ALLOWED_EVENT_TYPES — 新增不会破坏现有，但需要确保 AI path 接受新值
- CSS 暂不改：前端 review 队列的 hint 卡片暂时没"续任"标签，event_type 字段会是 None 标签。可以后补
- `_NON_PERSON_2CHAR_TOKENS` 列表是手工加的，**保守**：只精确匹配 2-字。不影响 3+ 字合法人名

## 验收标准

- [ ] `test_normalize_rejects_bu_zai` 等 5 个新单测全过
- [ ] `test_continuation_event_*` 等 4 个新单测全过
- [ ] 现有 56 个测试无回归
- [ ] 线上 doc 18686 review 时，hint 列表不再含 (不再, director, non_renewal)
- [ ] 线上 doc 18686 review 时，hint 列表**新增** (王宏向, director, continuation) 一条
- [ ] `/healthz` 200，服务未中断
