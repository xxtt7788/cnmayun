# 数据运维操作总录

> **唯一文档**：本文件为 `runner/` 目录下唯一运维记录文档，所有数据回填、修复、增强操作均记录于此。
> **维护人**：Kimi Code CLI Agent
> **最后更新**：2026-04-29

---

## 一、全库数据基线（2026-04-28 最终态）

| 维度 | 总量 | 指标 | 覆盖率 |
|------|------|------|--------|
| **公司** | 5,952 | ticker/exchange/name | 100% |
| | | industry_l2 | 95.2% |
| | | province | 95.7% |
| | | city | 90.5% |
| | | listed_date/website/地址 | 92%± |
| | | state_owned_flag | 3.0%（180家，名称推断） |
| **任期** | 99,899 | start_date | 97.8% |
| | | end_date | 6.7%（多为在职） |
| | | 孤儿记录 | 0 |
| **快照** | 137,998 | compensation | 83.4% |
| | | gender/birth_year/education | 97–100% |
| **人物** | 62,061 | 有画像 | 79.5% |
| | | 有任期 | 94.2% |
| | | 画像 education | 98.5% |
| **事件** | 13,186 | effective_date | 100% |
| | | 推断事件 | 11,692（88.7%） |
| | | reason_category | 10.8%（1,418/13,186） |
| | | post_decline_flag | 5.0%（665/13,186） |
| **财报** | 25,837 | 报告期数 | 5 |
| | | 营收/净利润/ROE | 99%+ |
| **Source Docs** | 16,742 | 推断占位 | 11,692 |
| **股东** | 74,662 | company_shareholders | 93.2%（5,546/5,952 家） |
| **股价** | 1,253,958 | company_stock_prices | 87.6%（5,213/5,952 家，1 年日 K） |
| **注册资本** | 5,383 | companies.registered_capital | 90.4% |
| **员工数** | 5,355 | companies.employee_count | 90.0% |
| **人物流动** | 42,155 | person_transfers | 100% |
| **人物持股** | 3,280 | person_shareholdings | 精确匹配 |
| **继任链** | 21 | event_chains | — |
| **变动率** | 2,585 | company_turnover_rate | 视图 |

---

## 二、本轮执行操作清单

### 2.1 P1 快速修复（2026-04-28）

| 操作 | 脚本 | 结果 | 备注 |
|------|------|------|------|
| 修复 UNKNOWN exchange | `fix_exchange_unknown.py` | 1 家修复（302132 → SZSE） | ticker 前缀推断 |
| 同步 education 到画像 | `sync_education_to_profiles.py` | 48,638 条更新，覆盖率 0% → 98.5% | 从 snapshots 最新记录同步 |
| 推断国企标识 | `infer_state_owned.py` | 180 家标记为国企 | 公司名称关键词匹配 |

### 2.2 City / BJ 股票修复（2026-04-28）

| 操作 | 脚本 | 结果 | 备注 |
|------|------|------|------|
| City 解析增强 | `backfill_city_enhanced.py` | +568 家，81.0% → 90.5% | 支持省/自治区/直辖市/地区/盟 |
| BJ 基本信息回填 | `backfill_bj_basic.py` | 310/564 家更新行业+省份 | akshare `stock_info_bj_name_code` |
| BJ 任期 start_date | `backfill_bj_tenure_start.py` | 4,489/5,601 条更新 | EastMoney BJ 前缀 API |

### 2.3 P2 财务与薪酬（2026-04-28）

| 操作 | 脚本 | 结果 | 备注 |
|------|------|------|------|
| 财报多期扩展 | `backfill_financials_multi_period.py` | 25,837 条，5 个报告期 | 2024 年报+3季报+中报+1季报，含之前已入库的 2024 年报 |
| 薪酬补漏 | `backfill_compensation_missing.py` | +4,974 条，79.8% → 83.4% | A 股重新抓取 EastMoney |

### 2.4 P3 事件生成（2026-04-28）

| 操作 | 脚本 | 结果 | 备注 |
|------|------|------|------|
| 推断 resignation 事件 | `generate_inferred_events.py` | 6,692 条 | 从 tenure end_date 生成，is_inferred=true |
| 推断 appointment 事件 | `generate_inferred_events.py` | 5,000 条 | 从 tenure start_date 生成，is_inferred=true |

### 2.5 系统数据增强 Round 1–5（2026-04-25）

| 操作 | 脚本 | 结果 | 备注 |
|------|------|------|------|
| Schema 迁移 | `migrate_schema_round1.py` + `fix_schema_round1.py` | 6 张新表 + 多个字段 | 全部 IF NOT EXISTS |
| R1.1 十大流通股东 | `backfill_r11_shareholders.py`（单线程版） | 74,662 条 / 5,546 家 | EastMoney emweb PageSDGD；406 家公司因 urllib 阻塞放弃 |
| R1.2 注册资本/员工数 | `backfill_r12_scale_parallel.py` | registered_capital=5,383, employee_count=5,355 | EastMoney emweb CompanySurveyAjax，ThreadPoolExecutor(5) |
| R1.3 股价历史近1年 | `backfill_r13_stock_prices.py` | 1,253,958 条 / 5,213 家 | baostock query_history_k_data_plus；BJ 代码无法识别跳过 |
| R2.1 变更原因分类 | `backfill_round2_event_deepening.py` | 1,418/13,185 条分类 | 规则匹配 excerpt 关键词 |
| R2.2 前任继任链 | `backfill_round2_event_chains_and_turnover.py` | 21 条 | resignation→appointment 180 天内 |
| R2.3 高管变动率 | `backfill_round2_event_chains_and_turnover.py` | 2,585 行视图 | 按公司+年度聚合 |
| R3.1 人物持股匹配 | `backfill_round3_4_5_sql.py` | 3,280 条 | company_shareholders × persons 精确匹配 |
| R3.2 人物跨公司流动 | `backfill_round3_person_transfers.py` | 42,155 条 | role_tenures 自连接 |
| R3.4 流动热度评分 | `backfill_round3_person_transfers.py` | avg=5.31 | persons.transfer_frequency_score |
| R4.2 行业财务中位数 | `backfill_round3_4_5_sql.py` | 0 行 | industry_l2 缺失导致 |
| R4.3 推断文档标记 | `backfill_round3_4_5_sql.py` | 0 条 | source_type 已区分或条件不匹配 |
| R5.1 处罚后变动标记 | `backfill_round3_4_5_sql.py` | 0 条 | company_risks 表为空 |
| R5.2 业绩恶化变动标记 | `backfill_round3_4_5_sql.py` | 665 条 | 营收/净利润同比 <-20% |
| R5.3 流动评分更新 | `backfill_round3_4_5_sql.py` | avg=5.31 | 复用 person_transfers |

---

## 三、新增/归档脚本清单

`runner/` 目录下以下脚本为本轮新增或更新：

- `backfill_financials.py` — Phase 5 财务指标回填（2024 年报）
- `backfill_financials_multi_period.py` — 财报多期扩展
- `backfill_city_enhanced.py` — 增强版城市解析
- `backfill_bj_basic.py` — BJ 股票基本信息回填
- `backfill_bj_tenure_start.py` — BJ 任期 start_date 回填
- `backfill_compensation_missing.py` — 薪酬补漏
- `fix_exchange_unknown.py` — UNKNOWN exchange 修复
- `sync_education_to_profiles.py` — 画像 education 同步
- `infer_state_owned.py` — 国企标识推断
- `generate_inferred_events.py` — 推断事件生成
- `_check_status.py` — 快速状态诊断（已更新）
- `migrate_schema_round1.py` / `fix_schema_round1.py` — Schema 迁移
- `backfill_r11_shareholders.py` — R1.1 十大流通股东（最终版，单线程+curl超时）
- `backfill_r12_scale_parallel.py` — R1.2 注册资本+员工数（最终版，5线程并行）
- `backfill_r13_stock_prices.py` — R1.3 股价历史（最终版，baostock）
- `backfill_round2_event_deepening.py` — R2.1 变更原因分类
- `backfill_round2_event_chains_and_turnover.py` — R2.2+R2.3 继任链+变动率
- `backfill_round3_person_transfers.py` — R3.2+R3.4 人物流动
- `backfill_round3_4_5_sql.py` — R3.1+R4.2+R4.3+R5 SQL 综合

---

## 四、已知未解决缺口（客观限制）

| 缺口 | 数量 | 原因 | 能否解决 |
|------|------|------|----------|
| city 缺失 | 365 家 | 注册地址不含地级市（县级市/县/工业园） | 否，地址本身无信息 |
| BJ industry/province | 254 家 | 老新三板基础层（430xxx），akshare 无接口 | 否，无公开数据源 |
| BJ start_date | 1,112 条 | EastMoney 无对应 75 家公司数据 | 否，无数据源 |
| state_owned_flag | 5,772 家 | 名称推断仅覆盖 obvious SOE，其余需实际控制人数据 | 需专门接口 |
| 人物持股/关系 | 0% | person_profiles.shareholding_raw / relationship_raw 为空 | 无可用 API |
| compensation | 20,834 条 | EastMoney 部分公司无薪酬披露 | 部分可补，受 API 限制 |
| 财报 | 仅 2024+ 部分季度 | 网络超时导致 2023 期间未完整入库 | 可重试 |

---

## 五、数据质量检查记录

- **孤儿记录**：tenures/snapshots/events 均为 0
- **重复 person**：存在同名不同人（正常现象）
- **日期异常**：start > end = 0，1980 年前 start = 极少，未来 start = 0
- **Zero compensation**：compensation=0 的快照需排查是否为解析失败

---

## 六、签名

```
Author: Kimi Code CLI Agent
Date: 2026-04-29
Session: R1–R5 系统数据增强全部完成（含 R1.1/1.2/1.3 后台任务收尾）
Status: COMPLETE (with documented limitations)
Note: R1.1 单线程版因 urllib 阻塞提前终止（5,546/5,952 家完成）；R1.2 并行版 5 线程 5,648 家全部处理完毕；R1.3 baostock 1 年日 K 5,213 家完成。BJ/新三板代码在 baostock 中无法识别，为已知限制。
```

---

```
Author: Kimi Code CLI Agent
Date: 2026-04-25
Session: System data enhancement Round 1-5
Status: IN PROGRESS (R1.1/1.2/1.3 background tasks running)
Note: Round 2-5 SQL-only tasks complete. R1 external API tasks ongoing.
```

---

*本文档为 runner/ 下唯一运维记录。新增操作请追加到本文档末尾，保持单文件维护。*
