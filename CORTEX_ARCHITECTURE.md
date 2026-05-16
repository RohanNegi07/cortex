# CORTEX — Full Architecture & Solution Design
**Client Oversight & Relationship Trajectory Executive**
*Agent 3 in the IRIS → CELL → CORTEX pipeline*
*Prepared for OpenCode implementation*

---

## 0. Pipeline Context

```
Meeting artifacts (R2)
        │
        ▼
    IRIS (8000)          — Agent 1: Extracts structured insights.yaml per meeting
        │  NERVE event
        ▼
    CELL (8002)          — Agent 2: Intern tasks, EOD, bounties, ERP writes
        │  Weekly summary API
        ▼
    CORTEX (8004)        — Agent 3: Project memory, health, documents, PM intelligence
        │
        ▼
    Intranet chatbot     — Embedded on project page, role-aware, conversational
```

**IRIS perceives. CELL executes. CORTEX thinks.**

---

## 1. What CORTEX Is

CORTEX is the project intelligence and PM command layer for the consultancy. It consumes every `insights.yaml` IRIS produces, stitches them into a living memory of each client engagement, tracks health and sentiment trajectories over time, manages the document lifecycle, detects risks and delays before they become misses, and answers any question any stakeholder has about any project — in a response shaped for their role.

It is the agent that notices the pattern before the PM does.

---

## 2. Full Capability Set

### Memory
- Stitch cross-meeting narrative — short-term rolling window (last 3 meetings) + long-term engagement story (full project lifetime)
- Fill `previous_meeting_ref` and `relationship_trajectory` that IRIS deliberately leaves blank
- Semantic retrieval via pgvector — surface past patterns relevant to current context
- Phase-aware memory — pre-project, active, closed phases treated differently
- Calibration events — PM can re-anchor project context (e.g. POC → Milestone 1) as immutable overlay events, never mutating raw history

### Health & Prediction
- Project health score computed after every meeting ingestion
- Predictive delay flags — pattern-based detection before a miss, not after
- Milestone drift detection — current velocity vs original SOW dates
- 3-consecutive-decline sentiment alert
- Velocity tracking from CELL — planned vs delivered per week per project

### Awareness
- Stakeholder sentiment tracking per external attendee over time
- Meeting cadence monitoring — absence of expected meetings is a signal
- Blocker age tracking — surfaces blockers unresolved past threshold
- Per-client health score in addition to per-project

### Planning
- Weekly PM plan every Monday 07:30 IST — delivered via Slack
- Recommended action brief after every `client-call` or `milestone-review` meeting
- POC todos handed off to CELL via `POST /cell/ingest-tasks`

### Documents
- Ingest and extract structure from manually uploaded SOW, solution architecture, timeline docs
- Generate and version: milestone deliverables, weekly status reports, proposals
- PM approval loop via Slack before anything is finalised
- Auto-draft weekly status report, auto-signal renewal as `end_date` approaches
- Full versioning — never overwrite, always new version

### Knowledge Transfer
- Onboarding brief when a new PM is assigned mid-engagement — full story so far
- KT document on demand — decisions made, risks, relationship history, open items, pending milestones
- Triggered via Slack command or team change event from ERP

### Queryable — Role-Aware Chatbot
- Embedded on intranet project page
- Employee identity and role resolved from intranet session
- Same underlying data, response shaped by who is asking
- Portfolio view for directors across all active projects

---

## 3. Role-Aware Response Matrix

| Role | What they care about | Response style |
|---|---|---|
| PM/RM | Relationship health, solution architecture, feature progress, on track, client sentiment, risks | Detailed, operational + relational |
| BA / Sales | Champion identification, discovery insights, stakeholder sentiment, expansion signals | Crisp, commercial |
| CEO / Director | Duration, cost, portfolio health, expansion opportunities | High level, business impact |
| APM | Tasks, blockers, intern performance, velocity | Execution focused |

Role is resolved automatically from the intranet employee profile. No self-declaration.

**Example responses to "How is this project going?" by role:**

- PM: "Sprint 3, day 4. Auth module complete. Staging blocker unresolved for 5 days — Milestone 2 at risk by May 20. Client sentiment declining over last 2 calls. Recommend escalating credentials access today."
- BA/Sales: "Client champion (Rajeev, CTO) has been engaged but sentiment dropped in the last call. Discovery identified two expansion areas — mobile SDK and reporting module — not yet in scope."
- Director: "Project 60% through timeline. Health score 72/100, amber. One at-risk milestone. Renewal signal in 6 weeks."
- APM: "3 tasks open for Arjun this week. 1 blocked on staging. Velocity down 20% vs last week."

---

## 4. Project Types

### Client Projects
- Locked before they open — project record created only after SOW is signed
- Have defined milestones, deliverables, external stakeholders
- Pre-project artifacts (POC, proposals, discovery notes) uploaded manually and linked
- POC can be re-anchored to Milestone 1 via calibration event

### Internal Projects
- No SOW — anchored by an abstract idea document (written by Saurabh, converted to MD by PM)
- Goal may shift over time — CORTEX tracks intent drift vs original idea doc
- CEO is the client — responses shaped accordingly
- No external stakeholder tracking needed
- Same memory and health infrastructure, different document templates

---

## 5. Project Lifecycle Phases

```
PRE-PROJECT
  └── POC / experiment / simulation / proposal / discovery
  └── Artifacts: POC transcripts, proposal docs, discovery call notes
  └── Stored in R2 under /pre-project/<client_id>/ before project_id exists
  └── Linked to project record when project is locked

PROJECT OPEN
  └── SOW signed → project_id created in ERP → project record created in CORTEX
  └── Pre-project artifacts migrated/linked to /projects/<project_id>/pre-project/
  └── Active: standups, client calls, sprint planning, milestone reviews
  └── Milestones tracked against SOW baseline

PROJECT CLOSED
  └── Memory preserved — not archived
  └── Client relationship record maintained
  └── Queryable indefinitely
  └── Renewal signal fires as end_date approaches or on new client contact
```

### Calibration Events
When project context shifts (POC → Milestone 1, scope change, timeline rebase):
- PM creates a calibration event with free-text description of what changed
- CORTEX layers this as an immutable overlay — raw history never mutated
- All downstream reporting reads through the calibration lens
- Multiple calibration events allowed — full audit trail
- If calibration was wrong, a correction calibration is created on top

---

## 6. Data Models (Postgres)

```sql
-- ─────────────────────────────────────────
-- PROJECTS
-- ─────────────────────────────────────────

CREATE TABLE clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_name TEXT NOT NULL,
  erp_client_id TEXT UNIQUE,
  industry TEXT,
  relationship_status TEXT CHECK (relationship_status IN ('prospect','active','closed','churned')) DEFAULT 'prospect',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  erp_project_id TEXT UNIQUE NOT NULL,
  client_id UUID REFERENCES clients(id),           -- null for internal projects
  project_name TEXT NOT NULL,
  project_type TEXT CHECK (project_type IN ('client','internal')) NOT NULL,
  pm_employee_id TEXT NOT NULL,                     -- from intranet employees table
  status TEXT CHECK (status IN ('pre_project','active','at_risk','on_hold','closed')) DEFAULT 'pre_project',
  start_date DATE,
  end_date DATE,
  idea_doc_r2_key TEXT,                             -- internal projects: anchor doc
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE project_milestones (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id),
  name TEXT NOT NULL,
  description TEXT,
  original_due_date DATE NOT NULL,                  -- from SOW, never changes
  current_due_date DATE NOT NULL,                   -- updated on drift detection
  status TEXT CHECK (status IN ('not_started','in_progress','at_risk','completed','missed')) DEFAULT 'not_started',
  completed_date DATE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Calibration events — immutable overlays, never delete
CREATE TABLE calibration_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id),
  created_by TEXT NOT NULL,                         -- employee_id
  event_type TEXT NOT NULL,                         -- poc_to_milestone | scope_change | timeline_rebase | other
  description TEXT NOT NULL,
  before_state JSONB,                               -- snapshot of relevant state before
  after_state JSONB,                                -- what PM says it should now be
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- MEETING MEMORY
-- ─────────────────────────────────────────

CREATE TABLE meeting_insights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id),
  meeting_id TEXT UNIQUE NOT NULL,                  -- from IRIS yaml
  meeting_type TEXT NOT NULL,
  meeting_date DATE NOT NULL,
  raw_yaml JSONB NOT NULL,                          -- full parsed yaml, immutable
  enriched_yaml JSONB,                              -- after CORTEX fills blank fields
  summary_embedding VECTOR(1536),                   -- pgvector
  ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- Living project memory — one row per project, updated after every ingestion
CREATE TABLE project_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID UNIQUE REFERENCES projects(id),

  -- Short-term: rolling 3-meeting window
  recent_context JSONB,
  -- {meetings: [{meeting_id, date, type, summary, open_actions, unresolved_blockers, sentiment_score}]}

  -- Long-term: agent-maintained narrative
  relationship_trajectory JSONB,
  -- {trend: "improving|stable|declining", narrative: "...", updated_at: "..."}

  -- Health history
  sentiment_history JSONB,
  -- [{date, score, label, drivers, meeting_id}]

  -- Risk register
  risk_register JSONB,
  -- [{id, description, severity, status, raised_date, resolved_date, source_meeting_id}]

  -- Blocker log
  blocker_log JSONB,
  -- [{id, description, raised_date, resolved_date, resolved_by, days_open}]

  -- Milestone status (live, reconciled against project_milestones table)
  milestone_status JSONB,

  -- IRIS blank fields filled by CORTEX
  previous_meeting_ref JSONB,
  -- {meeting_id, date, key_carryovers: [...]}

  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- HEALTH
-- ─────────────────────────────────────────

CREATE TABLE project_health_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id),
  score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
  band TEXT CHECK (band IN ('green','amber','red')) NOT NULL,
  components JSONB NOT NULL,
  -- {sentiment_penalty, open_risks_penalty, blocker_penalty, milestone_penalty, trajectory_penalty, velocity_penalty}
  computed_after_meeting_id TEXT,
  computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- STAKEHOLDERS
-- ─────────────────────────────────────────

CREATE TABLE client_stakeholders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id UUID REFERENCES clients(id),
  project_id UUID REFERENCES projects(id),          -- null = client-level stakeholder
  name TEXT,
  name_hash TEXT,                                   -- from IRIS until profile is built
  role_at_client TEXT,
  is_champion BOOLEAN DEFAULT FALSE,
  first_seen_date DATE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE stakeholder_sentiment_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stakeholder_id UUID REFERENCES client_stakeholders(id),
  meeting_id TEXT NOT NULL,
  meeting_date DATE NOT NULL,
  sentiment_score NUMERIC(3,2),
  sentiment_label TEXT,
  notes TEXT
);

-- ─────────────────────────────────────────
-- DOCUMENTS
-- ─────────────────────────────────────────

CREATE TABLE project_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id),
  doc_type TEXT CHECK (doc_type IN (
    'sow','solution_architecture','timeline',        -- source documents, manually uploaded
    'proposal','milestone_deliverable',              -- generated
    'status_report','kt_document','onboarding_brief','renewal_proposal','other'
  )) NOT NULL,
  version TEXT NOT NULL DEFAULT 'v1.0',
  status TEXT CHECK (status IN ('uploaded','draft','review','approved','sent','superseded')) DEFAULT 'draft',
  source TEXT CHECK (source IN ('manual_upload','generated')) NOT NULL,
  r2_key TEXT NOT NULL,
  extracted_data JSONB,                             -- structured data pulled from source docs
  generated_at TIMESTAMPTZ DEFAULT NOW(),
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  notes TEXT
);

-- ─────────────────────────────────────────
-- WEEKLY PLANS
-- ─────────────────────────────────────────

CREATE TABLE pm_task_plans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id),
  week_start DATE NOT NULL,
  generated_at TIMESTAMPTZ DEFAULT NOW(),
  plan_yaml TEXT NOT NULL,
  health_score_at_generation INTEGER,
  velocity_data JSONB,                              -- from CELL summary
  sent_to_slack BOOLEAN DEFAULT FALSE,
  pm_acknowledged BOOLEAN DEFAULT FALSE
);

-- ─────────────────────────────────────────
-- AUDIT
-- ─────────────────────────────────────────

CREATE TABLE agent_actions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id),
  action_type TEXT NOT NULL,
  -- ingest_yaml | update_memory | compute_health | generate_doc | send_plan
  -- calibration_event | kt_generated | alert_fired | enriched_yaml_written
  payload JSONB,
  triggered_by TEXT,                                -- r2_event | schedule | slack_command | intranet_api
  status TEXT DEFAULT 'ok',
  error_text TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. R2 Directory Structure

```
erp-agents/                              ← R2 bucket (shared with IRIS and CELL)
│
├── projects/
│   └── <project_id>/
│       ├── pre-project/                 ← POC artifacts, proposals, discovery notes
│       │   ├── poc_transcript_<date>.txt
│       │   ├── proposal_v1.pdf
│       │   └── discovery_notes.md
│       │
│       ├── source-docs/                 ← Manually uploaded by PM/BA
│       │   ├── sow_v1.pdf
│       │   ├── solution_architecture_v1.md
│       │   └── timeline_v1.md
│       │
│       ├── <YYYY-MM-DD>_<meeting_id>/   ← IRIS writes here (existing structure)
│       │   ├── metadata.json
│       │   ├── attendees.json
│       │   ├── transcript.txt
│       │   ├── insights.yaml            ← IRIS output
│       │   └── insights_enriched.yaml  ← CORTEX writes this
│       │
│       └── generated-docs/
│           ├── status_report_2025-W20_v1.0.md
│           ├── milestone_2_deliverable_v1.0.md
│           ├── milestone_2_deliverable_v1.1.md  ← new version, v1.0 → superseded
│           └── kt_document_2025-05-14_v1.0.md
│
├── pre-project/
│   └── <client_id>/                     ← Before project_id exists
│       ├── poc_<date>/
│       └── proposal_<date>/
│
└── templates/
    ├── sow.md
    ├── proposal.md
    ├── milestone_deliverable.md
    ├── status_report.md
    ├── kt_document.md
    ├── onboarding_brief.md
    └── renewal_proposal.md
```

---

## 8. insights.yaml Contract with IRIS

CORTEX fills the two fields IRIS leaves null. After filling, CORTEX writes `insights_enriched.yaml` back to R2.

```yaml
# ── IRIS fills everything above this line ──────────────────────
meeting_id: "mtg_20250514_proj42_standup"
project_id: "PROJ-CRM-0014"
meeting_type: "standup"
meeting_date: "2025-05-14"
summary: "Sprint 3 day 2. Auth module done. Deploy blocked by client env access."
risks:
  - description: "Staging env access delay may push milestone 2"
    severity: "high"
blockers:
  - description: "No staging credentials from client"
    raised_by: "bob"
sentiment:
  score: 0.4
  label: "cautious"
  drivers: ["blocker unresolved", "timeline pressure"]
milestones:
  - name: "Milestone 2 - Auth + API"
    due_date: "2025-05-20"
    status: "at_risk"
previous_meeting_ref: null     # ← CORTEX fills
relationship_trajectory: null  # ← CORTEX fills

# ── CORTEX writes to insights_enriched.yaml ────────────────────
previous_meeting_ref:
  meeting_id: "mtg_20250513_proj42_standup"
  date: "2025-05-13"
  key_carryovers:
    - "Staging credentials still pending (raised 2025-05-12)"
    - "Auth module was 80% complete, now done"

relationship_trajectory:
  trend: "declining"
  narrative: "Client engagement has been cautious over the last 3 standups.
    The staging credential blocker, now in its third day, is creating timeline
    pressure on Milestone 2. Recommend PM direct escalation to client delivery
    manager before EOD today."
```

---

## 9. Agent Architecture

### 9.1 Entry Points

```
┌──────────────────────────────────────────────────┐
│               CORTEX Entry Points                 │
├──────────────────────────────────────────────────┤
│ 1. NERVE Event (R2 upload notification)           │
│    POST /cortex/ingest-nerve                      │
│    Triggered by IRIS after every extraction       │
│                                                   │
│ 2. Document Upload Webhook                        │
│    POST /cortex/document-upload                   │
│    Called by intranet when PM uploads SOW etc.    │
│                                                   │
│ 3. Scheduled Jobs (APScheduler IST)               │
│    Daily  08:00 — health scan, blocker nudges     │
│    Daily  08:00 — cadence monitoring              │
│    Monday 07:30 — weekly PM plan generation       │
│    Weekly Sunday — renewal signal check           │
│                                                   │
│ 4. Intranet Chatbot API                           │
│    POST /cortex/chat                              │
│    Called from intranet project page              │
│                                                   │
│ 5. Slack Commands (capability built, UI deferred) │
│    /cortex-status [project_id]                    │
│    /cortex-doc [doc_type] [project_id]            │
│    /cortex-kt [project_id]                        │
│    /cortex-calibrate [project_id]                 │
│                                                   │
│ 6. ERP Team Change Webhook                        │
│    POST /cortex/team-change                       │
│    Fires KT doc generation on PM reassignment     │
└──────────────────────────────────────────────────┘
```

### 9.2 Processing Pipeline (NERVE → Full Run)

```
IRIS fires iris.extraction.complete
            │
            ▼
[1] INGEST
    Download insights.yaml from R2
    Parse + validate schema
    Upsert meeting_insights row
    Embed summary → pgvector (text-embedding-3-small)

            │
            ▼
[2] MEMORY STITCH
    Load project_memory
    Load last 3 meeting_insights (short-term window)
    Fill previous_meeting_ref
      → find last meeting for project
      → diff open actions and blockers for carryovers
    Update sentiment_history[]
    Merge new risks into risk_register
    Merge new blockers into blocker_log (compute days_open)
    Update milestone_status[]
    Save project_memory

            │
            ▼
[3] NARRATIVE UPDATE (LLM call)
    Input: sentiment_history (last 6), risk_register,
           milestone_status, recent_context
    Output: relationship_trajectory.trend + narrative
    Save to project_memory

            │
            ▼
[4] HEALTH SCORE
    Compute deterministic health score (see §11)
    Insert project_health_scores row
    If score < 60 → flag for PM alert (capability built, delivery deferred)
    If 3 consecutive declining sentiment → flag

            │
            ▼
[5] MILESTONE DRIFT CHECK
    For each open milestone:
      Load CELL weekly summary (velocity)
      Project completion date at current velocity
      If projected_date > current_due_date → update drift flag
      If drift > 3 days → flag

            │
            ▼
[6] ENRICH YAML
    Write insights_enriched.yaml to R2
    (same path + _enriched suffix)

            │
            ▼
[7] CONDITIONAL TRIGGERS
    If meeting_type == client-call OR milestone-review
      → Generate recommended action brief (LLM)
      → Store in project_memory, available via chatbot
    If milestone just moved to completed
      → Auto-draft milestone deliverable doc
    If blocker > 48h unresolved
      → Flag for PM nudge (delivery deferred)
```

---

## 10. Memory System

### 10.1 Short-Term Memory (Rolling Window)

```json
{
  "meetings": [
    {
      "meeting_id": "mtg_20250514_...",
      "date": "2025-05-14",
      "type": "standup",
      "summary": "...",
      "open_actions": ["Follow up on staging credentials"],
      "unresolved_blockers": ["No staging credentials from client"],
      "sentiment_score": 0.4
    },
    { ... },
    { ... }
  ]
}
```

### 10.2 Long-Term Narrative (LLM Prompt)

```
System:
  You are a senior project manager maintaining a living narrative for a client engagement.
  Given sentiment history, risk register, milestone status, and recent summaries, produce:
  1. trend: "improving" | "stable" | "declining"
  2. narrative: 2-3 sentences. Concrete. Reference specific dates and events.
     Written for a PM who will act on it.

User:
  <sentiment_history>[last 6 meetings]</sentiment_history>
  <risk_register>[open risks]</risk_register>
  <milestone_status>[...]</milestone_status>
  <recent_meetings>[last 3 summaries]</recent_meetings>
  <calibration_events>[any active calibrations]</calibration_events>
```

### 10.3 Semantic Memory (pgvector)

Used for two purposes:

**Carryover detection:** Before filling `previous_meeting_ref`, find semantically similar past situations:
```sql
SELECT meeting_id, meeting_date, raw_yaml
FROM meeting_insights
WHERE project_id = $1
ORDER BY summary_embedding <-> $2
LIMIT 5;
```

**Chatbot context retrieval:** When PM asks about a specific topic, retrieve the most relevant past meetings before answering:
```sql
SELECT meeting_id, meeting_date, raw_yaml, meeting_type
FROM meeting_insights
WHERE project_id = $1
ORDER BY summary_embedding <-> $2
LIMIT 8;
```

### 10.4 Calibration Events

Calibration events are first-class records. They never mutate existing data. All reporting and narrative generation passes calibration events as context so CORTEX understands the reframing.

```python
# Before generating any output for a project, always load calibrations
calibrations = await db.fetch("""
    SELECT * FROM calibration_events
    WHERE project_id = $1
    ORDER BY created_at ASC
""", project_id)
# Pass as context to every LLM call for this project
```

---

## 11. Health Score Algorithm

Deterministic, auditable. LLM is never used to produce a number a PM will act on.

```python
def compute_health_score(memory: ProjectMemory, recent_meetings: list, velocity: dict) -> dict:
    score = 100
    components = {}

    # Sentiment (last 3 meetings)
    avg_sentiment = mean([m["sentiment_score"] for m in recent_meetings[-3:]])
    sentiment_penalty = 0
    if avg_sentiment < 0:
        sentiment_penalty = 20
    elif avg_sentiment < 0.3:
        sentiment_penalty = 10
    score -= sentiment_penalty
    components["sentiment_penalty"] = sentiment_penalty

    # Open high-severity risks
    open_high = [r for r in memory.risk_register if r["severity"] == "high" and r["status"] == "open"]
    risk_penalty = len(open_high) * 10
    score -= risk_penalty
    components["open_risks_penalty"] = risk_penalty

    # Unresolved blockers by age
    blocker_penalty = 0
    for b in memory.blocker_log:
        if b["resolved_date"] is None:
            days = (today - b["raised_date"]).days
            if days > 7:
                blocker_penalty += 15
            elif days > 3:
                blocker_penalty += 7
    score -= blocker_penalty
    components["blocker_penalty"] = blocker_penalty

    # Milestones at risk
    at_risk = [m for m in memory.milestone_status if m["status"] == "at_risk"]
    milestone_penalty = len(at_risk) * 8
    score -= milestone_penalty
    components["milestone_penalty"] = milestone_penalty

    # Trajectory
    trajectory_penalty = 10 if memory.relationship_trajectory.get("trend") == "declining" else 0
    score -= trajectory_penalty
    components["trajectory_penalty"] = trajectory_penalty

    # Velocity (from CELL)
    velocity_penalty = 0
    if velocity:
        completion_rate = velocity.get("completion_rate", 1.0)
        if completion_rate < 0.5:
            velocity_penalty = 15
        elif completion_rate < 0.7:
            velocity_penalty = 7
    score -= velocity_penalty
    components["velocity_penalty"] = velocity_penalty

    final = max(0, min(100, score))
    band = "green" if final >= 80 else "amber" if final >= 60 else "red"
    return {"score": final, "band": band, "components": components}
```

---

## 12. CELL → CORTEX Weekly Summary Wire

CORTEX calls CELL every Monday before generating the PM plan:

```http
GET https://cell.internal/cell/summary/{project_id}?week={week_ref}
X-API-Key: <cell-api-key>
```

Response:
```json
{
  "project_id": "PROJ-CRM-0014",
  "week_ref": "2025-W20",
  "tasks_planned": 8,
  "tasks_completed": 5,
  "tasks_carried": 2,
  "tasks_blocked": 1,
  "completion_rate": 0.625,
  "bounty_earned": 12.5,
  "per_intern": [
    {
      "employee_id": "p-arjun-001",
      "name": "Arjun Sharma",
      "tasks_planned": 4,
      "tasks_completed": 3,
      "tasks_carried": 1,
      "tasks_blocked": 0
    }
  ],
  "cumulative_completion_rate": 0.71
}
```

CELL must implement this endpoint. It is the primary data feed for velocity-based health scoring and PM plan generation.

---

## 13. Document Lifecycle

### 13.1 Source Documents (Manually Uploaded)

PM/BA uploads via intranet. Intranet calls `POST /cortex/document-upload` after R2 write.

CORTEX extracts structured data:

**SOW:**
```json
{
  "milestones": [{"name": "...", "due_date": "...", "deliverables": [...]}],
  "payment_terms": "...",
  "scope": ["..."],
  "out_of_scope": ["..."],
  "total_value": "...",
  "duration_weeks": 12
}
```

**Solution Architecture:**
```json
{
  "feature_set": ["..."],
  "tech_stack": {"frontend": "...", "backend": "...", "infra": "..."},
  "integrations": ["..."],
  "assumptions": ["..."],
  "out_of_scope": ["..."]
}
```

**Timeline:**
```json
{
  "milestones": [{"name": "...", "start_date": "...", "end_date": "...", "dependencies": [...]}],
  "buffer_periods": ["..."],
  "critical_path": ["..."]
}
```

### 13.2 Generated Documents

```
Trigger (auto or PM command)
        │
        ▼
Load template from R2 (templates/<type>.md)
Load project_memory + last 5 meeting_insights + extracted SOW data
        │
        ▼
LLM fills template
        │
        ▼
Upload draft to R2: generated-docs/<name>_v1.0.md
Insert project_documents row (status=draft)
        │
        ▼
Slack message to PM: "Draft ready. [View] [Approve] [Request Changes]"
        │
PM approves
        ▼
project_documents.status → approved
Optional: ERP webhook for milestone delivery confirmation
```

### 13.3 Versioning Rule

When a document is regenerated:
- Existing record → `status = superseded`
- New record inserted with version bumped (`v1.0 → v1.1`)
- R2 key includes version in filename
- Both versions always queryable

---

## 14. Weekly PM Plan

Generated every Monday 07:30 IST per active project.

### Plan YAML Structure
```yaml
week_start: "2025-05-19"
project_id: "PROJ-CRM-0014"
health_score: 72
health_band: "amber"
relationship_trajectory: "stable"
velocity_last_week: 0.625

pm_focus_areas:
  - priority: 1
    area: "Unblock staging access"
    context: "Blocker raised 2025-05-14, 5 days unresolved. Milestone 2 at risk (due 2025-05-20)."
    suggested_actions:
      - "Escalate to client delivery manager"
      - "Schedule call if unresolved by EOD Monday"

  - priority: 2
    area: "Milestone 2 review prep"
    context: "Auth module complete. Deploy pending blocker resolution. 6 days to deadline."
    suggested_actions:
      - "Prepare demo script"
      - "Draft milestone deliverable doc"

poc_todos:
  - assignee: "p-arjun-001"
    task: "Confirm staging credentials or escalate"
    due: "2025-05-19"
    priority: "high"
    source_meeting: "mtg_20250514_proj42_standup"

documents_due:
  - type: "milestone_deliverable"
    name: "Milestone 2 - Auth + API"
    due: "2025-05-20"
    status: "not_started"

risks_to_watch:
  - description: "Milestone 2 delay"
    severity: "high"
    days_open: 5
    drift_days: 0
```

POC todos are pushed to CELL via `POST /cell/ingest-tasks` immediately after plan generation.

---

## 15. Intranet Chatbot Interface

### 15.1 Architecture

```
Intranet project page
    │  POST /cortex/chat
    │  Headers: X-Employee-ID, X-Project-ID (from intranet session)
    ▼
CORTEX /chat endpoint
    │
    ├── Resolve employee role from intranet API
    ├── Load project_memory + recent_context
    ├── Retrieve semantically relevant past meetings (pgvector)
    ├── Load calibration events
    ├── Build role-aware system prompt
    └── LLM call → response
```

### 15.2 Chat API

```http
POST /cortex/chat
X-Employee-ID: p-ananya-001
X-Project-ID: PROJ-CRM-0014
Content-Type: application/json

{
  "message": "Are we on track for Milestone 2?",
  "conversation_history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Response:
```json
{
  "response": "...",
  "project_id": "PROJ-CRM-0014",
  "sources": ["mtg_20250514_...", "mtg_20250513_..."],
  "health_score": 72,
  "generated_at": "2025-05-14T09:00:00Z"
}
```

### 15.3 Role-Aware System Prompt

```python
ROLE_SYSTEM_PROMPTS = {
    "pm": """You are CORTEX, a project intelligence assistant for a software consultancy PM.
    The PM needs detailed operational and relational information. Be specific — reference
    dates, people, features, risks. Surface patterns they might have missed. Recommend actions.""",

    "apm": """You are CORTEX. Respond with execution-level detail — tasks, blockers,
    intern performance, velocity. The APM needs to know what's happening on the ground.""",

    "ba": """You are CORTEX. The BA needs commercial intelligence — client champion status,
    sentiment of key stakeholders, discovery insights, expansion signals. Be crisp.""",

    "director": """You are CORTEX. Give high-level business intelligence — project health,
    timeline, cost trajectory, portfolio risks, expansion opportunities. No operational detail.""",

    "default": """You are CORTEX, a project intelligence assistant. Answer accurately
    based on project data."""
}
```

### 15.4 Portfolio Query (Director)

When `X-Project-ID` is absent and role is `director`:
```
"Give me portfolio status"
→ Load all active projects
→ Return RAG summary per project
→ Surface red projects first
```

---

## 16. KT & Onboarding

### KT Document (On PM Change)

Triggered by ERP team-change webhook or Slack command.

```http
POST /cortex/team-change
{
  "project_id": "PROJ-CRM-0014",
  "change_type": "pm_reassignment",
  "outgoing_employee_id": "p-ananya-001",
  "incoming_employee_id": "p-priya-002",
  "effective_date": "2025-05-20"
}
```

CORTEX generates a KT document covering:
- Project background and original goals
- All calibration events (scope changes, rebaselines)
- Current milestone status and drift
- Open risks and blockers
- Client relationship history and stakeholder map
- Key decisions made and why
- Pending deliverables
- Recommended first actions for incoming PM

Delivered to incoming PM via Slack. Stored in R2 and `project_documents`.

### Onboarding Brief (On New POC Added)

Shorter version of KT — "story so far" for a new POC or APM joining mid-project.

---

## 17. FastAPI Service Structure

```
cortex/
├── main.py                        # FastAPI app, scheduler init, lifespan context manager
├── config.py                      # env vars, constants, thresholds
│
├── models/
│   ├── db.py                      # asyncpg models matching §6 schema
│   └── schemas.py                 # Pydantic v2 schemas
│
├── routers/
│   ├── nerve.py                   # POST /cortex/ingest-nerve
│   ├── chat.py                    # POST /cortex/chat (intranet chatbot)
│   ├── documents.py               # POST /cortex/document-upload, doc approval
│   ├── team.py                    # POST /cortex/team-change
│   └── slack.py                   # Slack slash commands + interactive payloads
│
├── services/
│   ├── ingest.py                  # Step 1: yaml download, parse, embed
│   ├── memory.py                  # Step 2: short + long-term memory stitch
│   ├── narrative.py               # Step 3: LLM narrative update
│   ├── health.py                  # Step 4: deterministic health score
│   ├── drift.py                   # Step 5: milestone drift detection
│   ├── enrich.py                  # Step 6: write enriched yaml to R2
│   ├── triggers.py                # Step 7: conditional post-ingest triggers
│   ├── documents.py               # Document lifecycle: extract, generate, version, approve
│   ├── weekly_plan.py             # Monday plan generation + CELL handoff
│   ├── kt.py                      # KT + onboarding brief generation
│   ├── alerts.py                  # Health/blocker/sentiment threshold alerts (deferred delivery)
│   └── cell_client.py             # GET /cell/summary, POST /cell/ingest-tasks
│
├── chat/
│   ├── engine.py                  # Chat orchestration: role resolution, context retrieval, LLM call
│   ├── role_prompts.py            # Role-aware system prompts
│   └── retrieval.py               # pgvector semantic retrieval for chat context
│
├── llm/
│   ├── client.py                  # Anthropic API wrapper
│   └── prompts/
│       ├── narrative.py           # relationship_trajectory prompt
│       ├── doc_extract.py         # structured extraction from uploaded docs
│       ├── doc_generate.py        # document generation prompt
│       ├── weekly_plan.py         # weekly plan generation prompt
│       ├── action_brief.py        # post-meeting action brief prompt
│       └── kt.py                  # KT document generation prompt
│
├── integrations/
│   ├── r2.py                      # R2 download/upload (boto3, same pattern as IRIS/CELL)
│   ├── intranet.py                # Employee/role lookup (same mock IRIS uses)
│   ├── cell_api.py                # CELL summary + ingest-tasks
│   ├── erp.py                     # ERP project/milestone webhook
│   └── slack.py                   # Slack messaging (deferred delivery)
│
└── scheduler.py                   # APScheduler AsyncIOScheduler, IST-anchored
```

---

## 18. Scheduled Jobs

| Time (IST) | Job | What it does |
|---|---|---|
| Mon 07:30 | `weekly_plan_job` | Pull CELL velocity summary, generate PM plan per active project, push POC todos to CELL |
| Daily 08:00 | `health_scan_job` | Re-scan all active projects for blocker age, cadence gaps, milestone drift — flag threshold breaches |
| Daily 08:00 | `cadence_monitor_job` | Check if any project has gone > expected_gap days without a client call — flag |
| Sun 08:00 | `renewal_signal_job` | Check projects where end_date < 6 weeks away — flag, optionally draft renewal proposal |

All jobs: APScheduler `AsyncIOScheduler`, `timezone=Asia/Kolkata`.
Use `lifespan` context manager (not deprecated `@app.on_event`).

---

## 19. Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://cortex_user:cortex_pass@<host>:5432/cortex_db

# R2 (shared bucket with IRIS and CELL)
R2_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=erp-agents

# LLM
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
OPENAI_API_KEY=sk-...              # embeddings only (text-embedding-3-small)

# Slack (delivery deferred — build capability, don't wire delivery yet)
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...

# Internal services
CELL_API_BASE_URL=https://cell.internal
CELL_API_KEY=...
ERP_BASE_URL=https://erp.internal
ERP_API_KEY=...
INTRANET_API_BASE_URL=https://intranet.internal/api
INTRANET_API_KEY=...

# CORTEX service
CORTEX_HOST=0.0.0.0
CORTEX_PORT=8004
CORTEX_API_KEY=...                 # for intranet + ERP to call CORTEX

# Timezone
TZ=Asia/Kolkata

# Health score thresholds
HEALTH_SCORE_RED_THRESHOLD=60
HEALTH_SCORE_AMBER_THRESHOLD=80
BLOCKER_ALERT_DAYS=2
SENTIMENT_DECLINE_WINDOW=3
CADENCE_GAP_DAYS_CLIENT=14        # flag if no client call in 14 days
RENEWAL_SIGNAL_WEEKS=6            # flag when end_date < 6 weeks away
```

---

## 20. Integration Wires Summary

| From | To | Mechanism | Notes |
|---|---|---|---|
| IRIS | CORTEX | `POST /cortex/ingest-nerve` | Same NERVE event shape CELL receives |
| CORTEX | CELL | `GET /cell/summary/{project_id}` | New endpoint CELL must implement |
| CORTEX | CELL | `POST /cell/ingest-tasks` | Already implemented in CELL |
| Intranet | CORTEX | `POST /cortex/document-upload` | On PM file upload |
| Intranet | CORTEX | `POST /cortex/chat` | Project page chatbot |
| Intranet | CORTEX | `POST /cortex/team-change` | On PM/POC reassignment |
| CORTEX | ERP | `PATCH /api/milestones/:id` | On milestone deliverable approved |
| CORTEX | Slack | Slack SDK | Deferred — capability built, delivery not wired |

---

## 21. New Endpoint CELL Must Implement

```http
GET /cell/summary/{project_id}?week={week_ref}
X-API-Key: <cell-api-key>

Response 200:
{
  "project_id": "PROJ-CRM-0014",
  "week_ref": "2025-W20",
  "tasks_planned": 8,
  "tasks_completed": 5,
  "tasks_carried": 2,
  "tasks_blocked": 1,
  "completion_rate": 0.625,
  "bounty_earned": 12.5,
  "per_intern": [...],
  "cumulative_completion_rate": 0.71
}
```

---

## 22. Production Readiness Checklist

### Gaps to resolve before go-live

| # | Issue | Severity | Fix |
|---|---|---|---|
| 1 | CELL `/cell/summary` endpoint does not exist | Critical | CELL team must implement per §21 |
| 2 | Client stakeholder profiles — IRIS hashes external attendees | High | IRIS-side fix needed: once project locked, build stakeholder profiles from attendees.json |
| 3 | Intranet must call `/cortex/document-upload` on file upload | High | Intranet team to add webhook call after R2 write |
| 4 | Intranet must call `/cortex/team-change` on PM reassignment | High | Intranet team to add webhook call |
| 5 | Intranet must pass `X-Employee-ID` in chat requests | High | Intranet session → employee ID resolution |
| 6 | ERP must expose `PATCH /api/milestones/:id` | Medium | For milestone delivery confirmation |
| 7 | Slack delivery wired but not activated | Low | Build capability, activate when UI decided |
| 8 | pgvector extension required | Critical | `CREATE EXTENSION IF NOT EXISTS vector;` on cortex_db |

---

## 23. Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| CORTEX fills `previous_meeting_ref` and `relationship_trajectory`, not IRIS | IRIS is stateless per-meeting. Cross-meeting narrative is CORTEX's sole responsibility. |
| Calibration events as immutable overlays | Prevents data loss from misfire. Full audit trail. Raw history always recoverable. |
| Health score is deterministic, not LLM | Auditable, testable, no hallucination risk on a number PMs act on. LLM reserved for narrative. |
| Role-aware chatbot responses from intranet profile | No self-declaration. Consistent. Prevents role spoofing. |
| Separate `insights_enriched.yaml` rather than overwriting | IRIS output is source of truth. CORTEX enrichment is additive. Any future agent can consume either. |
| CELL weekly summary as velocity input | CORTEX cannot see intern task data directly. Clean API boundary — CELL owns task execution data. |
| Client relationship preserved after project close | Consultancy is building long-term client relationships. Closed ≠ forgotten. |
| Internal projects use idea doc as SOW equivalent | Preserves the same memory and health infrastructure without forcing internal work into a client-project mould. |
| Documents versioned in DB and R2 filename | DB gives queryable history. R2 filename prevents silent overwrites and supports direct human access. |
| Slack delivery capability built but not wired | UI for notifications undecided. Build the intelligence layer now, wire delivery when UI is confirmed. |

---

*CORTEX — IRIS perceives. CELL executes. CORTEX thinks.*
