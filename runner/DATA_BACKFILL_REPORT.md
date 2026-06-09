# 零侵入数据补齐工作报告

**Author:** Kimi Code CLI Agent  
**Date:** 2026-04-27 ~ 2026-04-28  
**Scope:** runner/ 目录，零侵入 app/ 原有代码库

---

## 一、薪酬数据回填

**脚本:** `backfill_compensation.py`  
**数据源:** 东方财富 CompanyManagementAjax API (xc 薪酬字段)  
**结果:**
- 69,405 条 executive_snapshots 更新 compensation 字段
- 处理范围: 全部 active 公司（排除 executive_sync_disabled）

---

## 二、公司基本信息补全

**最终脚本:** `backfill_location_final.py`  
**数据源:** 东方财富 CompanySurveyAjax API (sszjhhy/qy/zcdz 字段)  
**核心问题:**
- cninfo getCompanyIntroduction API 返回 404，已废弃
- 早期版本使用 `engine.connect() + conn.begin()` 遭遇 SQLAlchemy 2.0 autobegin 冲突，导致 UPDATE 提交不生效
- 最终改用 `engine.begin()` 解决事务提交问题

**结果:**
| 字段 | 完成数 | 覆盖率 | 备注 |
|------|--------|--------|------|
| industry_l1 | 5,504 | 92.5% | bootstrap 同步时已填充 |
| industry_l2 | 5,356 | 90.0% | 新增填充 |
| province | 5,387 | 90.5% | 新增填充 |
| city | 4,819 | 81.0% | 新增填充（地址解析有损耗） |

**剩余缺口:**
- BJ（北交所/新三板）股票约 564 家：东方财富 API 无数据
- 非 BJ 约 32 家：API 返回空数据

---

## 三、任期链重建

**脚本:** `backfill_tenure_start_dates.py`（修复 executive_sync_disabled 字段引用后重跑）  
**数据源:** 东方财富 CompanyManagementAjax API (rzsj 任职时间字段)  
**结果:**
- 49,900 条 tenure start_date 更新
- Missing before: 54,439 → Missing after: 4,539
- 覆盖率: 93.3% (93,231 / 99,899)

**剩余缺口:**
- 6,668 条 tenure 缺失 start_date（主要为 BJ 股票，东方财富 API 无历史任职日期）

---

## 四、其他已完成的数据增强（此前完成）

| 工作项 | 结果 |
|--------|------|
| 人物画像入库 | 48,230 条 person_profiles |
| 跨公司任职网络 | 8,705 条 network 记录 |
| 生效日期提取 | 118 条 events.effective_date 更新 |
| end_date 回填 | 6,692 条 tenure 设置 end_date+is_active=False |

---

## 五、技术债务与限制

1. **BJ 股票数据盲区**: 北交所/新三板公司（ticker 以 4/8/9 开头）在东方财富 API 中无公司概况和高管任职历史数据，industry_l2/province/city/start_date 均不可获取
2. **city 解析准确率**: 从注册地址（zcdz）正则提取城市名，对少数民族自治区、直辖县的解析有损耗
3. **事件底座转化率**: 2025 年 1,795 篇文档仅 387 条事件（21.5%），需结构优化提升

---

## 六、保留的核心脚本

```
backfill_location_final.py        # 公司位置回填（最终版）
backfill_compensation.py          # 薪酬回填
backfill_tenure_start_dates.py    # tenure start_date 回填
backfill_tenure_end_dates.py      # tenure end_date 回填
reconstruct_tenure_chains.py      # 任期链重建（事件配对）
extract_effective_dates_v2.py     # 生效日期提取
compute_person_network.py         # 人物跨公司网络
batch_enrich_person_profiles.py   # 人物画像批量入库
enhance_persons_from_eastmoney.py # 东方财富人物增强
sync_executives_from_eastmoney.py # 东方财富高管同步
```
