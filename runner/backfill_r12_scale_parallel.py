#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R1.2 only: 公司规模信息 — 多线程并发版（curl + ThreadPoolExecutor）

Author: Kimi Code CLI Agent
Date: 2026-04-25
"""
import json
import os
import sys
import logging
import subprocess
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

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

from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)

CURL_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
MAX_WORKERS = 5


def build_em_code(ticker: str, exchange: str) -> str:
    ticker = str(ticker).strip()
    exchange = str(exchange or "").strip().upper()
    if exchange == "SHSE" or ticker.startswith("6") or ticker.startswith("5"):
        return f"SH{ticker}"
    elif exchange == "BJSE" or ticker.startswith("4") or ticker.startswith("8") or ticker.startswith("9"):
        return f"BJ{ticker}"
    return f"SZ{ticker}"


def fetch_scale(row) -> tuple:
    ticker = row.ticker.strip()
    em_code = build_em_code(ticker, row.exchange)
    company_id = row.id

    try:
        url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax?code={em_code}"
        result = subprocess.run(
            ["curl", "-s", "-m", str(CURL_TIMEOUT), "-H", f"User-Agent: {USER_AGENT}", url],
            capture_output=True, text=True, timeout=CURL_TIMEOUT + 5
        )
        if result.returncode != 0:
            return (company_id, None, None, "curl_fail")

        resp = json.loads(result.stdout)
        if not resp or "jbzl" not in resp:
            return (company_id, None, None, "no_data")

        jbzl = resp["jbzl"]
        reg_cap = None
        emp_count = None

        zczb = str(jbzl.get("zczb") or "").strip()
        if zczb:
            m = re.match(r"([\d.]+)\s*([万亿万]?)", zczb)
            if m:
                num = float(m.group(1))
                unit = m.group(2)
                if unit == "\u4ebf":
                    reg_cap = num * 1e8
                elif unit == "\u4e07":
                    reg_cap = num * 1e4
                elif unit == "\u5343":
                    reg_cap = num * 1e3
                else:
                    reg_cap = num

        gyrs = jbzl.get("gyrs")
        if gyrs is not None:
            try:
                emp_count = int(gyrs)
            except (ValueError, TypeError):
                pass

        return (company_id, reg_cap, emp_count, "ok")
    except Exception:
        return (company_id, None, None, "error")


def main():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, ticker, exchange, registered_capital, employee_count
            FROM companies
            WHERE is_active = true AND (registered_capital IS NULL OR employee_count IS NULL)
            ORDER BY id
        """)).fetchall()

    total = len(rows)
    logger.info(f"Companies needing scale info: {total}")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_row = {executor.submit(fetch_scale, row): row for row in rows}
        for future in as_completed(future_to_row):
            results.append(future.result())
            if len(results) % 100 == 0:
                logger.info(f"Fetched: {len(results)}/{total}")

    # Batch update
    updated = 0
    skipped = 0
    errors = 0

    with engine.begin() as conn:
        for company_id, reg_cap, emp_count, status in results:
            if status == "ok":
                if reg_cap is not None:
                    conn.execute(text("UPDATE companies SET registered_capital = :cap WHERE id = :id"), {"cap": reg_cap, "id": company_id})
                if emp_count is not None:
                    conn.execute(text("UPDATE companies SET employee_count = :cnt WHERE id = :id"), {"cnt": emp_count, "id": company_id})
                if reg_cap is not None or emp_count is not None:
                    updated += 1
                else:
                    skipped += 1
            elif status == "no_data":
                skipped += 1
            else:
                errors += 1

    logger.info(f"R1.2 DONE: total={total}, updated={updated}, skipped={skipped}, errors={errors}")


if __name__ == "__main__":
    main()
