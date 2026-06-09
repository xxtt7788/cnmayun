#!/usr/bin/env python3
"""
Database readiness evaluation for production launch.

Author: Kimi Code CLI Agent
Date: 2026-04-27
"""
import os
import sys
from datetime import date

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

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ["DATABASE_URL"])
Session = sessionmaker(bind=engine)


def evaluate():
    db = Session()
    print("=" * 60)
    print("DATABASE READINESS EVALUATION")
    print(f"Date: {date.today()}")
    print("=" * 60)

    # 1. Company coverage
    total_companies = db.execute(text("SELECT COUNT(*) FROM companies")).scalar()
    active_companies = db.execute(text("SELECT COUNT(*) FROM companies WHERE is_active = TRUE")).scalar()
    disabled_companies = db.execute(text("SELECT COUNT(*) FROM companies WHERE executive_sync_disabled = TRUE")).scalar()
    print(f"\n[1] COMPANY COVERAGE")
    print(f"  Total companies: {total_companies}")
    print(f"  Active companies: {active_companies}")
    print(f"  Disabled (no data source): {disabled_companies}")
    print(f"  Active coverage: {active_companies / (active_companies + disabled_companies) * 100:.1f}%")

    # 2. Person completeness
    total_persons = db.execute(text("SELECT COUNT(*) FROM persons")).scalar()
    gender_filled = db.execute(text("SELECT COUNT(*) FROM persons WHERE gender IS NOT NULL")).scalar()
    birth_year_filled = db.execute(text("SELECT COUNT(*) FROM persons WHERE birth_year IS NOT NULL")).scalar()
    education_filled = db.execute(text("SELECT COUNT(*) FROM persons WHERE education IS NOT NULL")).scalar()
    print(f"\n[2] PERSON COMPLETENESS (total={total_persons})")
    print(f"  Gender: {gender_filled} ({gender_filled/total_persons*100:.1f}%)")
    print(f"  Birth year: {birth_year_filled} ({birth_year_filled/total_persons*100:.1f}%)")
    print(f"  Education: {education_filled} ({education_filled/total_persons*100:.1f}%)")

    # 3. Snapshots
    total_snapshots = db.execute(text("SELECT COUNT(*) FROM executive_snapshots")).scalar()
    orphan_snapshots = db.execute(text("""
        SELECT COUNT(*) FROM executive_snapshots 
        WHERE company_id NOT IN (SELECT id FROM companies)
    """)).scalar()
    print(f"\n[3] SNAPSHOTS")
    print(f"  Total snapshots: {total_snapshots}")
    print(f"  Orphan snapshots: {orphan_snapshots}")

    # 4. RoleTenures
    total_tenures = db.execute(text("SELECT COUNT(*) FROM role_tenures")).scalar()
    start_filled = db.execute(text("SELECT COUNT(*) FROM role_tenures WHERE start_date IS NOT NULL")).scalar()
    end_filled = db.execute(text("SELECT COUNT(*) FROM role_tenures WHERE end_date IS NOT NULL")).scalar()
    active_tenures = db.execute(text("SELECT COUNT(*) FROM role_tenures WHERE is_active = TRUE")).scalar()
    inactive_tenures = db.execute(text("SELECT COUNT(*) FROM role_tenures WHERE is_active = FALSE")).scalar()
    null_person = db.execute(text("SELECT COUNT(*) FROM role_tenures WHERE person_id IS NULL")).scalar()
    print(f"\n[4] ROLE TENURES (total={total_tenures})")
    print(f"  Start date filled: {start_filled} ({start_filled/total_tenures*100:.1f}%)")
    print(f"  End date filled: {end_filled} ({end_filled/total_tenures*100:.1f}%)")
    print(f"  Active: {active_tenures}")
    print(f"  Inactive: {inactive_tenures}")
    print(f"  Null person_id: {null_person}")

    # 5. Events
    total_events = db.execute(text("SELECT COUNT(*) FROM events")).scalar()
    published = db.execute(text("SELECT COUNT(*) FROM events WHERE event_status='published'")).scalar()
    review_req = db.execute(text("SELECT COUNT(*) FROM events WHERE event_status='review_required'")).scalar()
    print(f"\n[5] EVENTS (total={total_events})")
    print(f"  Published: {published}")
    print(f"  Review required: {review_req}")

    # 6. Source docs
    total_docs = db.execute(text("SELECT COUNT(*) FROM source_documents")).scalar()
    print(f"\n[6] SOURCE DOCUMENTS")
    print(f"  Total: {total_docs}")

    # 7. Review queue
    total_reviews = db.execute(text("SELECT COUNT(*) FROM review_queue")).scalar()
    pending = db.execute(text("SELECT COUNT(*) FROM review_queue WHERE status='pending'")).scalar()
    approved = db.execute(text("SELECT COUNT(*) FROM review_queue WHERE status='approved'")).scalar()
    print(f"\n[7] REVIEW QUEUE (total={total_reviews})")
    print(f"  Pending: {pending}")
    print(f"  Approved: {approved}")

    # 8. Data quality checks
    print(f"\n[8] DATA QUALITY CHECKS")
    dup_names = db.execute(text("""
        SELECT canonical_name, COUNT(*) FROM persons 
        WHERE canonical_name IS NOT NULL 
        GROUP BY canonical_name HAVING COUNT(*) > 1 
        LIMIT 5
    """)).fetchall()
    print(f"  Duplicate person names (top 5): {len(dup_names)}")
    for name, cnt in dup_names:
        print(f"    {name}: {cnt}")

    # Companies with zero snapshots
    zero_snap = db.execute(text("""
        SELECT COUNT(*) FROM companies c
        WHERE is_active = TRUE 
        AND NOT EXISTS (SELECT 1 FROM executive_snapshots s WHERE s.company_id = c.id)
    """)).scalar()
    print(f"  Active companies with zero snapshots: {zero_snap}")

    # Missing start_date by exchange
    bse_missing = db.execute(text("""
        SELECT COUNT(*) FROM role_tenures rt
        JOIN companies c ON rt.company_id = c.id
        WHERE rt.start_date IS NULL AND c.exchange = 'BSE'
    """)).scalar()
    sse_missing = db.execute(text("""
        SELECT COUNT(*) FROM role_tenures rt
        JOIN companies c ON rt.company_id = c.id
        WHERE rt.start_date IS NULL AND c.exchange = 'SSE'
    """)).scalar()
    szse_missing = db.execute(text("""
        SELECT COUNT(*) FROM role_tenures rt
        JOIN companies c ON rt.company_id = c.id
        WHERE rt.start_date IS NULL AND c.exchange = 'SZSE'
    """)).scalar()
    print(f"  Missing start_date by exchange: BSE={bse_missing}, SSE={sse_missing}, SZSE={szse_missing}")

    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    evaluate()
