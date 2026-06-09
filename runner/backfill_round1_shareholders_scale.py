#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round 1.1 + R1.2: 十大流通股东 + 公司规模信息
使用 EastMoney emweb 接口（urllib.request）

Author: Kimi Code CLI Agent
Date: 2026-04-25
"""
import json
import os
import sys
import time
import logging
from urllib.request import Request, urlopen

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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)
EASTMONEY_REFERER = "https://emweb.securities.eastmoney.com/"

SDGD_API = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageSDGD"
SURVEY_API = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"


def build_em_code(ticker: str, exchange: str) -> str:
    ticker = str(ticker).strip()
    exchange = str(exchange or "").strip().upper()
    if exchange == "SHSE" or ticker.startswith("6") or ticker.startswith("5"):
        return f"SH{ticker}"
    elif exchange == "BJSE" or ticker.startswith("4") or ticker.startswith("8") or ticker.startswith("9"):
        return f"BJ{ticker}"
    return f"SZ{ticker}"


def fetch_json(url: str, timeout: int = 15) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Referer": EASTMONEY_REFERER})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"fetch error: {url[:80]}... -> {e}")
        return {}


def backfill_shareholders(companies):
    """R1.1: 十大流通股东"""
    total = len(companies)
    inserted = 0
    skipped = 0
    errors = 0

    for idx, row in enumerate(companies, 1):
        ticker = row.ticker.strip()
        em_code = build_em_code(ticker, row.exchange)
        company_id = row.id

        try:
            # Try latest quarter first, then fallback
            dates = ["2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31"]
            data = None
            for d in dates:
                url = f"{SDGD_API}?code={em_code}&date={d}"
                resp = fetch_json(url)
                if resp and "sdgd" in resp and resp["sdgd"]:
                    data = resp["sdgd"]
                    break

            if not data:
                skipped += 1
                continue

            records = []
            for item in data:
                name = str(item.get("HOLDER_NAME") or "").strip()
                if not name:
                    continue
                count = item.get("HOLD_NUM")
                ratio = item.get("HOLD_NUM_RATIO")
                change = str(item.get("HOLD_NUM_CHANGE") or "").strip() or None
                shares_type = str(item.get("SHARES_TYPE") or "").strip() or None

                sh_type = "individual"
                if any(kw in name for kw in ["\u516c\u53f8", "\u96c6\u56e2", "\u6295\u8d44", "\u57fa\u91d1", "\u793e\u4fdd", "\u4fdd\u9669", "\u8d22\u56e2", "\u4fe1\u6258", "\u8bc1\u5238"]):
                    sh_type = "institutional"
                if any(kw in name for kw in ["\u56fd\u5bb6\u80a1", "\u56fd\u6709", "\u56fd\u8d44", "\u56fd\u5bb6\u96c6\u56e2"]):
                    sh_type = "state"

                records.append({
                    "company_id": company_id,
                    "shareholder_name": name,
                    "shareholder_type": sh_type,
                    "share_count": int(count) if count is not None else None,
                    "share_ratio": float(ratio) if ratio is not None else None,
                    "change_direction": change,
                    "report_date": d,
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
            if errors <= 10 or idx % 100 == 0:
                logger.warning(f"[{idx}/{total}] {ticker} shareholder error: {e}")

        if idx % 100 == 0:
            logger.info(f"Shareholders: {idx}/{total}, inserted={inserted}, skipped={skipped}, errors={errors}")
        time.sleep(0.3)

    logger.info(f"R1.1 DONE: inserted={inserted}, skipped={skipped}, errors={errors}")


def backfill_company_scale(companies):
    """R1.2: 公司规模信息（注册资本、员工数）"""
    total = len(companies)
    updated = 0
    skipped = 0
    errors = 0

    for idx, row in enumerate(companies, 1):
        ticker = row.ticker.strip()
        em_code = build_em_code(ticker, row.exchange)
        company_id = row.id
        needs_update = row.registered_capital is None or row.employee_count is None or row.market_cap is None
        if not needs_update:
            skipped += 1
            continue

        try:
            url = f"{SURVEY_API}?code={em_code}"
            resp = fetch_json(url)
            if not resp or "jbzl" not in resp:
                skipped += 1
                continue

            jbzl = resp["jbzl"]
            reg_cap = None
            emp_count = None

            # 注册资本
            zczb = str(jbzl.get("zczb") or "").strip()
            if zczb:
                # Parse like "194.1亿" or "5000万" or "10000万元"
                import re
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

            # 员工人数
            gyrs = jbzl.get("gyrs")
            if gyrs is not None:
                try:
                    emp_count = int(gyrs)
                except (ValueError, TypeError):
                    pass

            with engine.begin() as conn:
                if reg_cap is not None and row.registered_capital is None:
                    conn.execute(text("UPDATE companies SET registered_capital = :cap WHERE id = :id"), {"cap": reg_cap, "id": company_id})
                if emp_count is not None and row.employee_count is None:
                    conn.execute(text("UPDATE companies SET employee_count = :cnt WHERE id = :id"), {"cnt": emp_count, "id": company_id})
            if reg_cap is not None or emp_count is not None:
                updated += 1

        except Exception as e:
            errors += 1
            if errors <= 10 or idx % 100 == 0:
                logger.warning(f"[{idx}/{total}] {ticker} scale error: {e}")

        if idx % 100 == 0:
            logger.info(f"Scale: {idx}/{total}, updated={updated}, skipped={skipped}, errors={errors}")
        time.sleep(0.3)

    logger.info(f"R1.2 DONE: updated={updated}, skipped={skipped}, errors={errors}")


def main():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, ticker, exchange, company_name, market_cap, registered_capital, employee_count
            FROM companies WHERE is_active = true ORDER BY id
        """)).fetchall()
    companies = rows
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
