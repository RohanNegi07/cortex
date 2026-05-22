# CORTEX — Project Health Intelligence Service

This repository contains the current implementation of the CORTEX project health service.
The active codebase is focused on ingesting structured NERVE events, building project memory, and computing deterministic health scores.

---

## What this service does

The current running service supports:

- `POST /cortex/ingest-nerve` — ingest IRIS NERVE events
- `GET /cortex/health/{project_id}` — return the latest stored health score for a project
- `GET /healthz` — service liveness check
- project memory stitching from meeting insights
- deterministic health scoring based on project memory and CELL velocity
- scheduled background jobs via APScheduler

> Note: several router modules exist in `cortex/routers/`, but only the `nerve` router is mounted in `cortex/main.py` today.

---

## Current public endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Root service status |
| `GET` | `/healthz` | Liveness check |
| `GET` | `/cortex/health/{project_id}` | Latest computed project health score |
| `POST` | `/cortex/ingest-nerve` | Receive NERVE events from IRIS |

---

## Architecture at a glance

- `cortex/main.py` — FastAPI app, DB lifecycle, router registration, scheduler startup
- `cortex/config.py` — environment loading and configuration values
- `cortex/models/db.py` — PostgreSQL pool, schema initialization, DB queries
- `cortex/services/ingest.py` — ingest and store meeting insights
- `cortex/services/memory.py` — stitch project memory across meetings
- `cortex/services/health.py` — compute the deterministic health score
- `cortex/integrations/cell_api.py` — fetch velocity data from CELL
- `cortex/scheduler.py` — APScheduler recurring jobs

---

## Health scoring

The active health score implementation is deterministic and penalty-based.
It starts at `100` and subtracts penalties for:

- low or declining sentiment
- open high-severity risks
- unresolved blockers
- at-risk or drifted milestones
- declining relationship trajectory
- CELL velocity gaps
- blocked or at-risk meeting artifacts when present

The score is clamped to `0..100` and assigned a band:

- `green` — score ≥ 80
- `amber` — 60 ≤ score < 80
- `red` — score < 60

---

## Repository structure

```
project_health_agent_new/
├── cortex/
│   ├── main.py
│   ├── config.py
│   ├── scheduler.py
│   ├── routers/
│   │   ├── nerve.py
│   │   ├── chat.py
│   │   ├── documents.py
│   │   ├── slack.py
│   │   ├── team_change.py
│   │   ├── calibrate.py
│   │   └── eod.py
│   ├── services/
│   │   ├── ingest.py
│   │   ├── memory.py
│   │   ├── narrative.py
│   │   ├── health.py
│   │   ├── drift.py
│   │   ├── enrich.py
│   │   ├── triggers.py
│   │   ├── documents.py
│   │   ├── kt.py
│   │   ├── slack_notifier.py
│   │   ├── chat.py
│   │   ├── templates.py
│   │   ├── alerts.py
│   │   ├── cell_client.py
│   │   └── weekly_plan.py
│   ├── chat/
│   │   ├── engine.py
│   │   ├── retrieval.py
│   │   └── role_prompts.py
│   ├── llm/
│   │   ├── client.py
│   │   └── prompts/
│   └── integrations/
│       ├── cell_api.py
│       ├── erp.py
│       └── intranet.py
│   └── models/
│       ├── db.py
│       └── schemas.py
├── .env.example
└── requirements-cortex.txt
```

---

## Running locally

1. Install dependencies:

```powershell
pip install -r requirements-cortex.txt
```

2. Create and edit `.env` from the example:

```powershell
copy .env.example .env
```

3. Start the service:

```powershell
python -m cortex.main
```

4. Verify the app at:

```
http://localhost:8004/docs
```

---

## Configuration

`cortex/config.py` reads env vars used by the service.
Important values include:

- `DATABASE_URL`
- `CORTEX_HOST`
- `CORTEX_PORT`
- `ANTHROPIC_API_KEY`
- `CELL_API_BASE_URL`
- `CELL_API_KEY`
- `OPENAI_API_KEY`
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`

---

## Notes

- The currently active service surface is limited to NERVE ingest and health reporting.
- The repo contains additional router modules, but they are not mounted in `main.py` today.
- `cortex/integrations/intranet.py` is still a stubbed lookup helper and may not resolve real employee metadata.
- `cortex/integrations/cell_api.py` is used for velocity lookup; it does not currently fall back to mocked data.
