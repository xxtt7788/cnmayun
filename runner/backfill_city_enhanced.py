#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced city parser for registered_address.

Handles:
- 省/自治区/直辖市
- 市/地区/自治州/盟
- 县/县级市
- Special cases (海南省县级市, 新疆地区, 内蒙古盟)

Author: Kimi Code CLI Agent | Date: 2026-04-28
"""

import os
import sys
import re
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


def parse_city(addr):
    """
    Parse city from Chinese registered address.
    Returns city name or None.
    """
    if not addr:
        return None

    addr = str(addr).strip()
    if len(addr) < 6:
        return None

    # 1. Direct cities (直辖市)
    for city in ["北京市", "上海市", "天津市", "重庆市"]:
        if city in addr:
            return city

    # 2. Province/自治区 + city
    # Match: 省/自治区 + (NOT 省/市/县) + 市
    m = re.search(r'(?:省|自治区)([^省市县区旗]+?市)', addr)
    if m:
        city = m.group(1)
        # Filter out special zones
        if not any(z in city for z in ['高新', '开发', '经济', '产业', '保税', '自贸', '示范', '科技', '旅游']):
            return city

    # 3. Autonomous region + 地区
    m = re.search(r'(?:自治区)([^省市县区旗]+?地区)', addr)
    if m:
        return m.group(1)

    # 4. Autonomous region + 自治州
    m = re.search(r'(?:自治区)([^省市县区旗]+?自治州)', addr)
    if m:
        return m.group(1)

    # 5. Inner Mongolia 盟
    m = re.search(r'(?:内蒙古)([^省市县区旗]+?盟)', addr)
    if m:
        return m.group(1)

    # 6. Fallback: last 市 before district/street
    # Find the last occurrence of "市" that's preceded by Chinese chars
    # and not part of a special zone name
    all_cities = re.findall(r'([^省市县区旗\s]{1,8}市)(?=[县区旗镇乡街路号楼])', addr)
    if all_cities:
        city = all_cities[-1]
        if not any(z in city for z in ['高新', '开发', '经济', '产业', '保税', '自贸', '示范', '科技', '旅游', '前海', '雄安']):
            return city

    # 7. County-level city (县级市) without preceding 省
    # e.g. "义乌市..." or "昆山市..." — but these usually have 省 prefix
    # Only match if it starts with the city
    m = re.match(r'^([^省市县区旗]+?市)', addr)
    if m:
        city = m.group(1)
        if len(city) <= 8 and '中国' not in city:
            return city

    # 8. Special: 海南省县级市 (no prefecture-level city)
    m = re.search(r'海南省([^省市县区旗]+?市)', addr)
    if m:
        return m.group(1)

    # 9. Special: 湖北省仙桃市/潜江市/天门市/神农架林区 (directly administered)
    m = re.search(r'(?:湖北|海南|新疆|西藏|内蒙古)([^省市县区旗]+?市)', addr)
    if m:
        city = m.group(1)
        if len(city) <= 8:
            return city

    return None


def main():
    from sqlalchemy import create_engine, text
    from app.config import settings

    engine = create_engine(settings.database_url)

    logger.info("Loading companies with registered_address but no city...")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, ticker, registered_address, province, city
            FROM companies
            WHERE is_active = true
              AND registered_address IS NOT NULL AND registered_address != ''
              AND (city IS NULL OR city = '')
        """)).fetchall()

    logger.info(f"Found {len(rows)} companies to process")

    updates = {}
    parsed = 0
    failed = 0
    failures = []

    for row in rows:
        city = parse_city(row.registered_address)
        if city:
            updates[row.id] = city
            parsed += 1
        else:
            failed += 1
            failures.append((row.ticker, row.province, row.registered_address[:50]))

    logger.info(f"Parsed city for {parsed}/{len(rows)} companies")
    logger.info(f"Failed: {failed}")

    if failures:
        logger.info("=== Sample failures (first 20) ===")
        for ticker, prov, addr in failures[:20]:
            logger.info(f"  {ticker} [{prov}] {addr}")

    if not updates:
        logger.info("No cities to update.")
        return

    logger.info(f"Updating {len(updates)} companies...")
    with engine.begin() as conn:
        for cid, city in updates.items():
            conn.execute(
                text("UPDATE companies SET city = :city WHERE id = :id"),
                {"id": cid, "city": city}
            )

    logger.info("Done.")

    # Summary
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true")).scalar()
        has_city = conn.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = true AND city IS NOT NULL")).scalar()

    logger.info("=" * 50)
    logger.info("CITY COVERAGE SUMMARY")
    logger.info(f"  Total active:  {total}")
    logger.info(f"  With city:     {has_city} ({has_city/total*100:.1f}%)")
    logger.info(f"  Missing:       {total - has_city}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
