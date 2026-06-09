#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill multi-period financial data from akshare.

Fetches quarterly and annual reports for 2023-2024.

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

COL_TICKER = "\u80a1\u7968\u4ee3\u7801"
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
    import akshare as ak
    import pandas as pd

    engine = create_engine(settings.database_url)

    periods = ["20241231", "20240930", "20240630", "20240331"]

    # Load company ticker -> id mapping
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, ticker FROM companies WHERE is_active = true AND ticker IS NOT NULL")).fetchall()
        companies = {r.ticker.strip(): r.id for r in rows}

    logger.info(f"Loaded {len(companies)} active companies")

    total_inserted = 0

    for period in periods:
        logger.info(f"\n--- Processing period {period} ---")
        try:
            df = ak.stock_yjbb_em(date=period)
        except Exception as e:
            logger.warning(f"Period {period} failed: {e}")
            continue

        if df is None or len(df) == 0:
            logger.warning(f"Period {period}: no data")
            continue

        df["ticker"] = df[COL_TICKER].astype(str).str.strip()
        df = df[~df["ticker"].str.match(r"^[29]\d{5}$")]

        inserts = []
        for _, row in df.iterrows():
            ticker = row["ticker"]
            if ticker not in companies:
                continue

            inserts.append({
                "company_id": companies[ticker],
                "report_period": period,
                "report_date": parse_date(period),
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

        if not inserts:
            logger.info(f"Period {period}: no matched records")
            continue

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
        period_inserted = 0
        with engine.begin() as conn:
            for i in range(0, len(inserts), batch_size):
                batch = inserts[i:i + batch_size]
                result = conn.execute(text(insert_sql), batch)
                period_inserted += result.rowcount

        total_inserted += period_inserted
        logger.info(f"Period {period}: inserted/updated {period_inserted} records")

    logger.info(f"\n{'='*50}")
    logger.info(f"TOTAL inserted/updated across all periods: {total_inserted}")

    # Summary
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM company_financials")).scalar()
        periods_cnt = conn.execute(text("SELECT COUNT(DISTINCT report_period) FROM company_financials")).scalar()
    logger.info(f"Total financial records: {total}")
    logger.info(f"Distinct periods: {periods_cnt}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
