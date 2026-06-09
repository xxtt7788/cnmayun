# 数据丰富建议文档（影响原系统结构）

> Author: Kimi Code CLI Agent
> Date: 2026-04-27
> 说明：以下方案需要修改数据库 schema 或业务代码，建议按需择期实施。

---

## 建议一：公司财务指标表

### 现状
- `company_metrics_daily` 已有 `mom_change_rate`、`yoy_change_rate` 字段，但硬编码为 0
- 系统没有存储公司营收、净利润、市值、总资产等核心财务数据
- 用户无法按"大公司优先"筛选异动事件

### 建议方案

**方案 A：扩展现有表（最小侵入）**

在 `company_metrics_daily` 新增字段：
```sql
ALTER TABLE company_metrics_daily ADD COLUMN revenue BIGINT;           -- 营收（万元）
ALTER TABLE company_metrics_daily ADD COLUMN net_profit BIGINT;        -- 净利润（万元）
ALTER TABLE company_metrics_daily ADD COLUMN market_cap BIGINT;        -- 总市值（万元）
ALTER TABLE company_metrics_daily ADD COLUMN total_assets BIGINT;      -- 总资产（万元）
ALTER TABLE company_metrics_daily ADD COLUMN employee_count INTEGER;   -- 员工人数
```

**方案 B：新建独立表（更规范）**

```sql
CREATE TABLE company_financials (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    report_period VARCHAR(16) NOT NULL,        -- 如 "2025-Q3"
    report_type VARCHAR(16) NOT NULL,          -- "quarterly" / "annual"
    revenue BIGINT,
    net_profit BIGINT,
    market_cap BIGINT,
    total_assets BIGINT,
    net_assets BIGINT,
    roe NUMERIC(8,4),
    eps NUMERIC(12,4),
    employee_count INTEGER,
    source_platform VARCHAR(32) DEFAULT 'AKSHARE',
    source_url TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_company_financial_period UNIQUE (company_id, report_period, report_type)
);
```

### 数据源
- **akshare** `stock_yjbb_em`（业绩报表）或 `stock_financial_report_sina`
- 获取频率：每季度一次

### 业务价值
- 异动流可按市值/营收排序
- 人物详情页可展示"任职公司规模"
- 支持"大公司高管变动优先"的筛选逻辑

### 实施估算
- 脚本开发：2-3 小时
- 首次全量回填：约 6,000 家公司 × 4 个季度 ≈ 24,000 条记录
- 对现有系统影响：新增表/字段，不影响已有业务逻辑

---

## 建议二：人物外部身份表

### 现状
- `persons` 表只有 `external_person_id`（巨潮 F001V）
- 没有工商系统 ID、社会信用代码、其他平台 ID
- 无法关联企查查/天眼查等外部数据源

### 建议方案

新建 `person_external_ids` 表：

```sql
CREATE TABLE person_external_ids (
    id SERIAL PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES persons(id),
    id_type VARCHAR(32) NOT NULL,        -- "qichacha", "tianyancha", "aic", "cninfo"
    external_id VARCHAR(128) NOT NULL,
    id_url TEXT,
    confidence NUMERIC(5,4) DEFAULT 0.8,
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_person_external_type UNIQUE (person_id, id_type)
);
```

### 数据源
- 企查查 API（付费）
- 天眼查 API（付费）
- 国家企业信用信息公示系统（公开，需爬虫）

### 业务价值
- 打通工商任职数据，发现"上市公司高管 + 关联企业"网络
- 识别风险人物（行政处罚、失信记录）
- 支撑更完整的人物履历

---

## 建议三：公告内容质量评分

### 现状
- `source_documents.raw_text` 由 PyPDF 提取，质量不稳定
- 无 OCR 能力，扫描件返回空文本
- 无表格提取能力，董事会选举名单常被破坏

### 建议方案

**阶段 1：替换 PDF 解析引擎**

将 `app/document_parser.py` 中的 `PyPDF` 升级为 `pdfplumber`：
```python
# 当前
from pypdf import PdfReader

# 建议
import pdfplumber

def extract_pdf_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
```

**阶段 2：增加 OCR 兜底**

```python
from pdf2image import convert_from_bytes
import pytesseract

def extract_pdf_text_with_ocr(pdf_bytes: bytes) -> str:
    # 先尝试 pdfplumber
    text = extract_pdf_text(pdf_bytes)
    if len(text.strip()) > 100:
        return text
    # 空文本时 OCR
    images = convert_from_bytes(pdf_bytes, dpi=200)
    return "\n".join(pytesseract.image_to_string(img, lang='chi_sim') for img in images)
```

**阶段 3：增加内容质量标记**

在 `source_documents` 新增字段：
```sql
ALTER TABLE source_documents ADD COLUMN text_quality_score NUMERIC(3,2);
ALTER TABLE source_documents ADD COLUMN extraction_method VARCHAR(32);  -- "pypdf" / "pdfplumber" / "ocr"
ALTER TABLE source_documents ADD COLUMN page_count INTEGER;
ALTER TABLE source_documents ADD COLUMN is_scanned BOOLEAN DEFAULT FALSE;
```

### 业务价值
- 董事会选举名单提取准确率提升 30%+
- 减少"正文为空但确实有人事变动"的漏报
- 为审核人员提供文档质量信号

---

## 建议四：事件关联链

### 现状
- `events` 表每条记录独立，无因果关联
- "张三辞职"和"李四接任"是同一家公司同一岗位的连续事件，但无显式关联
- 无法展示"前任 → 继任"链条

### 建议方案

**方案 A：简单前驱字段（最小侵入）**

```sql
ALTER TABLE events ADD COLUMN predecessor_event_id INTEGER REFERENCES events(id);
ALTER TABLE events ADD COLUMN successor_event_id INTEGER REFERENCES events(id);
```

**方案 B：独立关联表（支持多对多）**

```sql
CREATE TABLE event_chains (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    role_canonical VARCHAR(64) NOT NULL,
    predecessor_event_id INTEGER REFERENCES events(id),
    successor_event_id INTEGER REFERENCES events(id),
    link_type VARCHAR(32) NOT NULL,  -- "resignation_to_appointment", "nomination_to_election"
    confidence NUMERIC(5,4) DEFAULT 0.8,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_event_chain_pair UNIQUE (predecessor_event_id, successor_event_id)
);
```

### 生成逻辑
- 同一公司同一角色，30 天内先 resignation 后 appointment → 自动关联
- 提名公告 + 选举公告 → 关联

### 业务价值
- 人物详情页展示"前任/继任"关系
- 公司页展示"领导层变迁时间线"
- 猎头可快速定位"因前任离职产生的继任机会"

---

## 建议五：审核质量度量表

### 现状
- `review_queue` 只有状态，无审核耗时、错误类型、高频误报统计
- 无法回答"本周误报率多少""哪个规则最不准"

### 建议方案

新建 `review_metrics` 表：

```sql
CREATE TABLE review_metrics (
    id SERIAL PRIMARY KEY,
    metric_date DATE NOT NULL,
    total_documents INTEGER DEFAULT 0,
    auto_published INTEGER DEFAULT 0,
    auto_rejected INTEGER DEFAULT 0,
    manual_review INTEGER DEFAULT 0,
    manual_approved INTEGER DEFAULT 0,
    manual_rejected INTEGER DEFAULT 0,
    avg_review_time_seconds INTEGER,
    top_error_type VARCHAR(64),
    top_error_count INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_review_metric_date UNIQUE (metric_date)
);
```

### 业务价值
- 运营人员每天看数据质量趋势
- 识别需要优化的规则
- 为 AI 模型迭代提供标注数据分布

---

## 实施优先级建议

| 优先级 | 建议 | 工作量 | 业务价值 |
|--------|------|--------|----------|
| P1 | 公司财务指标 | 中 | 高 |
| P2 | 公告内容质量评分 | 中 | 高 |
| P3 | 事件关联链 | 小 | 中 |
| P4 | 人物外部身份 | 大 | 中 |
| P5 | 审核质量度量 | 小 | 低 |

---

## 结论

以上五项均**不影响现有业务代码运行**，但都需要：
1. 新增数据库表或字段
2. 新增 runner 采集脚本
3. 可能新增 API 返回字段（前端可选消费）

建议按 P1 → P2 → P3 顺序实施，每完成一项即跑一次数据回填。
