#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 5: Backfill company financial metrics from akshare.

Fetches latest financial reports (revenue, net profit, ROE, etc.) via akshare
stock_yjbb_em and writes to a new table `company_financials`.

Zero-intrusive: does NOT modify app/ code; creates table via raw SQL.

Author: Kimi Code CLI Agent | Date: 2026-04-28
"""

import os
import sys
import logging
from datetime import datetime

ENV_PATH = "/etc/china-succession/china-succession.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.startswith("export "):
                    key = key[7:]
                os.environ[key] = value.strip().strip('"').strip("'")

sys.path.insert(0, "/opt/china-succession")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Create table (zero-intrusive, no ORM model change) ──
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS company_financials (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    report_period VARCHAR(8) NOT NULL,
    report_date DATE,
    revenue NUMERIC(20, 2),
    revenue_yoy NUMERIC(12, 4),
    revenue_qoq NUMERIC(12, 4),
    net_profit NUMERIC(20, 2),
    net_profit_yoy NUMERIC(12, 4),
    net_profit_qoq NUMERIC(12, 4),
    eps NUMERIC(12, 4),
    nav_per_share NUMERIC(12, 4),
    roe NUMERIC(12, 4),
    operating_cfps NUMERIC(12, 4),
    gross_margin NUMERIC(12, 4),
    industry_l2 TEXT,
    announcement_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(company_id, report_period)
);

CREATE INDEX IF NOT EXISTS idx_company_financials_company_id
    ON company_financials(company_id);
CREATE INDEX IF NOT EXISTS idx_company_financials_report_period
    ON company_financials(report_period);
"""

# ── Column names as Unicode escapes to avoid encoding issues ──
# 股票代码, 股票简称, 每股收益,
# 营业收入-营业收入, 营业收入-同比增长, 营业收入-季度环比增长,
# 净利润-净利润, 净利润-同比增长, 净利润-季度环比增长,
# 每股净资产, 净资产收益率, 每股经营现金流量, 销售毛利率, 所属行业, 最新公告日期
COL_TICKER = "\u80a1\u7968\u4ee3\u7801"
COL_NAME = "\u80a1\u7968\u7b80\u79f0"
COL_EPS = "\u6bcf\u80a1\u6536\u76ca"
COL_REVENUE = "\u8425\u4e1a\u603b\u6536\u5165-\u8425\u4e1a\u603b\u6536\u5165"
COL_REVENUE_YOY = "\u8425\u4e1a\u603b\u6536\u5165-\u540c\u6bd4\u589e\u957f"
COL_REVENUE_QOQ = "\u8425\u4e1a\u603b\u6536\u5165-\u5b63\u5ea6\u73af\u6bd4\u589e\u957f"
COL_NET_PROFIT = "\u51c0\u5229\u6da6-\u51c0\u5229\u6da6"
COL_NET_PROFIT_YOY = "\u51c0\u5229\u6da6-\u540c\u6bd4\u589e\u957f"
COL_NET_PROFIT_QOQ = "\u51c0\u5229\u6da6-\u5b63\u5ea6\u73af\u6bd4\u589e\u957f"
COL_NAV = "\u6bcf\u80a1\u51c0\u8d44\u4ea7"
COL_ROE = "\u51c0\u8d44\u4ea7\u6536\u76ca\u7387"
COL_OPERATING_CFPS = "\u6bcf\u80a1\u7ecf\u8425\u73b0\u91d1\u6d41\u91cf"
COL_GROSS_MARGIN = "\u9500\u552e\u6bdb\u5229\u7387"
COL_INDUSTRY = "\u6240\u5c5e\u884c\u4e1a"
COL_ANNOUNCEMENT_DATE = "\u6700\u65b0\u516c\u544a\u65e5\u671f"


def parse_numeric(val):
    """Parse numeric value, handling NaN, empty, and Chinese units."""
    import math
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "")
    if s in ("", "--", "-", "NaN", "null", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(val):
    """Parse date string to datetime.date."""
    from datetime import date as dt_date
    if val is None:
        return None
    s = str(val).strip()
    if not s or s == "NaN":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def main():
    from sqlalchemy import create_engine, text
    from app.config import settings

    periods_to_try = ["20241231", "20240930", "20240630", "20240331"]

    engine = create_engine(settings.database_url)

    # Step 1: Create table
    logger.info("Creating company_financials table if not exists...")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
    logger.info("Table ready.")

    # Step 2: Load active companies from DB
    logger.info("Loading active companies...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, ticker, company_name
            FROM companies
            WHERE ticker IS NOT NULL AND ticker != ''
        """))
        companies = {
            row.ticker.strip(): {"id": row.id, "name": row.company_name}
            for row in result
        }
    logger.info(f"Loaded {len(companies)} companies from DB.")

    # Step 3: Fetch financial data from akshare
    import akshare as ak
    import pandas as pd

    df = None
    used_period = None
    for period in periods_to_try:
        logger.info(f"Trying akshare stock_yjbb_em(date={period})...")
        try:
            df = ak.stock_yjbb_em(date=period)
            if df is not None and len(df) > 0:
                used_period = period
                logger.info(f"Got {len(df)} rows for period {period}")
                break
        except Exception as e:
            logger.warning(f"Period {period} failed: {e}")
            continue

    if df is None or len(df) == 0:
        logger.error("No financial data available from akshare.")
        return

    # Step 4: Filter and match
    df["ticker"] = df[COL_TICKER].astype(str).str.strip()
    df = df[~df["ticker"].str.match(r"^[29]\d{5}$")]
    logger.info(f"After filtering B-shares: {len(df)} rows")

    inserts = []
    matched = 0
    unmatched_tickers = []

    for _, row in df.iterrows():
        ticker = row["ticker"]
        if ticker not in companies:
            unmatched_tickers.append(ticker)
            continue

        company_id = companies[ticker]["id"]

        inserts.append({
            "company_id": company_id,
            "report_period": used_period,
            "report_date": parse_date(used_period),
            "revenue": parse_numeric(row.get(COL_REVENUE)),
            "revenue_yoy": parse_numeric(row.get(COL_REVENUE_YOY)),
            "revenue_qoq": parse_numeric(row.get(COL_REVENUE_QOQ)),
            "net_profit": parse_numeric(row.get(COL_NET_PROFIT)),
            "net_profit_yoy": parse_numeric(row.get(COL_NET_PROFIT_YOY)),
            "net_profit_qoq": parse_numeric(row.get(COL_NET_PROFIT_QOQ)),
            "eps": parse_numeric(row.get(COL_EPS)),
            "nav_per_share": parse_numeric(row.get(COL_NAV)),
            "roe": parse_numeric(row.get(COL_ROE)),
            "operating_cfps": parse_numeric(row.get(COL_OPERATING_CFPS)),
            "gross_margin": parse_numeric(row.get(COL_GROSS_MARGIN)),
            "industry_l2": str(row.get(COL_INDUSTRY)).strip() if pd.notna(row.get(COL_INDUSTRY)) else None,
            "announcement_date": parse_date(row.get(COL_ANNOUNCEMENT_DATE)),
        })
        matched += 1

    logger.info(f"Matched {matched}/{len(df)} rows to companies in DB")
    if unmatched_tickers:
        logger.info(f"Unmatched tickers (first 10): {unmatched_tickers[:10]}")

    if not inserts:
        logger.warning("No records to insert.")
        return

    # Step 5: Bulk insert with ON CONFLICT DO UPDATE
    logger.info(f"Inserting {len(inserts)} records into company_financials...")

    insert_sql = """
    INSERT INTO company_financials (
        company_id, report_period, report_date,
        revenue, revenue_yoy, revenue_qoq,
        net_profit, net_profit_yoy, net_profit_qoq,
        eps, nav_per_share, roe, operating_cfps, gross_margin,
        industry_l2, announcement_date, updated_at
    ) VALUES (
        :company_id, :report_period, :report_date,
        :revenue, :revenue_yoy, :revenue_qoq,
        :net_profit, :net_profit_yoy, :net_profit_qoq,
        :eps, :nav_per_share, :roe, :operating_cfps, :gross_margin,
        :industry_l2, :announcement_date, NOW()
    )
    ON CONFLICT (company_id, report_period) DO UPDATE SET
        report_date = EXCLUDED.report_date,
        revenue = EXCLUDED.revenue,
        revenue_yoy = EXCLUDED.revenue_yoy,
        revenue_qoq = EXCLUDED.revenue_qoq,
        net_profit = EXCLUDED.net_profit,
        net_profit_yoy = EXCLUDED.net_profit_yoy,
        net_profit_qoq = EXCLUDED.net_profit_qoq,
        eps = EXCLUDED.eps,
        nav_per_share = EXCLUDED.nav_per_share,
        roe = EXCLUDED.roe,
        operating_cfps = EXCLUDED.operating_cfps,
        gross_margin = EXCLUDED.gross_margin,
        industry_l2 = EXCLUDED.industry_l2,
        announcement_date = EXCLUDED.announcement_date,
        updated_at = NOW()
    """

    batch_size = 500
    total_inserted = 0
    with engine.begin() as conn:
        for i in range(0, len(inserts), batch_size):
            batch = inserts[i:i + batch_size]
            result = conn.execute(text(insert_sql), batch)
            total_inserted += result.rowcount
            logger.info(f"  Batch {i//batch_size + 1}: inserted/updated {result.rowcount} rows")

    logger.info(f"Done. Total inserted/updated: {total_inserted}")

    # Step 6: Summary stats
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM company_financials WHERE report_period = :p"),
            {"p": used_period}
        ).scalar()
        has_revenue = conn.execute(
            text("SELECT COUNT(*) FROM company_financials WHERE report_period = :p AND revenue IS NOT NULL"),
            {"p": used_period}
        ).scalar()
        has_profit = conn.execute(
            text("SELECT COUNT(*) FROM company_financials WHERE report_period = :p AND net_profit IS NOT NULL"),
            {"p": used_period}
        ).scalar()
        has_roe = conn.execute(
            text("SELECT COUNT(*) FROM company_financials WHERE report_period = :p AND roe IS NOT NULL"),
            {"p": used_period}
        ).scalar()

    logger.info("=" * 50)
    logger.info("FINANCIAL METRICS BACKFILL SUMMARY")
    logger.info(f"  Report period: {used_period}")
    logger.info(f"  Total records: {total}")
    logger.info(f"  With revenue:  {has_revenue} ({has_revenue/total*100:.1f}%)")
    logger.info(f"  With profit:   {has_profit} ({has_profit/total*100:.1f}%)")
    logger.info(f"  With ROE:      {has_roe} ({has_roe/total*100:.1f}%)")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
