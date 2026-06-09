#!/usr/bin/env python3
"""
Batch enrich person_profiles from EastMoney API resume (jj) field.

For each active company, fetch management list and extract full resume.
Parse career history, shareholding, and current positions from jj field.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from urllib.request import Request, urlopen

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

from app.db import session_scope
from app.models import Company, Person, PersonProfile
from sqlalchemy import select, text

EASTMONEY_MGMT_API = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/CompanyManagementAjax"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

MAX_WORKERS = int(os.getenv("BACKFILL_WORKERS", "20"))


def build_em_code(ticker: str) -> str:
    ticker = str(ticker).strip()
    if ticker.startswith("6") or ticker.startswith("5"):
        return f"SH{ticker}"
    return f"SZ{ticker}"


def fetch_company_management(ticker: str) -> list[dict]:
    em_code = build_em_code(ticker)
    url = f"{EASTMONEY_MGMT_API}?code={em_code}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("RptManagerList") or []
    except Exception:
        return []


def parse_resume(jj: str | None) -> dict:
    """Parse EastMoney resume text into structured fields."""
    if not jj or len(jj.strip()) < 10:
        return {}

    result = {
        "resume_raw": jj.strip(),
        "career_history_raw": "",
        "current_positions_raw": "",
        "shareholding_raw": "",
        "nationality": "",
        "professional_title": "",
    }

    text = jj.strip()

    # Extract nationality
    nat_match = re.search(r"([\u4e00-\u9fa5]+)国籍", text)
    if nat_match:
        result["nationality"] = nat_match.group(1)

    # Extract professional title (职称)
    title_match = re.search(r"([^，。；\s]+?(?:经济师|工程师|会计师|研究员|教授|高级工程师|高级会计师|高级经济师|政工师|律师|博士|硕士|学士))", text)
    if title_match:
        result["professional_title"] = title_match.group(1)

    # Split career history: "曾任..." and "现任..."
    parts = re.split(r"(?:曾任|历任)", text, maxsplit=1)
    if len(parts) == 2:
        history_part = parts[1]
        # Split at "现任" if present
        current_match = re.search(r"现任(.+?)(?:。|$)", history_part)
        if current_match:
            result["current_positions_raw"] = "现任" + current_match.group(1)
            result["career_history_raw"] = "曾任" + history_part[:current_match.start()]
        else:
            result["career_history_raw"] = "曾任" + history_part

    return result


def main():
    with session_scope() as db:
        disabled_ids = {row[0] for row in db.execute(text("SELECT id FROM companies WHERE executive_sync_disabled = TRUE")).fetchall()}
        companies = db.scalars(select(Company).where(Company.is_active.is_(True))).all()
        companies = [c for c in companies if c.id not in disabled_ids]

        # Load all persons into memory for matching
        persons = db.scalars(select(Person)).all()
        person_by_name = {p.canonical_name: p for p in persons if p.canonical_name}

    print(f"Companies to process: {len(companies)}")
    print(f"Workers: {MAX_WORKERS}")
    print("=" * 60)

    # Fetch all management lists
    results: dict[int, list[dict]] = {}
    processed = 0
    failed_tickers = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(fetch_company_management, c.ticker): c
            for c in companies
        }
        for future in as_completed(future_map):
            company = future_map[future]
            processed += 1
            try:
                managers = future.result()
                if managers:
                    results[company.id] = managers
            except Exception as e:
                failed_tickers.append(company.ticker)
                print(f"  ERROR {company.ticker}: {e}")

            if processed % 200 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Fetch progress: {processed}/{len(companies)} | success={len(results)} | {rate:.1f}/sec")

    fetch_elapsed = time.time() - start_time
    print(f"\nFetch complete: {len(results)} companies, {len(failed_tickers)} failed, {fetch_elapsed:.1f}s")

    # Build profile upserts
    profile_upserts: dict[int, dict] = {}  # person_id -> profile_data
    matched = 0
    unmatched = 0

    for cid, managers in results.items():
        for m in managers:
            name = m.get("xm", "").strip()
            jj = m.get("jj", "")
            if not name or not jj:
                continue

            person = person_by_name.get(name)
            if not person:
                unmatched += 1
                continue

            matched += 1
            parsed = parse_resume(jj)
            if not parsed:
                continue

            # Merge if we already have data for this person
            if person.id in profile_upserts:
                existing = profile_upserts[person.id]
                # Append career history if different
                if parsed.get("career_history_raw") and parsed["career_history_raw"] not in existing.get("career_history_raw", ""):
                    existing["career_history_raw"] += "\n" + parsed["career_history_raw"]
                # Update current positions if more recent
                if parsed.get("current_positions_raw"):
                    existing["current_positions_raw"] = parsed["current_positions_raw"]
                # Keep longest resume
                if len(parsed.get("resume_raw", "")) > len(existing.get("resume_raw", "")):
                    existing["resume_raw"] = parsed["resume_raw"]
            else:
                profile_upserts[person.id] = parsed

    print(f"Matched persons: {matched}")
    print(f"Unmatched names: {unmatched}")
    print(f"Unique profiles to upsert: {len(profile_upserts)}")

    # Apply to database
    BATCH_SIZE = 500
    inserted = 0
    updated = 0

    with session_scope() as db:
        person_ids = list(profile_upserts.keys())
        for i in range(0, len(person_ids), BATCH_SIZE):
            batch_ids = person_ids[i:i+BATCH_SIZE]
            existing_profiles = {
                p.person_id: p for p in db.scalars(
                    select(PersonProfile).where(PersonProfile.person_id.in_(batch_ids))
                ).all()
            }

            for pid in batch_ids:
                data = profile_upserts[pid]
                profile = existing_profiles.get(pid)
                if profile:
                    # Update existing
                    if data.get("resume_raw"):
                        profile.resume_raw = data["resume_raw"]
                    if data.get("career_history_raw"):
                        profile.career_history_raw = data["career_history_raw"]
                    if data.get("current_positions_raw"):
                        profile.current_positions_raw = data["current_positions_raw"]
                    if data.get("nationality"):
                        profile.nationality = data["nationality"]
                    if data.get("professional_title"):
                        profile.professional_title = data["professional_title"]
                    updated += 1
                else:
                    # Insert new
                    profile = PersonProfile(
                        person_id=pid,
                        identity_key=f"em_{pid}",
                        profile_name="EastMoney Profile",
                        resume_raw=data.get("resume_raw", ""),
                        career_history_raw=data.get("career_history_raw", ""),
                        current_positions_raw=data.get("current_positions_raw", ""),
                        nationality=data.get("nationality", ""),
                        professional_title=data.get("professional_title", ""),
                        source_url=EASTMONEY_MGMT_API,
                        confidence=0.85,
                    )
                    db.add(profile)
                    inserted += 1

        db.commit()

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("PERSON PROFILE ENRICHMENT COMPLETE")
    print(f"  Inserted: {inserted}")
    print(f"  Updated: {updated}")
    print(f"  Total profiles: {inserted + updated}")
    print(f"  Fetch time: {fetch_elapsed:.1f}s")
    print(f"  Total time: {total_elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
