# China Succession UI Plan

## 1. UI Objective

The UI should answer four questions as fast as possible:

1. What changed
2. Who changed
3. When it changed
4. Why the user should care

Evidence beats decoration. The interface should feel like a data terminal with product polish, not a generic dashboard toy.

## 2. Design Principles

1. Search-first navigation
2. Timeline-first comprehension
3. Source evidence always one click away
4. Dense by default, readable under load
5. Graphs only after list and timeline clarity
6. Mobile is supported, desktop is the primary power-user surface

## 3. Design System Direction

### 3.1 Visual Tone
Calm, financial, precise, and evidence-heavy.

### 3.2 Color System

1. Background: warm light gray or off-white
2. Primary text: near-black
3. Positive event accents: muted deep green
4. Risk event accents: brick red
5. Neutral board-cycle events: slate blue
6. Highlight color for links and selected filters: deep cobalt

### 3.3 Typography

1. Headings: serif or semi-serif with financial-report character
2. Body: readable sans-serif
3. Tables: tabular numerals enabled

### 3.4 Core Components

1. universal search bar
2. filter chips
3. event cards
4. dense tables
5. evidence drawer
6. metric panels
7. graph canvas
8. alert rule builder

## 4. Global Navigation

Top navigation:

1. Explore
2. Companies
3. People
4. Rankings
5. Graph
6. Alerts
7. Admin

Persistent utility actions:

1. search
2. saved filters
3. export
4. alert on current view

## 5. Page Inventory

## 5.1 Explore Page

Purpose:
Show the latest canonical management and board changes across the market.

Layout:

1. top filter ribbon
2. left saved filter rail on desktop
3. center event stream
4. right quick metrics rail

Core filters:

1. market
2. event date
3. announcement date
4. role
5. event type
6. industry
7. state-owned flag
8. confidence threshold

Event card fields:

1. company short name and ticker
2. person name
3. canonical role
4. event type
5. effective date
6. announcement date
7. one-line reason
8. evidence excerpt
9. source link

Desktop wireframe:

```text
+----------------------------------------------------------------------------------+
| Search | Saved Views | Export | Create Alert                                     |
+----------------------------------------------------------------------------------+
| Filters: Role | Event | Market | Industry | Date | Confidence                  |
+--------------------+-------------------------------------------------------------+
| Saved Views        | Recent Changes                                              |
| - CEO changes      | ----------------------------------------------------------- |
| - CFO changes      | [Event card] Company / Person / Role / Type / Dates       |
| - Chair changes    | [Event card] Evidence excerpt                              |
| - Board churn      | ----------------------------------------------------------- |
|                    | [Event card] ...                                            |
+--------------------+--------------------------------------------+----------------+
| Quick counts                                                 | Risk signals     |
| Today: 14  7d: 83  30d: 276                                  | churn heat map   |
+--------------------------------------------------------------+------------------+
```

## 5.2 Company Page

Purpose:
Explain a company's current leadership state and full change history.

Sections:

1. company header
2. current leadership snapshot
3. stability metrics
4. historical timeline
5. source documents
6. shared board relationships

Key table columns:

1. person
2. role
3. current status
4. start date
5. end date
6. source count

Desktop wireframe:

```text
+----------------------------------------------------------------------------------+
| Company Name (Ticker) | Market | Industry | SOE badge | Create Alert            |
+----------------------------------------------------------------------------------+
| Stability Score | 30d Changes | 90d Changes | MoM | YoY | Shared Board Count     |
+----------------------------------------------------------------------------------+
| Current Leadership Snapshot                                                     |
| Person                Role                   Since         Status                |
| --------------------  --------------------   -----------   --------------------  |
| Zhang San             Chairperson            2025-04-01    Active                |
| Li Si                 CEO-equivalent         2024-10-08    Active                |
+----------------------------------------------------------------------------------+
| Historical Change Timeline                                                      |
| [date] [event] [person] [excerpt] [source]                                      |
+----------------------------------------------------------------------------------+
| Shared Board Relationships                                                      |
| Company B | Shared People | Shared Independent Directors | Open Graph           |
+----------------------------------------------------------------------------------+
```

## 5.3 Person Page

Purpose:
Show the person's listed-company leadership history.

Sections:

1. identity summary
2. current active roles
3. historical tenures
4. movement timeline
5. source evidence

Key UX rule:
When identity confidence is low, show a visible warning instead of pretending certainty.

## 5.4 Rankings Page

Purpose:
Convert raw events into comparative insight.

Default tabs:

1. highest 30-day churn
2. CFO turnover
3. chairperson changes
4. independent director exits
5. abnormal turnover score

## 5.5 Graph Page

Purpose:
Support exploratory analysis after the user already understands a company or person.

Modes:

1. company-to-company board overlap
2. person movement path

Graph UX rules:

1. graph must always be paired with a detail side panel
2. every edge must expose the evidence behind it
3. do not start users on an empty canvas

## 5.6 Alerts Page

Purpose:
Let users subscribe to event streams.

Alert dimensions:

1. company
2. person
3. role
4. event type
5. industry
6. stability threshold

## 5.7 Admin Review Page

Purpose:
Resolve low-confidence or duplicate items without breaking auditability.

Views:

1. low-confidence extraction queue
2. duplicate candidates
3. role mapping mismatches
4. person merge candidates

## 6. State and Empty Cases

For every page define:

1. loading state
2. zero-result state
3. low-confidence warning state
4. source unavailable state
5. mobile compact state

Example empty state for Explore:
"No management-change events match this filter. Try widening date range or removing role filters."

## 7. Mobile Behavior

Mobile goals:

1. quick scan of recent changes
2. company lookup
3. person lookup
4. alert management

Mobile compromises:

1. graph page becomes summary plus drill-in list
2. dense comparison tables collapse into cards
3. evidence drawer becomes bottom sheet

## 8. UI Build Order

Build screens in this order:

1. Explore
2. Company page
3. Person page
4. Search results
5. Rankings
6. Admin review
7. Alerts
8. Graph

## 9. UI Acceptance Criteria

1. A user can understand a single event in under 5 seconds.
2. A user can explain why an event exists from source evidence in under 2 clicks.
3. A user can inspect a company's last 12 months of changes without leaving the company page.
4. A user can find a person's listed-company history from global search in under 10 seconds.
5. Graph views never hide the underlying evidence.
