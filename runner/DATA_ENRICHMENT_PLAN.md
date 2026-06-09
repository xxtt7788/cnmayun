# 数据补齐与丰富计划

> Author: Kimi Code CLI Agent
> Date: 2026-04-27
> 范围：数据收集与验证，不涉及业务代码开发

## 当前数据基线

| 维度 | 数值 | 备注 |
|------|------|------|
| 公司总数 | 6,104 | 5,952 活跃 + 343 disabled |
| 高管快照 | 137,998 | 东方财富全量同步 |
| 人物 | 62,061 | gender 99.2%, birth_year 98.0%, education 97.6% |
| 任职记录 | 99,899 | start_date 93.3%, end_date 6.7% |
| 事件 | 1,481 | 全部 published, 0 pending |
| 源文档 | 4,906 | 2015-2024 年历史回填 |
| 审核队列 | 0 | review_required 清零 |

## 已识别数据缺口

基于代码阅读（models.py, notice_pipeline.py, cninfo.py, document_parser.py）和实际数据核查：

1. **PersonProfile 表几乎为空** — resume_raw, career_history_raw, shareholding_raw 等字段无自动填充路径
2. **Event.effective_date 全等于 announcement_date** — 未从公告正文提取实际生效日期
3. **事件底座偏薄** — 1,481 条事件 vs 5,952 家公司，平均每家 0.25 条
4. **CompanyMetricDaily.mom/yoy 为硬编码 0** — 未真实计算
5. **BSE 公司 start_date 缺口 5,601 条** — 公开 API 无历史任职日期
6. **人物跨公司任职网络未显性化** — 数据已存在但未形成"一人多公司"视图

---

## 执行阶段

### Phase 1: 人物画像批量入库（高优先级）

**目标**：把东方财富 API 返回的完整简历（jj 字段）写入 person_profiles 表。

**数据源**：东方财富 CompanyManagementAjax（已有接口，rptManagerList[].jj）

**方法**：
1. 遍历所有活跃公司，获取当前高管列表
2. 对每个人物，提取 jj（简历）字段
3. 解析简历中的 career_history、shareholding、relationship 等信息
4. 写入 person_profiles 表

**预期成果**：
- person_profiles 从 ~0 条增至 60,000+ 条
- 人物详情页有完整履历展示

---

### Phase 2: 公告生效日期提取（高优先级）

**目标**：从 source_documents.raw_text 中提取实际生效日期，更新 events.effective_date。

**背景**：当前 notice_pipeline.py 中 `_upsert_event_from_notice()` 直接把 effective_date 设为 announcement_date，但公告正文通常包含"任期自X年X月X日起""自即日起生效"等实际生效日期。

**方法**：
1. 对已发布的 1,481 条事件，回溯其 source_document.raw_text
2. 用正则/规则提取正文中的生效日期表述
3. 更新 events.effective_date

**关键模式**：
- "任期自(\d{4})年(\d{1,2})月(\d{1,2})日起"
- "自(\d{4})年(\d{1,2})月(\d{1,2})日起生效"
- "自即日起生效" → effective_date = announcement_date
- "任期三年" → 可推断 end_date

**预期成果**：
- 至少 30% 的 events 获得更准确的 effective_date
- 提升人物任职时间线精度

---

### Phase 3: 2025 年公告持续采集 + 历史深挖（高优先级）

**目标**：增厚事件底座。

**方法**：
1. 每日增量采集 2025 年公告（已有 sync-notices 定时任务）
2. 对 4,906 篇已入库 source_documents 做二次扫描，识别被忽略的换届/选举类公告
3. 重点补充：换届公告（通常包含多人任命，之前因"多人公告"风险标记被置为 review_required，现已批量放行）

**预期成果**：
- 事件数从 1,481 增至 2,000+
- 近 90 天事件密度提升

---

### Phase 4: 人物跨公司任职网络计算（中优先级）

**目标**：从现有 role_tenures 数据计算"同一人任职多家公司"的关系，丰富人物详情。

**方法**：
1. 查询所有 person_id 出现在多家公司的 tenure
2. 生成"人物-公司"任职网络统计
3. 写入 persons.notes 或 person_profiles 的 career_history_raw

**预期成果**：
- 人物详情页展示"同时/历任 X 家公司"
- 支撑"高管流动路径"检索

---

### Phase 5: 公司财务指标补充（中优先级）

**目标**：用 akshare 获取公司基本财务数据，支撑"按市值/营收筛选"。

**数据源**：akshare stock_yjbb_em（业绩报表）或 stock_financial_report_sina

**方法**：
1. 批量获取公司最新一期财务数据（营收、净利润、市值）
2. 写入 company_metrics_daily 或 companies 表扩展字段

**预期成果**：
- 公司列表可按市值/营收排序
- 异动事件可附加"大公司优先"权重

---

### Phase 6: 任期链重建与校准（中优先级）

**目标**：从 appointment + resignation 事件重建连续 tenure，校准 start_date/end_date。

**方法**：
1. 按 (company_id, person_id, role_canonical) 分组
2. appointment 事件 → tenure.start_date
3. resignation/removal 事件 → tenure.end_date
4. 对同一公司同角色的 tenure 做连续性检查

**预期成果**：
- 填补部分缺失的 start_date（特别是 SSE/SZSE）
- 发现"任命但未找到辞职"的悬空 tenure

---

## 执行顺序

```
Phase 1 (人物画像) ──> Phase 2 (生效日期) ──> Phase 3 (事件增厚)
     │
     └──────────────> Phase 4 (任职网络) ──> Phase 5 (财务指标) ──> Phase 6 (任期重建)
```

Phase 1-3 可并行启动，Phase 4-6 依赖前序数据质量。

## 验收标准

| 阶段 | 验收指标 |
|------|----------|
| Phase 1 | person_profiles 表记录数 > 50,000 |
| Phase 2 | effective_date ≠ announcement_date 的事件比例 > 20% |
| Phase 3 | 事件总数 > 2,000 |
| Phase 4 | 跨公司任职人物数统计完成 |
| Phase 5 | 财务数据覆盖率 > 80% |
| Phase 6 | 通过事件重建补充 start_date > 200 条 |
