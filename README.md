# CORTEX — Project Health Intelligence Service

**CORTEX** (Client Oversight & Relationship Trajectory Executive) is the project intelligence and PM command layer of a consultancy's internal toolchain. It sits at the end of a three-service pipeline:

```
IRIS  →  CELL  →  CORTEX
(transcription & extraction)  (task tracking)  (project health, memory, documents, chat)
```

CORTEX receives structured meeting extraction events from IRIS, builds living project memory, computes deterministic health scores, generates documents, posts Slack alerts, and answers role-aware questions about any project.

---

## Table of Contents

1. [What this service does](#what-this-service-does)
2. [Architecture at a glance](#architecture-at-a-glance)
3. [The 7-step ingest pipeline](#the-7-step-ingest-pipeline)
4. [Health score logic](#health-score-logic)
5. [Project structure](#project-structure)
6. [All API endpoints](#all-api-endpoints)
7. [Key data models](#key-data-models)
8. [Scheduled jobs](#scheduled-jobs)
9. [Configuration & environment variables](#configuration--environment-variables)
10. [Running locally](#running-locally)
11. [External dependencies](#external-dependencies)
12. [Concepts for new readers](#concepts-for-new-readers)

---

## What this service does

| Capability | How it works |
|---|---|
| **Meeting ingest** | Receives `NERVEEvent` payloads from IRIS and runs a 7-step pipeline to process each meeting |
| **Project memory** | Stitches sentiment history, risk register, blocker log, and milestone state across meetings |
| **Health scoring** | Deterministic (no LLM) score from 0–100, banded as green/amber/red |
| **Narrative update** | LLM-generated relationship trajectory text, updated per meeting |
| **Document generation** | Status reports, KT (knowledge transfer) docs, milestone deliverables |
| **EOD reports** | Daily end-of-day submissions that roll up into weekly health summaries |
| **Team change handling** | PM reassignment webhooks that auto-trigger KT document generation |
| **Calibration events** | Manual re-baselining of project health, recorded for audit |
| **Slack notifications** | Health alerts, action briefs, and weekly summaries posted to Slack |
| **Project chat** | Role-aware (PM / BA / Director / APM) Q&A interface backed by Claude |

---

## Architecture at a glance

```
┌──────────────────────────────────────────────────────────────┐
│                        CORTEX (port 8004)                    │
│                                                              │
│  FastAPI app  ──  routers/  ──  services/  ──  models/db.py  │
│       │                │                                     │
│   scheduler       integrations/          pgvector (memory)   │
│  (APScheduler)    cell_api / erp                             │
│                   intranet / slack                            │
└──────────────────────────────────────────────────────────────┘
          ▲                    ▲
       IRIS sends          ERP / Intranet
     NERVEEvent            webhooks
```

- **FastAPI** runs on port `8004` (configurable).
- **asyncpg** manages a connection pool to PostgreSQL (with pgvector for semantic search).
- **APScheduler** runs recurring background jobs (health scans, weekly plans, cadence checks).
- **Anthropic Claude** is used for narrative updates, document generation, and chat.
- **Cloudflare R2** (via boto3) is referenced for document storage.
- **Slack SDK** posts notifications via a bot token.

---

## The 7-step ingest pipeline

When IRIS sends a `POST /cortex/ingest-nerve` event, the `nerve` router runs these steps in order:

```
Step 1 → INGEST           parse, validate, embed, and store insights in DB
Step 2 → MEMORY STITCH    build cross-meeting memory: sentiment, risks, blockers, milestones
Step 3 → NARRATIVE UPDATE LLM-generated relationship trajectory text
Step 4 → HEALTH SCORE     deterministic scoring (starts at 100, subtracts penalties)
Step 5 → MILESTONE DRIFT  detect delayed milestones
Step 6 → ENRICH YAML      write insights_enriched.yaml back to storage
Step 7 → TRIGGERS         fire conditional actions (Slack alerts, action briefs, docs)
```

Each step is a separate service function. If a step fails, the pipeline logs the error but continues (it is non-fatal after Step 1). The endpoint returns:

```json
{
  "status": "success",
  "project_id": "...",
  "meeting_id": "...",
  "health_score": 74,
  "steps_completed": 7
}
```

If the meeting was already ingested, it returns `{"status": "skipped", "meeting_id": "..."}`.

---

## Health score logic

The health score is **fully deterministic** — no LLM is involved. It starts at 100 and subtracts penalties across 6 dimensions:

| Dimension | Weight | What causes a penalty |
|---|---|---|
| `sentiment_penalty` | 20% | Sentiment score below 0.3 threshold |
| `open_risks_penalty` | 20% | High-severity open risks |
| `blocker_penalty` | 20% | Blockers unresolved for more than `BLOCKER_ALERT_DAYS` |
| `milestone_penalty` | 20% | At-risk or drifted milestones |
| `trajectory_penalty` | 10% | Declining relationship trajectory |
| `velocity_penalty` | 10% | Velocity gap from CELL |
| `artifact_penalty` | 10% | EOD reports with blocked/at-risk status |

**Bands:**

| Band | Score range |
|---|---|
| `green` | ≥ 80 |
| `amber` | ≥ 60 and < 80 |
| `red` | < 60 |

Thresholds are configurable via `HEALTH_SCORE_RED_THRESHOLD` and `HEALTH_SCORE_AMBER_THRESHOLD`.

---

## Project structure

```
project_health_agent_new/
├── cortex/
│   ├── main.py                  # FastAPI app, lifespan, routers, root endpoint
│   ├── config.py                # All env vars loaded from .env
│   ├── scheduler.py             # APScheduler recurring jobs
│   │
│   ├── routers/                 # HTTP layer — thin, validate + delegate to services
│   │   ├── nerve.py             # POST /cortex/ingest-nerve  (7-step pipeline)
│   │   ├── chat.py              # POST /cortex/chat
│   │   ├── documents.py         # Document upload, approval, generation
│   │   ├── slack.py             # Slack webhook receivers
│   │   ├── team_change.py       # Team/PM reassignment webhook
│   │   ├── calibrate.py         # POST /cortex/health/calibrate
│   │   └── eod.py               # EOD report ingest + weekly health compute
│   │
│   ├── services/                # Business logic layer
│   │   ├── ingest.py            # Step 1: Parse, embed, store meeting insights
│   │   ├── memory.py            # Step 2: Stitch project memory across meetings
│   │   ├── narrative.py         # Step 3: LLM relationship trajectory
│   │   ├── health.py            # Step 4: Deterministic health score
│   │   ├── drift.py             # Step 5: Milestone drift detection
│   │   ├── enrich.py            # Step 6: Write enriched YAML
│   │   ├── triggers.py          # Step 7: Conditional alerts / docs / tasks
│   │   ├── eod.py               # EOD ingestion and weekly health aggregation
│   │   ├── documents.py         # Document generation and upload handling
│   │   ├── kt.py                # KT document generation for team handovers
│   │   ├── slack_notifier.py    # Slack message posting (alerts, briefs, summaries)
│   │   ├── chat.py              # Chat request processing
│   │   ├── templates.py         # Document template loading
│   │   ├── alerts.py            # Alert dispatch helpers
│   │   ├── cell_client.py       # CELL API stub client
│   │   └── weekly_plan.py       # Weekly plan generation
│   │
│   ├── chat/                    # Chat subsystem
│   │   ├── engine.py            # Orchestration, role selection, LLM invocation
│   │   ├── role_prompts.py      # System prompts per role (PM / BA / Director / APM)
│   │   └── retrieval.py         # pgvector semantic retrieval of meeting context
│   │
│   ├── llm/                     # LLM wrapper
│   │   ├── client.py            # Anthropic + Groq API clients
│   │   └── prompts/
│   │       ├── narrative.py     # Relationship trajectory prompt
│   │       ├── action_brief.py  # Post-meeting action brief prompt
│   │       ├── doc_generate.py  # Document generation prompt
│   │       ├── doc_extract.py   # Document extraction prompt
│   │       ├── kt.py            # KT document prompt
│   │       └── weekly_plan.py   # Weekly plan prompt
│   │
│   ├── integrations/            # External system clients
│   │   ├── cell_api.py          # CELL summary and task ingest stubs
│   │   ├── erp.py               # ERP project/team webhook integration
│   │   └── intranet.py          # Employee/role lookup stub
│   │
│   └── models/
│       ├── db.py                # asyncpg pool, schema init, all DB queries
│       └── schemas.py           # All Pydantic request/response models
│
├── .env.example                 # Copy to .env and fill in values
└── requirements-cortex.txt      # Python dependencies
```

---

## All API endpoints

All endpoints are served from `http://localhost:8004` (or wherever `CORTEX_HOST:CORTEX_PORT` is configured).

Protected endpoints require an `x-api-key` header matching `CORTEX_API_KEY`. In `development` mode with no key configured, auth is skipped.

### Root & health check

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | No | Returns service name, version, and status |
| `GET` | `/healthz` | No | Liveness check; returns `HealthCheckResponse` |

**`GET /healthz` response:**
```json
{
  "status": "ok",
  "message": "CORTEX is running",
  "database_connected": true,
  "version": "0.1.0"
}
```

---

### Project health

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/cortex/health/{project_id}` | No | Latest health score for a project |
| `GET` | `/cortex/health/{project_id}/weekly/{week_start}` | No | Read stored weekly EOD health |
| `POST` | `/cortex/health/{project_id}/weekly/{week_start}/compute` | No | Compute weekly EOD health from stored reports |

`{project_id}` can be the internal UUID or an external ERP project ID — CORTEX normalizes it.
`{week_start}` is a date in `YYYY-MM-DD` format.

**`GET /cortex/health/{project_id}` response:**
```json
{
  "project_id": "uuid-...",
  "score": 74,
  "band": "amber",
  "components": {
    "sentiment_penalty": 10,
    "open_risks_penalty": 5,
    "blocker_penalty": 8,
    "milestone_penalty": 0,
    "trajectory_penalty": 0,
    "velocity_penalty": 3
  },
  "computed_after_meeting_id": "mtg-abc-123",
  "computed_at": "2026-05-21T08:00:00"
}
```

---

### NERVE ingest (main pipeline entry point)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/cortex/ingest-nerve` | `x-api-key` | Receive IRIS extraction event; run 7-step pipeline |

**Request body (`NERVEEvent`):**
```json
{
  "event_type": "iris.extraction.complete",
  "project_id": "erp-proj-001",
  "meeting_id": "mtg-2026-05-21-standup",
  "meeting_date": "2026-05-21",
  "timestamp": "2026-05-21T10:30:00",
  "insights": {
    "meeting_id": "mtg-2026-05-21-standup",
    "project_id": "erp-proj-001",
    "meeting_type": "standup",
    "meeting_date": "2026-05-21",
    "summary": "Team discussed blocker on integration module.",
    "risks": [{"id": "r-001", "description": "API latency risk", "severity": "high"}],
    "blockers": [{"id": "b-001", "description": "Auth service down", "raised_date": "2026-05-20"}],
    "sentiment": {"score": 0.4, "label": "neutral"},
    "milestones": []
  },
  "meeting_artifacts": {
    "eod_reports": [],
    "documents": []
  }
}
```

**Response:**
```json
{
  "status": "success",
  "project_id": "uuid-...",
  "meeting_id": "mtg-2026-05-21-standup",
  "health_score": 74,
  "steps_completed": 7
}
```

---

### Chat (role-aware project Q&A)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/cortex/chat` | No | Ask a question about a project in natural language |

Roles available: `pm`, `director`, `ba`, `apm`. Each role gets a different system prompt and response style.

**Request (`ChatRequest`):**
```json
{
  "project_id": "erp-proj-001",
  "question": "What are the top risks right now?",
  "user_role": "pm",
  "conversation_history": []
}
```

**Response (`ChatResponse`):**
```json
{
  "answer": "The project has two open high-severity risks...",
  "project_id": "erp-proj-001",
  "user_role": "pm",
  "health_score": 74,
  "status": "amber",
  "confidence": 0.85,
  "sources": ["mtg-abc-001", "mtg-abc-002"],
  "generated_at": "2026-05-21T11:00:00"
}
```

---

### Documents

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/cortex/document-upload` | `x-api-key` | Register a document uploaded to R2 |
| `POST` | `/cortex/documents/approve` | `x-api-key` | Mark a document as approved |
| `POST` | `/cortex/documents/status-report` | No | Generate a weekly status report |
| `POST` | `/cortex/documents/kt-document` | No | Generate a knowledge transfer document |
| `POST` | `/cortex/documents/milestone-deliverable` | No | Generate a milestone deliverable |

**`POST /cortex/document-upload` request:**
```json
{
  "project_id": "erp-proj-001",
  "document_type": "sow",
  "r2_key": "projects/erp-proj-001/source-docs/sow.pdf",
  "source": "manual_upload",
  "uploader": "pm@company.com"
}
```

**`POST /cortex/documents/status-report` request (`DocumentRequest`):**
```json
{
  "project_id": "erp-proj-001",
  "document_type": "status_report",
  "meeting_id": "mtg-abc-001"
}
```

**Document generation response (`DocumentResponse`):**
```json
{
  "project_id": "erp-proj-001",
  "document_type": "status_report",
  "content": "## Weekly Status Report\n...",
  "file_path": "/path/to/generated/file",
  "version": 1,
  "generated_at": "2026-05-21T12:00:00"
}
```

**Valid `document_type` values:** `sow`, `solution_architecture`, `timeline`, `proposal`, `milestone_deliverable`, `status_report`, `kt_document`, `onboarding_brief`, `renewal_proposal`, `other`

---

### Slack webhook receivers

These endpoints receive calls from CORTEX's own scheduler/trigger system and forward messages to Slack.

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/cortex/slack/health-alert` | `x-api-key` | Post a health alert to Slack |
| `POST` | `/cortex/slack/action-brief` | `x-api-key` | Post an action brief to Slack |
| `POST` | `/cortex/slack/weekly-summary` | `x-api-key` | Post a weekly summary to Slack |

**`POST /cortex/slack/health-alert` request:**
```json
{
  "project_id": "erp-proj-001",
  "score": 55,
  "band": "red",
  "old_score": 72,
  "components": {"sentiment_penalty": 15, "blocker_penalty": 20}
}
```

**`POST /cortex/slack/weekly-summary` request:**
```json
{
  "project_id": "erp-proj-001",
  "week_ref": "2026-W21",
  "completion_rate": 0.75,
  "risks": ["API latency unresolved"],
  "blockers": [],
  "upcoming_milestones": ["UAT handoff on 2026-05-28"]
}
```

---

### Team change

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/cortex/team/change` | `x-api-key` | Handle PM or POC reassignment |

For `pm_reassignment`, CORTEX automatically generates a KT document for the incoming PM.

**Request (`TeamChangePayload`):**
```json
{
  "project_id": "erp-proj-001",
  "change_type": "pm_reassignment",
  "outgoing_employee_id": "emp-ananya-001",
  "incoming_employee_id": "emp-priya-002",
  "effective_date": "2026-05-28"
}
```

**Response:**
```json
{
  "status": "ok",
  "project_id": "erp-proj-001",
  "change_type": "pm_reassignment",
  "message": "Team change processed for erp-proj-001",
  "kt_document": {
    "document_id": "doc-uuid-...",
    "r2_url": "https://r2.../kt-doc.md",
    "slack_posted": true
  }
}
```

**Valid `change_type` values:** `pm_reassignment`, `poc_added`, `poc_removed`

---

### Calibration events

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/cortex/health/calibrate` | `x-api-key` | Record a manual health re-baseline event |

Used when a PM or director wants to manually reset or annotate the health baseline (e.g., after a major project recovery).

**Request (`CalibratePayload`):**
```json
{
  "project_id": "erp-proj-001",
  "event_type": "manual_rebaseline",
  "description": "Scope reduced by client. Health reset to green.",
  "created_by": "director@company.com",
  "before_state": {"score": 55, "band": "red"},
  "after_state": {"score": 82, "band": "green"}
}
```

**Response:**
```json
{"status": "ok", "event_id": "cal-uuid-..."}
```

---

### EOD (End-of-Day) reporting

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/cortex/eod/` | `x-api-key` | Submit a daily EOD report |
| `POST` | `/cortex/eod/{project_id}/weekly/{week_start}/compute` | `x-api-key` | Compute weekly health from EOD reports |
| `GET` | `/cortex/eod/{project_id}/weekly/{week_start}` | No | Read stored weekly EOD health |

EOD health scores are separate from the standard meeting-based health scores. They are computed from the week's EOD submissions and stored independently.

**`POST /cortex/eod/` request (`EODReportRequest`):**
```json
{
  "project_id": "erp-proj-001",
  "reporter_id": "emp-dev-003",
  "report_date": "2026-05-21",
  "status": "blocked",
  "summary": "Auth integration blocked on DevOps response.",
  "tasks_completed": [{"task": "Wrote unit tests for billing module"}],
  "tasks_blocked": [{"task": "Auth service integration", "assignee": "DevOps team"}]
}
```

**Valid `status` values:** `on_track`, `at_risk`, `blocked`, `leave`

**Weekly EOD health response (`WeeklyEODHealth`):**
```json
{
  "project_id": "uuid-...",
  "week_start": "2026-05-18",
  "score": 68,
  "band": "amber",
  "components": {"blocked_count": 2, "on_track_count": 3},
  "eod_count": 5,
  "created_at": "2026-05-21T07:00:00"
}
```

---

### Complete endpoint reference table

| Method | Path | Auth Required | Router file |
|---|---|---|---|
| `GET` | `/` | No | `main.py` |
| `GET` | `/healthz` | No | `main.py` |
| `GET` | `/cortex/health/{project_id}` | No | `main.py` |
| `GET` | `/cortex/health/{project_id}/weekly/{week_start}` | No | `main.py` |
| `POST` | `/cortex/health/{project_id}/weekly/{week_start}/compute` | No | `main.py` |
| `POST` | `/cortex/ingest-nerve` | `x-api-key` | `routers/nerve.py` |
| `POST` | `/cortex/chat` | No | `routers/chat.py` |
| `POST` | `/cortex/document-upload` | `x-api-key` | `routers/documents.py` |
| `POST` | `/cortex/documents/approve` | `x-api-key` | `routers/documents.py` |
| `POST` | `/cortex/documents/status-report` | No | `routers/documents.py` |
| `POST` | `/cortex/documents/kt-document` | No | `routers/documents.py` |
| `POST` | `/cortex/documents/milestone-deliverable` | No | `routers/documents.py` |
| `POST` | `/cortex/slack/health-alert` | `x-api-key` | `routers/slack.py` |
| `POST` | `/cortex/slack/action-brief` | `x-api-key` | `routers/slack.py` |
| `POST` | `/cortex/slack/weekly-summary` | `x-api-key` | `routers/slack.py` |
| `POST` | `/cortex/team/change` | `x-api-key` | `routers/team_change.py` |
| `POST` | `/cortex/health/calibrate` | `x-api-key` | `routers/calibrate.py` |
| `POST` | `/cortex/eod/` | `x-api-key` | `routers/eod.py` |
| `POST` | `/cortex/eod/{project_id}/weekly/{week_start}/compute` | `x-api-key` | `routers/eod.py` |
| `GET` | `/cortex/eod/{project_id}/weekly/{week_start}` | No | `routers/eod.py` (via main) |

Interactive Swagger docs are always available at `http://localhost:8004/docs`.

---

## Key data models

All models live in `cortex/models/schemas.py`. Here are the most important ones:

### `NERVEEvent`
The payload IRIS sends to trigger ingestion. Contains `project_id`, `meeting_id`, `meeting_date`, and nested `InsightsYAML`.

### `InsightsYAML`
The structured meeting extraction from IRIS. Contains `risks`, `blockers`, `sentiment`, `milestones`, and `summary`. This is stored directly in the DB after ingestion.

### `ProjectHealthScore`
The computed health output. Fields: `project_id`, `score` (0–100), `band` (green/amber/red), `components` (penalty breakdown), `computed_at`.

### `EODReportRequest` / `EODReportResponse`
Daily end-of-day submission per team member. Contains `status`, `summary`, and lists of completed/blocked tasks.

### `WeeklyEODHealth`
Aggregated health from a week's worth of EOD reports. Separate from the meeting-based `ProjectHealthScore`.

### `ChatRequest` / `ChatResponse`
Input for the chat endpoint. The response includes the LLM answer, current health score, and the meeting IDs used as sources.

### `DocumentRequest` / `DocumentResponse`
Input for document generation. The response contains the generated `content` as markdown text.

---

## Scheduled jobs

CORTEX runs four recurring background jobs via APScheduler (all times in IST by default):

| Job | Schedule | Config var | Description |
|---|---|---|---|
| Weekly plans | Monday 07:30 | `WEEKLY_PLAN_TIME` | Generate weekly work plans for all active projects |
| Daily health scan | Daily 08:00 | `HEALTH_SCAN_TIME` | Re-score all projects; send alerts where needed |
| Cadence check | Monday 09:00 | `CADENCE_CHECK_TIME` | Flag projects missing client meetings |
| Weekly EOD health | Sunday 07:00 | `WEEKLY_HEALTH_TIME` | Aggregate EOD reports into weekly scores |

The scheduler is started in the FastAPI lifespan handler and stopped on shutdown.

---

## Configuration & environment variables

Copy `.env.example` to `.env` and fill in values before running.

### Database
| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://cortex_user:cortex_pass@localhost:5432/cortex_db` | PostgreSQL connection string (asyncpg format) |
| `DATABASE_POOL_SIZE` | `10` | Connection pool size |
| `DATABASE_MAX_OVERFLOW` | `20` | Max overflow connections |

### LLM
| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Claude API key (required for narrative, documents, chat) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `OPENAI_API_KEY` | — | OpenAI key for embeddings (`text-embedding-3-small`) |
| `GROQ_API_KEY` | — | Optional Groq key for lightweight LLM calls |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model |

### External services
| Variable | Default | Description |
|---|---|---|
| `IRIS_API_BASE_URL` | `http://localhost:8000` | IRIS service (sends NERVEEvents to CORTEX) |
| `IRIS_API_KEY` | — | Auth key for IRIS |
| `CELL_API_BASE_URL` | `http://localhost:8002` | CELL task tracking service |
| `CELL_API_KEY` | — | Auth key for CELL |
| `ERP_API_BASE_URL` | — | ERP system for project/employee data |
| `ERP_API_KEY` | — | Auth key for ERP |
| `INTRANET_API_BASE_URL` | — | Intranet for employee lookups |
| `INTRANET_API_KEY` | — | Auth key for Intranet |
| `SLACK_BOT_TOKEN` | — | Slack bot token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | — | Slack signing secret |

### CORTEX service
| Variable | Default | Description |
|---|---|---|
| `CORTEX_HOST` | `0.0.0.0` | Bind address |
| `CORTEX_PORT` | `8004` | Port |
| `CORTEX_API_KEY` | — | API key for protected endpoints (omit to disable auth in dev) |
| `CORTEX_ENV` | `development` | `development` or `production` |
| `TZ` | `Asia/Kolkata` | Timezone for scheduler |

### Health score thresholds
| Variable | Default | Description |
|---|---|---|
| `HEALTH_SCORE_RED_THRESHOLD` | `60` | Below this = red |
| `HEALTH_SCORE_AMBER_THRESHOLD` | `80` | Below this = amber |
| `BLOCKER_ALERT_DAYS` | `2` | Blocker age (days) before penalty applies |
| `SENTIMENT_DECLINE_WINDOW` | `3` | Meetings to look back for sentiment trend |
| `CADENCE_GAP_DAYS_CLIENT` | `14` | Days without client meeting before alert |
| `RENEWAL_SIGNAL_WEEKS` | `6` | Weeks before contract end to flag renewal |

---

## Running locally

**1. Install dependencies:**
```bash
pip install -r requirements-cortex.txt
```

**2. Configure environment:**
```bash
cp .env.example .env
# Edit .env with your DB URL, API keys, etc.
```

**3. Start the service:**
```bash
# Option A — module entry point
python -m cortex.main

# Option B — uvicorn with reload (dev)
uvicorn cortex.main:app --host 0.0.0.0 --port 8004 --reload
```

**4. Open Swagger UI:**
```
http://localhost:8004/docs
```

**5. Run tests:**
```bash
pytest tests/
```

---

## External dependencies

| Dependency | Purpose |
|---|---|
| `fastapi` + `uvicorn` | HTTP server |
| `asyncpg` | Async PostgreSQL (with pgvector for embeddings) |
| `anthropic` | Claude LLM for narrative, documents, chat |
| `openai` | `text-embedding-3-small` for pgvector semantic search |
| `groq` | Optional lightweight LLM |
| `boto3` | Cloudflare R2 document storage |
| `slack-sdk` | Slack bot messaging |
| `apscheduler` | Recurring background jobs |
| `pydantic` v2 | Request/response validation |
| `python-dotenv` | `.env` loading |
| `httpx` | Async HTTP client for integration calls |
| `pyyaml` | YAML parsing for enriched meeting files |

---

## Concepts for new readers

**Why is there a NERVE event?** IRIS processes meeting transcripts and extracts structured insight. It sends the result to CORTEX as a `NERVEEvent`. CORTEX does not transcribe or extract — it ingests, stores, computes, and acts.

**Why is the health score deterministic?** Consistency matters for PM trust. The score uses configurable rules against measurable signals (sentiment score, blocker age, milestone dates). LLMs are used only for narrative text and document content, not for scoring.

**What is "project memory"?** Memory is the stitched cross-meeting state: the last 3 meetings' context (short-term), plus sentiment history, open risks, blockers, and milestone status (long-term). The chat and narrative systems both read from memory.

**What is the difference between EOD health and project health?** Project health (`/cortex/health/{project_id}`) is computed from meeting insights after each NERVE event. EOD health (`/cortex/eod/...`) is computed weekly from daily team EOD submissions. They serve different audiences and cadences but both produce a score and band.

**What is a calibration event?** When a project's context changes dramatically (scope reduction, contract amendment, recovery from a crisis), a PM or director can record a calibration event. This creates an audit trail in `calibration_events` but does not automatically overwrite the health score — it is a human annotation.

**Where does project_id normalization happen?** Many callers use the ERP project ID (e.g. `erp-proj-001`). CORTEX maps this to an internal UUID via `normalize_project_id()` in `models/db.py`. All internal operations use the UUID.

**How does auth work?** Protected endpoints check the `x-api-key` header against `CORTEX_API_KEY`. In `development` mode with no key set, auth is skipped. In `production`, a missing or mismatched key returns HTTP 403.