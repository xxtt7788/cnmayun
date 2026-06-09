#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill basic info for BJ stocks (Beijing Stock Exchange / NEEQ)
using akshare stock_info_bj_name_code.

Fills: industry_l2, province from akshare BJ stock list.

Author: Kimi Code CLI Agent | Date: 2026-04-28
"""

import os
import sys
import logging

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

# Unicode escapes for akshare column names
COL_TICKER = "\u8bc1\u5238\u4ee3\u7801"      # 证券代码
COL_NAME = "\u8bc1\u5238\u540d\u79f0"        # 证券名称
COL_INDUSTRY = "\u6240\u5c5e\u884c\u4e1a"    # 所属行业
COL_REGION = "\u5730\u533a"                  # 地区
COL_LIST_DATE = "\u4e0a\u5e02\u65e5\u671f"   # 上市日期


def main():
    from sqlalchemy import create_engine, text
    from app.config import settings

    engine = create_engine(settings.database_url)

    # Load BJ companies from DB
    logger.info("Loading BJ companies from DB...")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, ticker, company_name, industry_l2, province, city
            FROM companies
            WHERE is_active = true AND ticker ~ '^[489]'
            ORDER BY ticker
        """)).fetchall()

    bj_companies = {row.ticker.strip(): row for row in rows}
    logger.info(f"Found {len(bj_companies)} BJ companies in DB")

    # Fetch from akshare
    logger.info("Fetching BJ stock list from akshare...")
    import akshare as ak
    import pandas as pd

    try:
        df = ak.stock_info_bj_name_code()
    except Exception as e:
        logger.error(f"akshare failed: {e}")
        return

    logger.info(f"akshare returned {len(df)} BJ stocks")

    # Build lookup by ticker
    df["ticker"] = df[COL_TICKER].astype(str).str.strip()
    ak_data = {}
    for _, row in df.iterrows():
        ticker = row["ticker"]
        ak_data[ticker] = {
            "name": str(row.get(COL_NAME) or "").strip(),
            "industry": str(row.get(COL_INDUSTRY) or "").strip() or None,
            "region": str(row.get(COL_REGION) or "").strip() or None,
            "list_date": row.get(COL_LIST_DATE),
        }

    logger.info(f"Built lookup for {len(ak_data)} akshare BJ stocks")

    # Match and build updates
    updates_industry = {}
    updates_province = {}
    matched = 0
    unmatched = []

    for ticker, db_row in bj_companies.items():
        if ticker in ak_data:
            data = ak_data[ticker]
            matched += 1
            if data["industry"] and not db_row.industry_l2:
                updates_industry[db_row.id] = data["industry"]
            if data["region"] and not db_row.province:
                updates_province[db_row.id] = data["region"]
        else:
            unmatched.append(ticker)

    logger.info(f"Matched {matched}/{len(bj_companies)} BJ stocks from akshare")
    logger.info(f"Unmatched: {len(unmatched)}")
    if unmatched:
        logger.info(f"Sample unmatched: {unmatched[:20]}")

    # Execute updates
    total_updated = 0
    with engine.begin() as conn:
        if updates_industry:
            for cid, val in updates_industry.items():
                conn.execute(
                    text("UPDATE companies SET industry_l2 = :val WHERE id = :id"),
                    {"id": cid, "val": val}
                )
            logger.info(f"Updated industry_l2 for {len(updates_industry)} companies")
            total_updated += len(updates_industry)

        if updates_province:
            for cid, val in updates_province.items():
                conn.execute(
                    text("UPDATE companies SET province = :val WHERE id = :id"),
                    {"id": cid, "val": val}
                )
            logger.info(f"Updated province for {len(updates_province)} companies")
            total_updated += len(updates_province)

    # Summary
    with engine.connect() as conn:
        total_bj = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true AND ticker ~ '^[489]'")).scalar()
        has_ind = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true AND ticker ~ '^[489]' AND industry_l2 IS NOT NULL")).scalar()
        has_prov = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true AND ticker ~ '^[489]' AND province IS NOT NULL")).scalar()
        has_city = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true AND ticker ~ '^[489]' AND city IS NOT NULL")).scalar()

    logger.info("=" * 50)
    logger.info("BJ STOCK BACKFILL SUMMARY")
    logger.info(f"  Total BJ:       {total_bj}")
    logger.info(f"  industry_l2:    {has_ind} ({has_ind/total_bj*100:.1f}%)")
    logger.info(f"  province:       {has_prov} ({has_prov/total_bj*100:.1f}%)")
    logger.info(f"  city:           {has_city} ({has_city/total_bj*100:.1f}%)")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
