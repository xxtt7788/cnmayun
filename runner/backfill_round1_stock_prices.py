#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round 1.3: 股价历史（近1年）回填到 company_stock_prices

Author: Kimi Code CLI Agent
Date: 2026-04-25
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta

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

# Unicode escapes for akshare columns
COL_DATE = "\u65e5\u671f"
COL_OPEN = "\u5f00\u76d8"
COL_HIGH = "\u6700\u9ad8"
COL_LOW = "\u6700\u4f4e"
COL_CLOSE = "\u6536\u76d8"
COL_VOLUME = "\u6210\u4ea4\u91cf"
COL_AMOUNT = "\u6210\u4ea4\u989d"

START_DATE = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
END_DATE = datetime.now().strftime("%Y%m%d")

BATCH_SIZE = 500  # insert batch size


def load_companies():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, ticker, exchange FROM companies
            WHERE is_active = true ORDER BY id
        """)).fetchall()
    return rows


def backfill_stock_prices():
    companies = load_companies()
    total = len(companies)
    logger.info(f"Companies to process: {total}")
    logger.info(f"Date range: {START_DATE} ~ {END_DATE}")

    inserted_total = 0
    skipped_total = 0
    errors_total = 0
    batch = []

    for idx, row in enumerate(companies, 1):
        ticker = row.ticker.strip()
        company_id = row.id

        try:
            df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=START_DATE, end_date=END_DATE, adjust="qfq")
            if df is None or df.empty:
                skipped_total += 1
                time.sleep(0.2)
                continue

            for _, r in df.iterrows():
                trade_date = r.get(COL_DATE)
                if trade_date is None:
                    continue
                # parse date
                if isinstance(trade_date, str):
                    try:
                        trade_date = pd.to_datetime(trade_date).date()
                    except Exception:
                        continue
                elif isinstance(trade_date, pd.Timestamp):
                    trade_date = trade_date.date()
                else:
                    continue

                batch.append({
                    "company_id": company_id,
                    "trade_date": trade_date,
                    "open": float(r[COL_OPEN]) if pd.notna(r.get(COL_OPEN)) else None,
                    "high": float(r[COL_HIGH]) if pd.notna(r.get(COL_HIGH)) else None,
                    "low": float(r[COL_LOW]) if pd.notna(r.get(COL_LOW)) else None,
                    "close": float(r[COL_CLOSE]) if pd.notna(r.get(COL_CLOSE)) else None,
                    "volume": int(r[COL_VOLUME]) if pd.notna(r.get(COL_VOLUME)) else None,
                    "amount": float(r[COL_AMOUNT]) if pd.notna(r.get(COL_AMOUNT)) else None,
                })

            inserted_total += len(df)

        except Exception as e:
            errors_total += 1
            if errors_total <= 10 or idx % 100 == 0:
                logger.warning(f"[{idx}/{total}] {ticker} error: {e}")

        if len(batch) >= BATCH_SIZE:
            _insert_batch(batch)
            batch = []

        if idx % 100 == 0:
            logger.info(f"Progress: {idx}/{total}, inserted={inserted_total}, skipped={skipped_total}, errors={errors_total}, batch_pending={len(batch)}")

        time.sleep(0.15)

    if batch:
        _insert_batch(batch)

    logger.info("=" * 60)
    logger.info(f"R1.3 DONE: total_companies={total}, rows_inserted={inserted_total}, skipped={skipped_total}, errors={errors_total}")
    logger.info("=" * 60)


def _insert_batch(batch):
    if not batch:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO company_stock_prices
                (company_id, trade_date, open, high, low, close, volume, amount)
                VALUES (:company_id, :trade_date, :open, :high, :low, :close, :volume, :amount)
                ON CONFLICT (company_id, trade_date) DO NOTHING
            """), batch)
    except Exception as e:
        logger.error(f"Batch insert error ({len(batch)} rows): {e}")


if __name__ == "__main__":
    backfill_stock_prices()
