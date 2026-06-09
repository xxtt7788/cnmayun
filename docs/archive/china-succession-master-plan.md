# China Succession Master Plan

## 1. Project Definition

### 1.1 Working Name
ChinaSuccession

### 1.2 One-Sentence Definition
ChinaSuccession is a structured intelligence system for China-listed companies that detects, normalizes, and tracks leadership and board changes from official disclosures, then turns them into searchable events, timelines, alerts, and relationship graphs.

### 1.3 Why This Product Exists
China does not have a single disclosure stream equivalent to the SEC's 8-K Item 5.02. Leadership changes are scattered across appointment notices, board resolutions, shareholder meeting resolutions, reelection notices, annual reports, and governance disclosures. The market does not need another notice portal. It needs a reliable event layer.

### 1.4 Product Thesis
The durable advantage is not scraping. The durable advantage is:

1. Detecting relevant governance notices in near real time.
2. Converting messy disclosure text into canonical management-change events.
3. Reconstructing tenure history across companies and time.
4. Exposing comparative metrics and graph relationships that are hard to derive from raw notices.

## 2. Product Goals

### 2.1 Primary Goal
Build the most reliable structured event database for leadership and board changes across A-share listed companies.

### 2.2 Secondary Goals

1. Give researchers a company-level timeline of management changes.
2. Give users a person-level history of listed-company roles.
3. Quantify leadership stability and abnormal turnover.
4. Surface board overlap and cross-company movement patterns.

### 2.3 Non-Goals for V1

1. Full China capital markets coverage across A-shares, Hong Kong, and US-listed ADRs.
2. Compensation analytics.
3. Sentiment and opinion mining.
4. Full executive search workflow software.
5. Automated investment reports.

## 3. Scope Freeze

### 3.1 Market Scope
V1 covers only A-share listed companies, including:

1. Shanghai Main Board
2. Shenzhen Main Board
3. ChiNext
4. STAR Market
5. Beijing Stock Exchange

### 3.2 Role Scope
V1 tracks only these canonical roles:

1. `chairperson`
2. `ceo_equivalent`
3. `cfo_equivalent`
4. `director`
5. `independent_director`

### 3.3 Event Scope
V1 tracks only these canonical event types:

1. `appointment`
2. `resignation`
3. `removal`
4. `reelection`
5. `interim_assignment`
6. `title_change`
7. `nomination`
8. `non_renewal`
9. `retirement`

### 3.4 Data Source Scope
V1 uses:

1. Official disclosure platforms as primary sources.
2. Annual reports for roster reconciliation.
3. Company IR pages only as low-confidence supplemental sources.

### 3.5 Explicit Exclusions
V1 excludes:

1. Supervisors.
2. Board secretary unless later promoted into core scope.
3. Core technical personnel.
4. Offshore listings.
5. Compensation tables.
6. Insider trading linkage.

## 4. Users and Core Jobs

### 4.1 Priority Users

1. Buy-side and sell-side researchers.
2. Financial media and data journalists.
3. Executive search firms.
4. Investor relations and strategy teams.
5. Governance researchers.

### 4.2 Core Jobs To Be Done

1. Tell me which listed companies changed chairperson, CEO-equivalent, CFO-equivalent, or board members today.
2. Tell me whether a change was a normal cycle, a resignation, or an abnormal turnover signal.
3. Tell me where this person served before.
4. Tell me which companies share directors or independent directors.
5. Tell me which companies have unstable leadership this quarter compared with prior periods.

## 5. Product Requirements

### 5.1 V1 Core Features

1. Continuous ingestion of official notices.
2. Notice classification into management-change relevance.
3. Structured extraction of people, roles, event types, dates, and supporting excerpts.
4. Canonical event storage with confidence scoring.
5. Company page with event timeline and current leadership snapshot.
6. Person page with role history and movement timeline.
7. Global search across company, ticker, person, role, and event.
8. Recent changes feed.
9. CSV export for search and timeline results.

### 5.2 V1.5 Differentiation Features

1. Month-over-month and year-over-year change metrics.
2. Leadership stability score.
3. Board overlap graph.
4. Personnel flow graph.
5. Company and person alerts.

### 5.3 Internal Ops Features

1. Review queue for low-confidence extraction.
2. Duplicate resolution workflow.
3. Role mapping editor.
4. Audit log for every event change.

## 6. Information Architecture

### 6.1 Public Product Surface

1. Home
2. Explore feed
3. Companies
4. People
5. Rankings
6. Graph
7. Alerts
8. Admin review

### 6.2 Key Entity Pages

#### Company page

1. Current leadership snapshot.
2. Historical event timeline.
3. Stability metrics.
4. Shared board links.
5. Source documents.

#### Person page

1. Canonical name and aliases.
2. Current active roles.
3. Historical tenures.
4. Movement path across companies.
5. Source evidence.

## 7. Source Strategy

### 7.1 Source Priority

1. CNINFO and official exchange disclosures as primary truth.
2. Annual reports as historical roster truth.
3. Company IR pages as weak supplemental signals.

### 7.2 Why Source Strategy Matters
The system must distinguish between:

1. announcement date
2. board approval date
3. shareholder approval date
4. effective date

These are not interchangeable. The system stores all available dates and promotes one `effective_date` only when supported by evidence.

## 8. Data and Event Model

### 8.1 Core Entities

1. Company
2. Person
3. Source document
4. Extracted event
5. Canonical event
6. Role tenure
7. Board overlap edge
8. User alert

### 8.2 Canonical Role Mapping

| Raw title examples | Canonical role |
| --- | --- |
| Chairman, Board Chair, Chairperson | `chairperson` |
| President, General Manager, Chief Executive Officer | `ceo_equivalent` |
| CFO, Finance Director, Financial Controller, Finance Head | `cfo_equivalent` |
| Director | `director` |
| Independent Director | `independent_director` |

### 8.3 Core Event Rules

1. One notice can create multiple events.
2. "Resigned as general manager but remains chairperson" becomes two role-specific facts, not one vague event.
3. "Nominated" is not the same as "appointed".
4. "Term expired and reelected" must be represented differently from "resigned".
5. The system must retain raw role text and canonical role mapping together.

## 9. System Architecture

### 9.1 Ingestion Pipeline

1. Poll official disclosure feeds.
2. Store raw metadata and documents.
3. Convert PDF or HTML to normalized text.
4. Run rule-based classification for management relevance.
5. Run structured extraction on candidates.
6. Normalize people, roles, and dates.
7. Deduplicate events.
8. Rebuild company and person projections.
9. Update metrics and graph edges.

### 9.2 Services

1. `collector-service`
2. `document-parser-service`
3. `notice-classifier-service`
4. `event-extractor-service`
5. `normalization-service`
6. `dedupe-service`
7. `projection-service`
8. `alert-service`
9. `review-console`

### 9.3 Storage

1. PostgreSQL for transactional and structured entities.
2. OpenSearch for search.
3. Object storage for raw files.
4. Redis for queues and caching.

Neo4j is optional. V1 can compute board overlap from relational tables.

## 10. Extraction Strategy

### 10.1 Detection Layers

1. Title-based keyword rules for fast recall.
2. Body-section rules for extraction focus.
3. LLM or IE model for structured parsing.
4. Rules for normalization and validation.

### 10.2 Why Not Pure LLM
Pure LLM extraction will drift, over-merge, hallucinate dates, and collapse subtle distinctions like nomination versus appointment. It is acceptable as one layer, not as the sole source of truth.

### 10.3 Confidence Policy

1. High confidence events are auto-published.
2. Medium confidence events are published with internal review sampling.
3. Low confidence events enter manual review.

## 11. Deduplication and Identity Resolution

### 11.1 Document Deduplication

1. Hash-based duplicate detection.
2. Similar-title clustering.
3. Same company plus same day plus high-overlap text collapsing.

### 11.2 Event Deduplication

Candidate duplicate keys:

1. company
2. person raw name
3. canonical role
4. event type
5. effective date or announcement date window

### 11.3 Person Resolution
V1 uses conservative identity resolution:

1. Strong same-company continuity merges first.
2. Cross-company same-name merges require corroboration from resume text, age, or explicit prior service mentions.
3. When uncertain, keep separate person records.

This reduces catastrophic false merges.

## 12. Metrics

### 12.1 Must-Have Metrics

1. 30-day change count.
2. 90-day change count.
3. month-over-month change rate.
4. year-over-year change rate.
5. leadership stability score.
6. board overlap count.
7. abnormal turnover marker.

### 12.2 Stability Score Framework

Suggested weights:

1. chairperson event = 1.0
2. ceo_equivalent event = 0.9
3. cfo_equivalent event = 0.8
4. director event = 0.5
5. independent_director event = 0.4

Modifiers:

1. normal reelection = lower impact
2. mid-term resignation = higher impact
3. acting assignment = elevated risk

## 13. UI Plan

### 13.1 UX Principles

1. Evidence first.
2. Search first.
3. Timeline as default mental model.
4. One screen should answer what changed, when, who, and why.
5. Graphs are supporting tools, not the primary navigation model.

### 13.2 Core Screens

1. Explore feed.
2. Company detail.
3. Person detail.
4. Ranking and comparison.
5. Graph explorer.
6. Alert builder.
7. Admin review queue.

### 13.3 UI Readiness Status
We have enough information architecture to design V1 screens, but not enough detail to claim UI is fully designed until each screen has:

1. exact layout
2. filter model
3. table columns
4. state handling
5. mobile behavior

This master plan defines all of those targets. The dedicated UI plan file freezes them.

## 14. Delivery Plan

### 14.1 Phase 0: Foundation
Duration: 2 weeks

Deliverables:

1. frozen scope
2. source inventory
3. schema draft
4. sample corpus
5. title taxonomy

Exit criteria:

1. at least 500 labeled notices
2. role mapping dictionary v1
3. extraction contract v1

### 14.2 Phase 1: Core Data Engine
Duration: 4 weeks

Deliverables:

1. collection pipeline
2. parser pipeline
3. classifier v1
4. extraction v1
5. canonical event storage
6. company page API

Exit criteria:

1. notice ingestion is stable
2. event extraction works on core roles
3. company timeline is queryable

### 14.3 Phase 2: Product V1
Duration: 4 weeks

Deliverables:

1. public explore feed
2. company page
3. person page
4. search
5. export
6. review console

Exit criteria:

1. users can monitor events end to end
2. low-confidence cases are reviewable
3. internal QA metrics are visible

### 14.4 Phase 3: Product V1.5
Duration: 4 weeks

Deliverables:

1. metrics
2. alerts
3. graph pages
4. comparison pages
5. API beta

Exit criteria:

1. differential analytics are working
2. graph relationships are understandable and explainable
3. alert latency is acceptable

## 15. Acceptance Criteria

### 15.1 Data Quality

1. management-related notice recall >= 95%
2. classification precision >= 90%
3. person extraction accuracy >= 97%
4. canonical role accuracy >= 95%
5. event-type accuracy >= 93%
6. effective-date accuracy >= 90%

### 15.2 Product Performance

1. new event latency under 15 minutes from source availability
2. search response under 500 ms for common queries
3. company page under 1.5 s

### 15.3 Operational Quality

1. every canonical event retains source link and excerpt
2. every manual override is auditable
3. no irreversible merges without audit trail

## 16. Risks and Controls

### 16.1 High Risks

1. over-broad scope
2. noisy extraction
3. aggressive person merges
4. normal reelection misclassified as instability
5. UI over-indexing on graph novelty rather than evidence

### 16.2 Controls

1. hard scope freeze
2. conservative identity policy
3. evidence retention for every event
4. review queue for low-confidence items
5. metrics validated only after canonical event confidence clears threshold

## 17. Final Build Order

If only one build order is allowed, use this:

1. freeze schema and extraction contract
2. build ingestion
3. build classification
4. build extraction
5. build normalization and dedupe
6. build company timeline
7. build person timeline
8. build search
9. build admin review
10. build metrics
11. build graphs
12. build alerts

## 18. Final Decision

The project is conceptually ready, but it was not previously execution-ready. This plan, together with the schema, extraction contract, and UI plan files, is the minimum package required to start implementation without drifting into fragmented decision-making.
