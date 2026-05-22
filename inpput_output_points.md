# CORTEX API — Input & Output Reference

> **Service:** CORTEX (Client Oversight & Relationship Trajectory Executive)
> **Base URL:** `http://<host>:8004`
> **Auth:** `x-api-key` header required on protected endpoints when `CORTEX_API_KEY` is configured.

---

## Table of Contents

1. [Service Health](#1-service-health)
2. [NERVE — Meeting Ingest Pipeline](#2-nerve--meeting-ingest-pipeline)
3. [Project Health Score](#3-project-health-score)

---

## 1. Service Health

### `GET /healthz`

**Description:** Liveness check — confirms CORTEX is running.

**Input:** None

**Output:**
```json
{
  "status": "ok",
  "message": "CORTEX is running",
  "database_connected": true,
  "version": "0.1.0"
}
```

---

## 2. NERVE — Meeting Ingest Pipeline

### `POST /cortex/ingest-nerve`

**Description:** IRIS sends this event after extracting insights from a meeting. Triggers the full 7-step pipeline: Ingest → Memory Stitch → Narrative Update → Health Score → Milestone Drift → Enrich YAML → Conditional Triggers.

**Auth:** `x-api-key` header (optional, validated if `CORTEX_API_KEY` is set)

**Input (Request Body):**

| Field | Type | Required | Description |
|---|---|---|---|
| `event_type` | string | ✅ | e.g. `"iris.extraction.complete"` |
| `project_id` | string | ✅ | ERP or internal project identifier |
| `meeting_id` | string | ✅ | Unique meeting identifier |
| `meeting_date` | date | ✅ | Date of the meeting (`YYYY-MM-DD`) |
| `timestamp` | datetime | ✅ | Event timestamp |
| `insights` | object | ❌ | Structured IRIS extraction output (see below) |
| `meeting_artifacts` | object | ❌ | Transcripts, raw docs, etc. |

**`insights` object fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `meeting_id` | string | ✅ | |
| `project_id` | string | ✅ | |
| `meeting_type` | string | ✅ | `standup`, `client-call`, `milestone-review`, `internal`, `vendor`, `other` |
| `meeting_date` | date | ✅ | |
| `summary` | string | ✅ | |
| `risks` | array | ❌ | List of risk objects |
| `blockers` | array | ❌ | List of blocker objects |
| `sentiment` | object | ❌ | Sentiment analysis dict |
| `milestones` | array | ❌ | Milestone references |

**Output (Success):**
```json
{
  "status": "success",
  "project_id": "<internal-uuid>",
  "meeting_id": "<meeting-id>",
  "health_score": 78,
  "steps_completed": 7
}
```

**Output (Skipped — already ingested):**
```json
{
  "status": "skipped",
  "meeting_id": "<meeting-id>"
}
```

---

## 3. Project Health Score

### `GET /cortex/health/{project_id}`

**Description:** Returns the latest computed health score for a project.

**Input (Path Parameter):**

| Param | Type | Description |
|---|---|---|
| `project_id` | string | ERP or internal project ID |

**Output:**
```json
{
  "project_id": "<uuid>",
  "score": 74,
  "band": "amber",
  "components": {
    "sentiment_penalty": -5,
    "open_risks_penalty": -10,
    "blocker_penalty": -5,
    "milestone_penalty": 0,
    "trajectory_penalty": -3,
    "velocity_penalty": -3
  },
  "computed_after_meeting_id": "<meeting-id>",
  "computed_at": "2026-05-21T10:00:00Z"
}
```

**Health Bands:** `green` | `amber` | `red`

---

