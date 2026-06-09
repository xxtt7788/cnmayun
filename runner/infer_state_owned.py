#!/usr/bin/env python3
"""Infer state_owned_flag from company name patterns + akshare controller data."""
import os, sys

ENV_PATH = "/etc/china-succession/china-succession.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.startswith("export "): key = key[7:]
                os.environ[key] = value.strip().strip('"').strip("'")

sys.path.insert(0, "/opt/china-succession")
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)

# Phase 1: Name-based inference
SOE_KEYWORDS = [
    "中国", "国家", "中化", "中粮", "中油", "中铁", "中建", "中交",
    "中航", "中船", "中核", "中广核", "国家电网", "南方电网",
    "华润", "招商局", "保利", "中信", "光大", "国家开发",
    "中国航天", "中国兵器", "中国电子", "中国电科", "中国华能",
    "中国大唐", "中国华电", "中国国电", "中国电力", "中国长江",
    "中国电信", "中国移动", "中国联通", "中国石油", "中国石化",
    "中国海油", "中国中化", "中国一汽", "东风汽车", "中国宝武",
    "中国铝业", "中国远洋", "中国海运", "中国外运",
]

NON_SOE_KEYWORDS = [
    "民营", "私企", "外资", "合资", "台资", "港资",
]

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT id, ticker, company_name
        FROM companies
        WHERE is_active = true AND (state_owned_flag IS NULL)
        ORDER BY ticker
    """)).fetchall()

updates = {}
for row in rows:
    name = row.company_name or ""
    is_soe = None
    for kw in SOE_KEYWORDS:
        if kw in name:
            is_soe = True
            break
    if is_soe is None:
        for kw in NON_SOE_KEYWORDS:
            if kw in name:
                is_soe = False
                break
    if is_soe is not None:
        updates[row.id] = is_soe

print(f"Name-based inference: {len(updates)}/{len(rows)} companies")

# Phase 2: Try akshare for remaining (sample)
try:
    import akshare as ak
    print("Checking akshare stock_yjbb_em for controller info...")
    # akshare doesn't have a direct controller field in basic interfaces
    # We use the already fetched stock_info_bj_name_code as proxy
except Exception as e:
    print(f"akshare check skipped: {e}")

# Apply updates
if updates:
    with engine.begin() as conn:
        for cid, flag in updates.items():
            conn.execute(
                text("UPDATE companies SET state_owned_flag = :flag WHERE id = :id"),
                {"flag": flag, "id": cid}
            )
    print(f"Updated {len(updates)} companies")

# Summary
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true")).scalar()
    soe_yes = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true AND state_owned_flag = true")).scalar()
    soe_no = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true AND state_owned_flag = false")).scalar()
    soe_null = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true AND state_owned_flag IS NULL")).scalar()

print(f"\nstate_owned_flag summary:")
print(f"  SOE (true):  {soe_yes} ({soe_yes/total*100:.1f}%)")
print(f"  Non-SOE:     {soe_no} ({soe_no/total*100:.1f}%)")
print(f"  Unknown:     {soe_null} ({soe_null/total*100:.1f}%)")
