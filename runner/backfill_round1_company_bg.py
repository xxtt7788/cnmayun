#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round 1: 公司背景数据回填
- R1.1 十大流通股东 (company_shareholders)
- R1.2 公司规模信息 (companies 扩展字段)

Author: Kimi Code CLI Agent
Date: 2026-04-25
"""
import os
import sys
import time
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

import akshare as ak
import pandas as pd
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)

# Unicode escapes
COL_SH_NAME = "\u80a1\u4e1c\u540d\u79f0"
COL_SH_COUNT = "\u6301\u80a1\u6570\u91cf"
COL_SH_RATIO = "\u6301\u80a1\u6bd4\u4f8b"
COL_SH_CHANGE = "\u53d8\u52a8\u65b9\u5411"

COL_ITEM = "\u9879\u76ee"
COL_VALUE = "\u503c"

# yjbb columns
COL_TICKER = "\u80a1\u7968\u4ee3\u7801"
COL_EMP_COUNT = "\u5458\u5de5\u4eba\u6570"
COL_REG_CAP = "\u6ce8\u518c\u8d44\u672c"


def load_companies():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, ticker, exchange, company_name, market_cap, registered_capital, employee_count
            FROM companies WHERE is_active = true ORDER BY id
        """)).fetchall()
    return rows


def backfill_shareholders(company_rows):
    """R1.1: 十大流通股东"""
    total = len(company_rows)
    inserted = 0
    skipped = 0
    errors = 0

    for idx, row in enumerate(company_rows, 1):
        ticker = row.ticker.strip()
        company_id = row.id
        try:
            df = ak.stock_gdfx_top_10_em(symbol=ticker)
            if df is None or df.empty:
                skipped += 1
                time.sleep(0.3)
                continue

            records = []
            for _, r in df.iterrows():
                name = str(r.get(COL_SH_NAME) or "").strip()
                if not name:
                    continue
                count = r.get(COL_SH_COUNT)
                ratio = r.get(COL_SH_RATIO)
                change = str(r.get(COL_SH_CHANGE) or "").strip() or None
                # 推断股东类型
                sh_type = "individual"
                if any(kw in name for kw in ["\u516c\u53f8", "\u96c6\u56e2", "\u6295\u8d44", "\u57fa\u91d1", "\u793e\u4fdd", "\u4fdd\u9669", "\u8d22\u56e2", "\u4fe1\u6258", "\u8bc1\u5238"]):
                    sh_type = "institutional"
                if any(kw in name for kw in ["\u56fd\u5bb6\u80a1", "\u56fd\u6709", "\u56fd\u8d44", "\u56fd\u5bb6\u96c6\u56e2"]):
                    sh_type = "state"

                records.append({
                    "company_id": company_id,
                    "shareholder_name": name,
                    "shareholder_type": sh_type,
                    "share_count": int(count) if pd.notna(count) else None,
                    "share_ratio": float(ratio) if pd.notna(ratio) else None,
                    "change_direction": change,
                    "report_date": None,
                })

            if records:
                with engine.begin() as conn:
                    for rec in records:
                        conn.execute(text("""
                            INSERT INTO company_shareholders
                            (company_id, shareholder_name, shareholder_type, share_count, share_ratio, change_direction, report_date)
                            VALUES (:company_id, :shareholder_name, :shareholder_type, :share_count, :share_ratio, :change_direction, :report_date)
                            ON CONFLICT (company_id, shareholder_name, report_date) DO NOTHING
                        """), rec)
                inserted += len(records)

        except Exception as e:
            errors += 1
            logger.warning(f"[{idx}/{total}] {ticker} shareholder error: {e}")

        if idx % 100 == 0:
            logger.info(f"Shareholders progress: {idx}/{total}, inserted={inserted}, skipped={skipped}, errors={errors}")
        time.sleep(0.3)

    logger.info(f"R1.1 DONE: inserted={inserted}, skipped={skipped}, errors={errors}")


def backfill_company_scale(company_rows):
    """R1.2: 公司规模信息 (市值 + yjbb 注册资本/员工数)"""
    total = len(company_rows)
    updated = 0
    skipped = 0
    errors = 0

    # 先批量获取 yjbb 数据，避免每次循环都调用 API
    logger.info("Prefetching stock_yjbb_em (2024年报)...")
    try:
        yjbb_df = ak.stock_yjbb_em(date="20241231")
        if yjbb_df is not None and not yjbb_df.empty:
            yjbb_df[COL_TICKER] = yjbb_df[COL_TICKER].astype(str).str.strip()
            yjbb_lookup = {}
            for _, r in yjbb_df.iterrows():
                t = r[COL_TICKER]
                if t not in yjbb_lookup:
                    yjbb_lookup[t] = r
            logger.info(f"YJBB lookup built: {len(yjbb_lookup)} entries")
        else:
            yjbb_lookup = {}
            logger.warning("YJBB empty")
    except Exception as e:
        logger.warning(f"YJBB fetch failed: {e}")
        yjbb_lookup = {}

    for idx, row in enumerate(company_rows, 1):
        ticker = row.ticker.strip()
        company_id = row.id
        needs_update = row.market_cap is None or row.registered_capital is None or row.employee_count is None
        if not needs_update:
            skipped += 1
            continue

        market_cap = None
        reg_cap = None
        emp_count = None

        # Part A: individual_info_em for market_cap
        if row.market_cap is None:
            try:
                df = ak.stock_individual_info_em(symbol=ticker)
                if df is not None and not df.empty:
                    info = {}
                    for _, r in df.iterrows():
                        item = str(r.get(COL_ITEM) or "").strip()
                        val = r.get(COL_VALUE)
                        info[item] = val
                    if "\u603b\u5e02\u503c" in info:
                        cap_str = str(info["\u603b\u5e02\u503c"] or "").replace(",", "").strip()
                        try:
                            market_cap = float(cap_str)
                        except ValueError:
                            pass
            except Exception as e:
                logger.debug(f"{ticker} individual_info error: {e}")

        # Part B: yjbb lookup for reg_cap & emp_count
        if row.registered_capital is None or row.employee_count is None:
            yjbb_row = yjbb_lookup.get(ticker)
            if yjbb_row is not None:
                # 员工人数
                if pd.notna(yjbb_row.get(COL_EMP_COUNT)):
                    try:
                        emp_count = int(float(str(yjbb_row[COL_EMP_COUNT]).replace(",", "")))
                    except (ValueError, TypeError):
                        pass
                # 注册资本 (yjbb 里可能没有，尝试模糊匹配)
                for col in yjbb_df.columns if 'yjbb_df' in dir() else []:
                    col_str = str(col)
                    if "\u6ce8\u518c\u8d44\u672c" in col_str and pd.notna(yjbb_row.get(col)):
                        try:
                            reg_cap = float(str(yjbb_row[col]).replace(",", ""))
                            break
                        except (ValueError, TypeError):
                            pass

        # 执行更新
        try:
            with engine.begin() as conn:
                if market_cap is not None:
                    conn.execute(text("UPDATE companies SET market_cap = :cap WHERE id = :id"), {"cap": market_cap, "id": company_id})
                if reg_cap is not None:
                    conn.execute(text("UPDATE companies SET registered_capital = :cap WHERE id = :id"), {"cap": reg_cap, "id": company_id})
                if emp_count is not None:
                    conn.execute(text("UPDATE companies SET employee_count = :cnt WHERE id = :id"), {"cnt": emp_count, "id": company_id})
            if market_cap is not None or reg_cap is not None or emp_count is not None:
                updated += 1
        except Exception as e:
            errors += 1
            logger.warning(f"[{idx}/{total}] {ticker} update error: {e}")

        if idx % 100 == 0:
            logger.info(f"Scale progress: {idx}/{total}, updated={updated}, skipped={skipped}, errors={errors}")
        time.sleep(0.2)

    logger.info(f"R1.2 DONE: updated={updated}, skipped={skipped}, errors={errors}")


def main():
    companies = load_companies()
    logger.info(f"Loaded {len(companies)} companies")

    logger.info("=" * 60)
    logger.info("START R1.1: Company Shareholders")
    logger.info("=" * 60)
    backfill_shareholders(companies)

    logger.info("=" * 60)
    logger.info("START R1.2: Company Scale Info")
    logger.info("=" * 60)
    backfill_company_scale(companies)

    logger.info("=" * 60)
    logger.info("ROUND 1 (R1.1 + R1.2) COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
