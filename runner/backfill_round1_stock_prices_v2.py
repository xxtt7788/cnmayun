#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round 1.3: 股价历史（近1年）回填到 company_stock_prices
使用 baostock

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

import baostock as bs
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)

START_DATE = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
END_DATE = datetime.now().strftime("%Y-%m-%d")
BATCH_SIZE = 500


def to_baostock_code(ticker: str, exchange: str) -> str:
    ticker = str(ticker).strip()
    exchange = str(exchange or "").strip().upper()
    if exchange == "SHSE" or ticker.startswith("6") or ticker.startswith("5"):
        return f"sh.{ticker}"
    elif exchange == "BJSE" or ticker.startswith("4") or ticker.startswith("8") or ticker.startswith("9"):
        return f"bj.{ticker}"
    return f"sz.{ticker}"


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

    lg = bs.login()
    logger.info(f"baostock login: {lg.error_msg}")

    inserted_total = 0
    skipped_total = 0
    errors_total = 0
    batch = []

    for idx, row in enumerate(companies, 1):
        ticker = row.ticker.strip()
        bs_code = to_baostock_code(ticker, row.exchange)
        company_id = row.id

        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,volume,amount",
                start_date=START_DATE,
                end_date=END_DATE,
                frequency="d",
                adjustflag="3"  # 复权: 1=后复权, 2=前复权, 3=不复权
            )
            if rs.error_code != '0':
                logger.warning(f"[{idx}/{total}] {ticker} bs error: {rs.error_msg}")
                errors_total += 1
                continue

            data = []
            while rs.next():
                data.append(rs.get_row_data())

            if not data:
                skipped_total += 1
                continue

            for item in data:
                # item: [date, code, open, high, low, close, volume, amount]
                batch.append({
                    "company_id": company_id,
                    "trade_date": item[0],
                    "open": float(item[2]) if item[2] else None,
                    "high": float(item[3]) if item[3] else None,
                    "low": float(item[4]) if item[4] else None,
                    "close": float(item[5]) if item[5] else None,
                    "volume": int(float(item[6])) if item[6] else None,
                    "amount": float(item[7]) if item[7] else None,
                })

            inserted_total += len(data)

        except Exception as e:
            errors_total += 1
            if errors_total <= 10 or idx % 100 == 0:
                logger.warning(f"[{idx}/{total}] {ticker} error: {e}")

        if len(batch) >= BATCH_SIZE:
            _insert_batch(batch)
            batch = []

        if idx % 100 == 0:
            logger.info(f"Progress: {idx}/{total}, inserted={inserted_total}, skipped={skipped_total}, errors={errors_total}, batch_pending={len(batch)}")

        time.sleep(0.05)  # baostock 限速较低

    if batch:
        _insert_batch(batch)

    bs.logout()
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
