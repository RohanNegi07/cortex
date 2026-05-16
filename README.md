# CORTEX

**Client Oversight & Relationship Trajectory Executive**

Agent 3 in the `IRIS → CELL → CORTEX` pipeline. CORTEX is the project intelligence and PM command layer for the consultancy. It receives every meeting extraction that IRIS produces, stitches them into a living memory of each client engagement, tracks health and sentiment over time, manages the document lifecycle, and answers any stakeholder question about any project — shaped for their role.

> *IRIS perceives. CELL executes. CORTEX thinks.*

---

## What CORTEX Does

When IRIS finishes processing a meeting transcript, it fires a NERVE event to CORTEX. CORTEX then runs a deterministic 7-step pipeline automatically:

1. **Ingest** — downloads `insights.yaml` from R2, validates schema, embeds summary via OpenAI `text-embedding-3-small` into pgvector
2. **Memory Stitch** — fills `previous_meeting_ref`, updates sentiment history, merges risks, ages blockers, tracks milestone status
3. **Narrative Update** — LLM call (Claude) to update `relationship_trajectory` (trend + narrative prose)
4. **Health Score** — deterministic 0–100 score across 6 dimensions: sentiment, open risks, blockers, milestones, trajectory, velocity
5. **Milestone Drift** — compares current velocity against original SOW dates, flags at-risk milestones
6. **Enrich YAML** — writes `insights_enriched.yaml` back to R2 with the two fields IRIS leaves null filled in
7. **Conditional Triggers** — fires action briefs, Slack alerts, and document drafts based on meeting type and health signals

Beyond ingestion, CORTEX also handles:

- **Document generation** — status reports, KT documents, milestone deliverables (LLM-generated, versioned, stored in R2)
- **Document upload registration** — PM uploads SOW/architecture docs via intranet, CORTEX registers and extracts structure
- **Role-aware chat** — intranet project page chatbot where the same underlying data is shaped differently for PM, BA/Sales, Director, or APM
- **Team change handling** — on PM reassignment, auto-generates an onboarding brief and KT document
- **Scheduled jobs** — weekly plans every Monday 07:30 IST, daily health scans at 08:00, cadence gap monitoring, Sunday renewal signals
- **Slack notifications** — health alerts, action briefs, weekly summaries (capability built; delivery activation deferred)
- **Calibration events** — immutable overlays when project context shifts (POC → Milestone 1, scope change, timeline rebase). Raw history is never mutated.

---

## Pipeline Position

```
Meeting artifacts (R2)
        │
        ▼
    IRIS (8000)       — Agent 1: extracts structured insights.yaml per meeting
        │  NERVE event
        ▼
    CELL (8002)       — Agent 2: intern tasks, EOD, bounties, ERP writes
        │  weekly summary API
        ▼
    CORTEX (8004)     — Agent 3: project memory, health, documents, PM intelligence
        │
        ▼
    Intranet chatbot  — embedded on project page, role-aware, conversational
```

---

## Full Request Flow

### 1. Meeting Ingestion (NERVE event)

```
IRIS fires → POST /cortex/ingest-nerve
                │
                ├─ Step 1: Download insights.yaml from R2
                │          Parse + validate (InsightsYAML schema)
                │          Embed summary → pgvector
                │          Insert into meeting_insights
                │
                ├─ Step 2: Load project_memory
                │          Fill previous_meeting_ref (last meeting ref)
                │          Append to sentiment_history
                │          Merge new risks into risk_register
                │          Age unresolved blockers in blocker_log
                │          Update milestone_status
                │
                ├─ Step 3: LLM call → update relationship_trajectory
                │          { trend: improving|stable|declining, narrative: "..." }
                │
                ├─ Step 4: Deterministic health score (0–100)
                │          sentiment_penalty + open_risks_penalty
                │          + blocker_penalty + milestone_penalty
                │          + trajectory_penalty + velocity_penalty
                │          Band: green (≥80) / amber (≥60) / red (<60)
                │          Insert into project_health_scores
                │
                ├─ Step 5: Milestone drift detection
                │          current_due_date vs original_due_date
                │          Flag at_risk milestones
                │
                ├─ Step 6: Write insights_enriched.yaml → R2
                │          Adds previous_meeting_ref + relationship_trajectory
                │          that IRIS left null
                │
                └─ Step 7: Conditional triggers
                           client-call     → action brief via Slack
                           milestone-review → draft milestone deliverable
                           health score red → health alert via Slack
                           3× sentiment decline → alert
                           POC todo items → POST /cell/ingest-tasks
```

### 2. Chat (Intranet project page)

```
Intranet sends X-Employee-ID header
→ POST /cortex/chat
    │
    ├─ Resolve role from employee profile (PM/RM | BA/Sales | Director | APM)
    ├─ Semantic retrieval from pgvector for relevant past context
    ├─ Role-aware system prompt selected
    ├─ LLM call (Claude primary, Groq fallback)
    └─ Response shaped for role
       PM:       operational detail, risks, blockers, sentiment
       BA/Sales: champion identification, expansion signals
       Director: portfolio health, cost, timeline, renewal
       APM:      tasks, velocity, intern performance
```

### 3. Document Generation

```
POST /cortex/documents/status-report
POST /cortex/documents/kt-document
POST /cortex/documents/milestone-deliverable
    │
    ├─ Pull project memory + health scores + milestones from DB
    ├─ LLM generates document from template
    ├─ Version assigned (v1.0, v1.1, ...)
    ├─ Saved to R2: projects/<id>/generated-docs/<name>_<version>.md
    ├─ Registered in project_documents table (status: draft)
    └─ PM approval loop via Slack before finalising
```

### 4. Document Upload (Manual — PM uploads SOW etc.)

```
POST /cortex/document-upload
    │
    ├─ Register in project_documents (source: manual_upload)
    ├─ Extract structured data from PDF/MD (LLM call)
    └─ Milestones, timeline, scope extracted → stored in extracted_data JSONB
```

### 5. Team Change (PM Reassignment)

```
ERP webhook → POST /cortex/team-change
    │
    ├─ Receive: project_id, old_pm, new_pm, reason
    ├─ Generate onboarding brief for new PM (full story so far)
    └─ Generate KT document (decisions, risks, relationship history, open items)
```

### 6. Calibration Events

```
POST /cortex/calibrate
    │
    ├─ Receive: project_id, event_type, description, before_state, after_state
    ├─ Insert into calibration_events (immutable — never delete)
    └─ All downstream reporting reads through the calibration lens
       Raw history always preserved
       Multiple calibration events allowed (full audit trail)
```

### 7. Scheduled Jobs (APScheduler, IST-anchored)

| Time | Job | What it does |
|---|---|---|
| Monday 07:30 | `weekly_plan_job` | Pull CELL velocity summary, generate PM plan per active project, push POC todos to CELL |
| Daily 08:00 | `health_scan_job` | Re-scan all active projects, post Slack health alerts if thresholds breached |
| Monday 09:00 | `cadence_check_job` | Flag projects with no client call in the last 14 days |
| Sunday 08:00 | `renewal_signal_job` | Flag projects where end_date < 6 weeks away |

---

## Project Structure

```
project_health_agent_new/
│
├── cortex/
│   ├── main.py                    # FastAPI app, lifespan, router registration
│   ├── config.py                  # All env vars + constants
│   ├── scheduler.py               # APScheduler setup (4 jobs, Asia/Kolkata)
│   │
│   ├── routers/
│   │   ├── nerve.py               # POST /cortex/ingest-nerve (7-step pipeline)
│   │   ├── chat.py                # POST /cortex/chat
│   │   ├── documents.py           # POST /cortex/document-upload + /documents/*
│   │   ├── slack.py               # POST /cortex/slack/* (health-alert, action-brief, weekly-summary)
│   │   ├── team.py                # POST /cortex/team-change (router stub)
│   │   ├── team_change.py         # POST /cortex/team-change (implementation)
│   │   └── calibrate.py           # POST /cortex/calibrate
│   │
│   ├── services/
│   │   ├── ingest.py              # Step 1: yaml download, parse, embed, store
│   │   ├── memory.py              # Step 2: cross-meeting memory stitch
│   │   ├── narrative.py           # Step 3: LLM relationship_trajectory update
│   │   ├── health.py              # Step 4: deterministic health score (6 dimensions)
│   │   ├── drift.py               # Step 5: milestone drift detection
│   │   ├── enrich.py              # Step 6: write insights_enriched.yaml to R2
│   │   ├── triggers.py            # Step 7: conditional post-ingest triggers
│   │   ├── documents.py           # Document lifecycle: generate, version, approve
│   │   ├── weekly_plan.py         # Monday plan generation + CELL handoff
│   │   ├── kt.py                  # KT + onboarding brief generation
│   │   ├── alerts.py              # Health/blocker/sentiment threshold alerts
│   │   ├── slack_notifier.py      # Slack SDK wrapper (deferred delivery)
│   │   ├── cell_client.py         # GET /cell/summary stub
│   │   ├── templates.py           # Document template loader
│   │   └── chat.py                # Chat service entry point
│   │
│   ├── chat/
│   │   ├── engine.py              # Chat orchestration: role resolution, context, LLM call
│   │   ├── role_prompts.py        # Role-aware system prompts (PM/BA/Director/APM)
│   │   └── retrieval.py           # pgvector semantic retrieval for chat context
│   │
│   ├── llm/
│   │   ├── client.py              # Anthropic + Groq client wrappers
│   │   └── prompts/
│   │       ├── narrative.py       # relationship_trajectory prompt
│   │       ├── action_brief.py    # Post-meeting action brief prompt
│   │       ├── doc_extract.py     # Structured extraction from uploaded docs
│   │       ├── doc_generate.py    # Document generation prompt
│   │       ├── weekly_plan.py     # Weekly plan generation prompt
│   │       └── kt.py              # KT document generation prompt
│   │
│   ├── integrations/
│   │   ├── r2.py                  # R2 download/upload (boto3)
│   │   ├── cell_api.py            # CELL summary + ingest-tasks
│   │   ├── erp.py                 # ERP milestone webhook
│   │   ├── intranet.py            # Employee/role lookup
│   │   └── slack.py               # Slack messaging
│   │
│   └── models/
│       ├── db.py                  # asyncpg connection pool + schema init
│       └── schemas.py             # Pydantic models (NERVEEvent, InsightsYAML, etc.)
│
├── seed_and_test.py               # End-to-end test + seed data runner
├── inspect_meeting.py             # CLI tool to inspect ingested meeting data
├── requirements-cortex.txt        # All Python dependencies
├── CORTEX_ARCHITECTURE.md         # Full architecture + data models + design decisions
├── TESTING_GUIDE.md               # How to run tests and seed data
└── .env                           # Environment variables (not committed)
```

---

## Data Models (Key Tables)

| Table | Purpose |
|---|---|
| `clients` | Client organisations, relationship status |
| `projects` | Projects (client or internal), linked to ERP |
| `project_milestones` | SOW milestones with original + current due dates |
| `calibration_events` | Immutable overlays for context shifts |
| `meeting_insights` | Every ingested meeting — raw YAML + embedding |
| `project_memory` | One row per project — living memory (sentiment history, risk register, blocker log, trajectory) |
| `project_health_scores` | Health score history per project per meeting |
| `client_stakeholders` | External attendees, champion tracking |
| `stakeholder_sentiment_log` | Per-stakeholder sentiment per meeting |
| `project_documents` | All documents (manual + generated), versioned |
| `pm_task_plans` | Weekly PM plans, linked to CELL velocity data |
| `agent_actions` | Full audit log of every action CORTEX takes |

---

## Health Score Calculation

The health score is **deterministic — no LLM involved**. It starts at 100 and subtracts penalties:

| Dimension | Penalty condition |
|---|---|
| Sentiment | avg < 0.3 over last 3 meetings → –10 to –20 |
| Open risks | Each high-severity open risk → –10 |
| Blockers | Blocker age 3–7 days → –7; age >7 days → –15 |
| Milestones | Each at-risk milestone → –8 |
| Trajectory | Declining trend → –10 |
| Velocity | CELL data stub (to be wired) |

**Bands:** Green ≥ 80 · Amber ≥ 60 · Red < 60

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/cortex/health` | Health check |
| GET | `/` | Root |
| POST | `/cortex/ingest-nerve` | IRIS NERVE event → 7-step pipeline |
| POST | `/cortex/chat` | Intranet chatbot |
| POST | `/cortex/document-upload` | Register PM-uploaded doc |
| POST | `/cortex/documents/approve` | Approve a document |
| POST | `/cortex/documents/status-report` | Generate weekly status report |
| POST | `/cortex/documents/kt-document` | Generate KT document |
| POST | `/cortex/documents/milestone-deliverable` | Generate milestone deliverable |
| POST | `/cortex/slack/health-alert` | Post health alert to Slack |
| POST | `/cortex/slack/action-brief` | Post action brief to Slack |
| POST | `/cortex/slack/weekly-summary` | Post weekly summary to Slack |
| POST | `/cortex/team-change` | ERP PM reassignment webhook |
| POST | `/cortex/calibrate` | Create calibration event |

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL with `pgvector` extension (`CREATE EXTENSION IF NOT EXISTS vector;`)
- Cloudflare R2 bucket (shared with IRIS and CELL, named `erp-agents`)
- Anthropic API key (Claude — narrative, documents, chat)
- OpenAI API key (embeddings only — `text-embedding-3-small`)

### Install

```bash
pip install -r requirements-cortex.txt
```

### Environment Variables

Copy `.env` and fill in:

```env
# Database
DATABASE_URL=postgresql+asyncpg://cortex_user:cortex_pass@localhost:5432/cortex_db

# R2
R2_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=erp-agents

# LLM
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
OPENAI_API_KEY=sk-...

# Groq (chat fallback)
GROQ_API_KEY=...
GROQ_MODEL=llama-3.1-8b-instant

# Slack (build capability, activate when UI decided)
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...

# Internal services
CELL_API_BASE_URL=http://localhost:8002
CELL_API_KEY=...
ERP_API_BASE_URL=https://erp.internal
ERP_API_KEY=...
INTRANET_API_BASE_URL=https://intranet.internal/api
INTRANET_API_KEY=...

# CORTEX
CORTEX_HOST=0.0.0.0
CORTEX_PORT=8004
CORTEX_API_KEY=...
CORTEX_ENV=development

# Timezone
TZ=Asia/Kolkata

# Thresholds
HEALTH_SCORE_RED_THRESHOLD=60
HEALTH_SCORE_AMBER_THRESHOLD=80
BLOCKER_ALERT_DAYS=2
SENTIMENT_DECLINE_WINDOW=3
CADENCE_GAP_DAYS_CLIENT=14
RENEWAL_SIGNAL_WEEKS=6
```

### Run

```bash
# From project root
python -m cortex.main

# Or directly
uvicorn cortex.main:app --host 0.0.0.0 --port 8004 --reload
```

Swagger UI: `http://localhost:8004/docs`

### Seed + Test

```bash
python seed_and_test.py
```

This creates test projects, inserts mock meeting data, runs the full ingest pipeline, and verifies health scores and memory stitching. See `TESTING_GUIDE.md` for details.

---

## Integration Wires

| From | To | Mechanism |
|---|---|---|
| IRIS | CORTEX | `POST /cortex/ingest-nerve` (NERVE event after every extraction) |
| CORTEX | CELL | `GET /cell/summary/{project_id}` (weekly velocity — CELL must implement this) |
| CORTEX | CELL | `POST /cell/ingest-tasks` (POC todos on Monday plan) |
| Intranet | CORTEX | `POST /cortex/document-upload` (on PM file upload) |
| Intranet | CORTEX | `POST /cortex/chat` (project page chatbot, with X-Employee-ID) |
| Intranet | CORTEX | `POST /cortex/team-change` (on PM/POC reassignment) |
| ERP | CORTEX | `POST /cortex/team-change` (PM reassignment webhook) |
| CORTEX | ERP | `PATCH /api/milestones/:id` (on milestone deliverable approved) |
| CORTEX | Slack | Slack SDK (deferred — build now, wire when UI decided) |

---

## Known Gaps (Pre–Go-Live)

| # | Issue | Severity |
|---|---|---|
| 1 | CELL `/cell/summary` endpoint not yet implemented | Critical |
| 2 | Intranet must pass `X-Employee-ID` in chat requests | High |
| 3 | IRIS hashes external attendees — stakeholder profiles need IRIS-side fix | High |
| 4 | ERP must expose `PATCH /api/milestones/:id` | Medium |
| 5 | Slack delivery built but not activated | Low |
| 6 | `pgvector` extension must be enabled on `cortex_db` | Critical |

---

## Design Decisions

**Health score is deterministic, not LLM.** Auditable, testable, no hallucination risk on a number PMs act on. LLM is reserved for narrative and document generation only.

**CORTEX fills `previous_meeting_ref` and `relationship_trajectory`, not IRIS.** IRIS is stateless per meeting. Cross-meeting narrative is CORTEX's sole responsibility.

**Calibration events are immutable overlays.** When context shifts (POC → Milestone 1, scope change), CORTEX never mutates raw history. A calibration event layers over it. All reporting reads through the calibration lens. Full audit trail always intact.

**`insights_enriched.yaml` is additive, not a replacement.** IRIS output is source of truth. CORTEX enrichment is additive. Any future agent can consume either file.

**Role-aware chat from intranet profile, not self-declaration.** No role spoofing. Consistent. Employee identity resolved server-side from the intranet session.

**Client relationship preserved after project close.** Closed ≠ forgotten. Consultancy is building long-term client relationships. All history queryable indefinitely.

**Slack delivery capability built but not wired.** The intelligence layer is ready. Delivery activates when the notification UI is confirmed.