CREATE TABLE companies (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(16) NOT NULL,
    ticker VARCHAR(32) NOT NULL,
    company_name TEXT NOT NULL,
    short_name TEXT,
    industry_l1 TEXT,
    industry_l2 TEXT,
    province TEXT,
    city TEXT,
    market_segment VARCHAR(32),
    state_owned_flag BOOLEAN,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (exchange, ticker)
);

CREATE TABLE persons (
    id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    alias_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    gender VARCHAR(16),
    birth_year INTEGER,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE source_documents (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    source_type VARCHAR(32) NOT NULL,
    source_platform VARCHAR(64) NOT NULL,
    external_doc_id TEXT,
    title TEXT NOT NULL,
    title_hash VARCHAR(128),
    announcement_date DATE,
    publish_ts TIMESTAMPTZ,
    meeting_date DATE,
    effective_date_hint DATE,
    source_url TEXT NOT NULL,
    raw_pdf_url TEXT,
    raw_html_url TEXT,
    raw_text TEXT,
    raw_text_hash VARCHAR(128),
    language VARCHAR(8) NOT NULL DEFAULT 'zh',
    parse_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_source_documents_company_date
    ON source_documents(company_id, announcement_date DESC);

CREATE INDEX idx_source_documents_title_hash
    ON source_documents(title_hash);

CREATE TABLE document_classifications (
    id BIGSERIAL PRIMARY KEY,
    source_document_id BIGINT NOT NULL UNIQUE REFERENCES source_documents(id) ON DELETE CASCADE,
    is_management_relevant BOOLEAN NOT NULL,
    notice_type_raw TEXT,
    notice_type_canonical VARCHAR(64),
    classifier_version VARCHAR(64) NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE document_extractions (
    id BIGSERIAL PRIMARY KEY,
    source_document_id BIGINT NOT NULL UNIQUE REFERENCES source_documents(id) ON DELETE CASCADE,
    extractor_version VARCHAR(64) NOT NULL,
    extraction_json JSONB NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    person_id BIGINT REFERENCES persons(id),
    source_document_id BIGINT NOT NULL REFERENCES source_documents(id),
    duplicate_group_id BIGINT,
    role_raw TEXT NOT NULL,
    role_canonical VARCHAR(64) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    event_status VARCHAR(32) NOT NULL DEFAULT 'published',
    predecessor_role_raw TEXT,
    predecessor_role_canonical VARCHAR(64),
    event_reason_raw TEXT,
    announcement_date DATE,
    effective_date DATE,
    board_approval_date DATE,
    shareholder_approval_date DATE,
    excerpt TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    is_inferred BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_company_effective
    ON events(company_id, effective_date DESC, announcement_date DESC);

CREATE INDEX idx_events_person_effective
    ON events(person_id, effective_date DESC, announcement_date DESC);

CREATE INDEX idx_events_role_type
    ON events(role_canonical, event_type);

CREATE TABLE role_tenures (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    person_id BIGINT NOT NULL REFERENCES persons(id),
    role_canonical VARCHAR(64) NOT NULL,
    role_raw_latest TEXT,
    start_date DATE,
    end_date DATE,
    start_event_id BIGINT REFERENCES events(id),
    end_event_id BIGINT REFERENCES events(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    inferred_flag BOOLEAN NOT NULL DEFAULT FALSE,
    confidence NUMERIC(5,4) NOT NULL DEFAULT 1.0000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_role_tenures_company_role_active
    ON role_tenures(company_id, role_canonical, is_active);

CREATE INDEX idx_role_tenures_person
    ON role_tenures(person_id, start_date DESC);

CREATE TABLE person_company_edges (
    id BIGSERIAL PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES persons(id),
    company_id BIGINT NOT NULL REFERENCES companies(id),
    first_seen_date DATE,
    last_seen_date DATE,
    active_role_count INTEGER NOT NULL DEFAULT 0,
    total_event_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (person_id, company_id)
);

CREATE TABLE board_overlap_edges (
    id BIGSERIAL PRIMARY KEY,
    company_id_a BIGINT NOT NULL REFERENCES companies(id),
    company_id_b BIGINT NOT NULL REFERENCES companies(id),
    shared_person_count INTEGER NOT NULL DEFAULT 0,
    shared_director_count INTEGER NOT NULL DEFAULT 0,
    shared_independent_director_count INTEGER NOT NULL DEFAULT 0,
    last_calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (company_id_a, company_id_b)
);

CREATE TABLE company_metrics_daily (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id),
    metric_date DATE NOT NULL,
    change_count_30d INTEGER NOT NULL DEFAULT 0,
    change_count_90d INTEGER NOT NULL DEFAULT 0,
    mom_change_rate NUMERIC(12,4),
    yoy_change_rate NUMERIC(12,4),
    stability_score NUMERIC(12,4),
    abnormal_turnover_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (company_id, metric_date)
);

CREATE TABLE alerts (
    id BIGSERIAL PRIMARY KEY,
    user_key TEXT NOT NULL,
    alert_name TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    criteria_json JSONB NOT NULL,
    last_triggered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE alert_deliveries (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    event_id BIGINT REFERENCES events(id),
    delivery_channel VARCHAR(32) NOT NULL,
    delivery_status VARCHAR(32) NOT NULL DEFAULT 'queued',
    delivered_at TIMESTAMPTZ,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE review_queue (
    id BIGSERIAL PRIMARY KEY,
    source_document_id BIGINT REFERENCES source_documents(id) ON DELETE CASCADE,
    event_id BIGINT REFERENCES events(id) ON DELETE CASCADE,
    queue_reason VARCHAR(64) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 50,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    assigned_to TEXT,
    review_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(64) NOT NULL,
    entity_id BIGINT NOT NULL,
    action VARCHAR(64) NOT NULL,
    actor TEXT NOT NULL,
    before_json JSONB,
    after_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
