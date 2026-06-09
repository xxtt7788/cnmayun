#!/usr/bin/env python3
"""
Backfill company location using engine.begin() (proven to commit correctly).

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys
import time
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENV_PATH = "/etc/china-succession/china-succession.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.startswith("export "):
                    key = key[7:]
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value

import requests
from app.db import engine
from sqlalchemy import text

EASTMONEY_SURVEY_API = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PROVINCES = {"北京", "上海", "天津", "重庆"}
COMMIT_EVERY = 50


def build_em_code(ticker: str) -> str:
    ticker = str(ticker).strip()
    if ticker.startswith(("0", "3")):
        return f"SZ{ticker}"
    if ticker.startswith(("4", "8", "9", "92")):
        return f"BJ{ticker}"
    return f"SH{ticker}"


def extract_city(zcdz: str, province: str) -> str:
    if not zcdz or not province:
        return ""
    if province in PROVINCES:
        return province
    remaining = zcdz
    for prefix in [province + "省", province, province + "自治区"]:
        if remaining.startswith(prefix):
            remaining = remaining[len(prefix):]
            break
    for suffix in ["壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "自治州"]:
        if remaining.startswith(suffix):
            remaining = remaining[len(suffix):]
            break
    m = re.search(r'^(.+?)(市|县)', remaining)
    if m:
        return m.group(1)
    return ""


def fetch_company_survey(ticker: str) -> dict:
    em_code = build_em_code(ticker)
    url = f"{EASTMONEY_SURVEY_API}?code={em_code}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=(5, 15))
        resp.raise_for_status()
        data = resp.json()
        if data is None:
            return {}
        return data.get("jbzl", {})
    except Exception:
        return {}


def main():
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, ticker FROM companies 
                WHERE is_active = TRUE 
                AND (industry_l2 IS NULL OR province IS NULL OR city IS NULL)
                AND ticker NOT LIKE '4%' AND ticker NOT LIKE '8%' AND ticker NOT LIKE '9%'
                ORDER BY id
            """)
        ).fetchall()
        companies = [(r[0], r[1]) for r in rows]

    print(f"Companies to process: {len(companies)}")
    if not companies:
        print("Nothing to do.")
        return

    updates = []
    updated = 0
    failed = 0
    committed = 0
    start_time = time.time()

    for i, (cid, ticker) in enumerate(companies):
        try:
            jbzl = fetch_company_survey(ticker)
            if not jbzl:
                failed += 1
                continue

            industry_l2 = ""
            sszjhhy = jbzl.get("sszjhhy", "")
            if sszjhhy and "-" in sszjhhy:
                industry_l2 = sszjhhy.split("-")[-1].strip()
            elif sszjhhy:
                industry_l2 = sszjhhy.strip()

            province = jbzl.get("qy", "")
            city = ""
            zcdz = jbzl.get("zcdz", "")
            if province:
                if province in PROVINCES:
                    city = province
                else:
                    city = extract_city(zcdz, province)

            if industry_l2 or province or city:
                updates.append({"id": cid, "industry_l2": industry_l2, "province": province, "city": city})
                updated += 1
        except Exception as e:
            failed += 1
            print(f"  ERROR {ticker}: {e}")

        if (i + 1) % COMMIT_EVERY == 0:
            if updates:
                with engine.begin() as conn:
                    for u in updates:
                        fields = []
                        params = {"id": u["id"]}
                        if u["industry_l2"]:
                            fields.append("industry_l2 = :industry_l2")
                            params["industry_l2"] = u["industry_l2"]
                        if u["province"]:
                            fields.append("province = :province")
                            params["province"] = u["province"]
                        if u["city"]:
                            fields.append("city = :city")
                            params["city"] = u["city"]
                        if fields:
                            sql = f"UPDATE companies SET {', '.join(fields)} WHERE id = :id"
                            result = conn.execute(text(sql), params)
                            committed += result.rowcount
                updates = []
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  Progress: {i+1}/{len(companies)} | updated={updated} | committed={committed} | failed={failed} | {rate:.1f}/sec")

        time.sleep(0.2)

    # Final commit
    if updates:
        with engine.begin() as conn:
            for u in updates:
                fields = []
                params = {"id": u["id"]}
                if u["industry_l2"]:
                    fields.append("industry_l2 = :industry_l2")
                    params["industry_l2"] = u["industry_l2"]
                if u["province"]:
                    fields.append("province = :province")
                    params["province"] = u["province"]
                if u["city"]:
                    fields.append("city = :city")
                    params["city"] = u["city"]
                if fields:
                    sql = f"UPDATE companies SET {', '.join(fields)} WHERE id = :id"
                    result = conn.execute(text(sql), params)
                    committed += result.rowcount

    print(f"\nUpdated: {updated}, Committed: {committed}, Failed: {failed}")
    print(f"Total time: {time.time() - start_time:.1f}s")


if __name__ == "__main__":
    main()
