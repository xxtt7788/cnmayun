from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, CompanyMetricDaily, Event, Person, RoleTenure, SourceDocument


def seed_demo_data(db: Session) -> None:
    if db.scalar(select(Company.id).limit(1)):
        return

    companies = [
        Company(
            exchange="SSE",
            ticker="600519",
            company_name="贵州茅台酒股份有限公司",
            short_name="贵州茅台",
            industry_l1="食品饮料",
            industry_l2="白酒",
            province="贵州",
            city="遵义",
            market_segment="Main Board",
            state_owned_flag=True,
        ),
        Company(
            exchange="SZSE",
            ticker="300750",
            company_name="宁德时代新能源科技股份有限公司",
            short_name="宁德时代",
            industry_l1="电力设备",
            industry_l2="锂电池",
            province="福建",
            city="宁德",
            market_segment="ChiNext",
            state_owned_flag=False,
        ),
        Company(
            exchange="SSE",
            ticker="688981",
            company_name="中芯国际集成电路制造有限公司",
            short_name="中芯国际",
            industry_l1="电子",
            industry_l2="半导体",
            province="上海",
            city="上海",
            market_segment="STAR",
            state_owned_flag=False,
        ),
    ]
    db.add_all(companies)
    db.flush()

    people = [
        Person(canonical_name="张远航", alias_names='["张远航"]', notes="示例董事长人物资料。"),
        Person(canonical_name="李思成", alias_names='["李思成"]', notes="示例总经理人物资料。"),
        Person(canonical_name="王谨", alias_names='["王谨"]', notes="示例财务负责人人物资料。"),
        Person(canonical_name="周岚", alias_names='["周岚"]', notes="示例独立董事人物资料。"),
        Person(canonical_name="陈嘉木", alias_names='["陈嘉木"]', notes="示例董事及跨公司重叠人物资料。"),
    ]
    db.add_all(people)
    db.flush()

    docs = [
        SourceDocument(
            company_id=companies[0].id,
            source_type="appointment_notice",
            source_platform="CNINFO",
            title="关于聘任财务负责人的公告",
            announcement_date=date(2026, 4, 12),
            publish_ts=datetime(2026, 4, 12, 9, 5),
            source_url="https://example.com/notices/600519-cfo",
            raw_text="董事会同意聘任王谨为公司财务负责人，自董事会审议通过之日起生效。",
        ),
        SourceDocument(
            company_id=companies[1].id,
            source_type="resignation_notice",
            source_platform="CNINFO",
            title="关于董事兼总经理辞职的公告",
            announcement_date=date(2026, 4, 15),
            publish_ts=datetime(2026, 4, 15, 19, 30),
            source_url="https://example.com/notices/300750-ceo",
            raw_text="李思成因个人原因申请辞去公司总经理职务，辞任后不再担任公司任何职务。",
        ),
        SourceDocument(
            company_id=companies[2].id,
            source_type="reelection_notice",
            source_platform="SSE",
            title="关于董事会换届选举的公告",
            announcement_date=date(2026, 4, 16),
            publish_ts=datetime(2026, 4, 16, 18, 0),
            source_url="https://example.com/notices/688981-board",
            raw_text="陈嘉木、周岚获提名并连任董事、独立董事，任期三年。",
        ),
    ]
    db.add_all(docs)
    db.flush()

    db.add_all(
        [
            Event(
                company_id=companies[0].id,
                person_id=people[2].id,
                source_document_id=docs[0].id,
                role_raw="财务负责人",
                role_canonical="cfo_equivalent",
                event_type="appointment",
                event_status="published",
                event_reason_raw="董事会聘任",
                announcement_date=date(2026, 4, 12),
                effective_date=date(2026, 4, 12),
                board_approval_date=date(2026, 4, 12),
                excerpt="董事会同意聘任王谨为公司财务负责人，自董事会审议通过之日起生效。",
                confidence=Decimal("0.9700"),
                published_at=datetime(2026, 4, 12, 9, 8),
            ),
            Event(
                company_id=companies[1].id,
                person_id=people[1].id,
                source_document_id=docs[1].id,
                role_raw="总经理",
                role_canonical="ceo_equivalent",
                event_type="resignation",
                event_status="published",
                event_reason_raw="个人原因辞任",
                announcement_date=date(2026, 4, 15),
                effective_date=date(2026, 4, 15),
                excerpt="李思成因个人原因申请辞去公司总经理职务，辞任后不再担任公司任何职务。",
                confidence=Decimal("0.9600"),
                published_at=datetime(2026, 4, 15, 19, 35),
            ),
            Event(
                company_id=companies[2].id,
                person_id=people[4].id,
                source_document_id=docs[2].id,
                role_raw="董事",
                role_canonical="director",
                event_type="reelection",
                event_status="published",
                event_reason_raw="董事会换届连任",
                announcement_date=date(2026, 4, 16),
                effective_date=date(2026, 4, 16),
                shareholder_approval_date=date(2026, 4, 16),
                excerpt="陈嘉木获提名并连任董事，任期三年。",
                confidence=Decimal("0.9400"),
                published_at=datetime(2026, 4, 16, 18, 5),
            ),
            Event(
                company_id=companies[2].id,
                person_id=people[3].id,
                source_document_id=docs[2].id,
                role_raw="独立董事",
                role_canonical="independent_director",
                event_type="reelection",
                event_status="published",
                event_reason_raw="董事会换届连任",
                announcement_date=date(2026, 4, 16),
                effective_date=date(2026, 4, 16),
                shareholder_approval_date=date(2026, 4, 16),
                excerpt="周岚获提名并连任独立董事，任期三年。",
                confidence=Decimal("0.9400"),
                published_at=datetime(2026, 4, 16, 18, 6),
            ),
        ]
    )

    db.add_all(
        [
            RoleTenure(company_id=companies[0].id, person_id=people[0].id, role_canonical="chairperson", role_raw_latest="董事长", start_date=date(2025, 4, 1), is_active=True),
            RoleTenure(company_id=companies[0].id, person_id=people[2].id, role_canonical="cfo_equivalent", role_raw_latest="财务负责人", start_date=date(2026, 4, 12), is_active=True),
            RoleTenure(company_id=companies[1].id, person_id=people[1].id, role_canonical="ceo_equivalent", role_raw_latest="总经理", start_date=date(2024, 10, 8), end_date=date(2026, 4, 15), is_active=False),
            RoleTenure(company_id=companies[2].id, person_id=people[4].id, role_canonical="director", role_raw_latest="董事", start_date=date(2023, 4, 16), is_active=True),
            RoleTenure(company_id=companies[2].id, person_id=people[3].id, role_canonical="independent_director", role_raw_latest="独立董事", start_date=date(2023, 4, 16), is_active=True),
        ]
    )

    db.add_all(
        [
            CompanyMetricDaily(company_id=companies[0].id, metric_date=date(2026, 4, 17), change_count_30d=1, change_count_90d=2, mom_change_rate=Decimal("0.1000"), yoy_change_rate=Decimal("0.2500"), stability_score=Decimal("86.2000"), abnormal_turnover_flag=False),
            CompanyMetricDaily(company_id=companies[1].id, metric_date=date(2026, 4, 17), change_count_30d=2, change_count_90d=3, mom_change_rate=Decimal("1.0000"), yoy_change_rate=Decimal("0.5000"), stability_score=Decimal("58.4000"), abnormal_turnover_flag=True),
            CompanyMetricDaily(company_id=companies[2].id, metric_date=date(2026, 4, 17), change_count_30d=2, change_count_90d=2, mom_change_rate=Decimal("0.4000"), yoy_change_rate=Decimal("0.1000"), stability_score=Decimal("79.5000"), abnormal_turnover_flag=False),
        ]
    )
