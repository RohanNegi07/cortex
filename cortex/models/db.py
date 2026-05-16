"""
Database initialization, connection management, and async queries using asyncpg
"""

import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import json
from cortex.config import DATABASE_URL, DATABASE_POOL_SIZE, DATABASE_MAX_OVERFLOW

# Global connection pool
_pool: Optional[asyncpg.Pool] = None

# ─────────────────────────────────────────────────────────────────────────────
# CONNECTION POOL MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

async def init_db():
    """Initialize the database connection pool"""
    global _pool
    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=DATABASE_POOL_SIZE,
            command_timeout=60,
        )
        print("[OK] Database pool initialized")
        return True
    except Exception as e:
        print(f"[WARN] Database connection failed: {e}")
        print("")
        print("Troubleshooting:")
        print("1. Check Postgres is running: docker ps | grep cortex-db")
        print("2. Start Docker container: docker start cortex-db")
        print("3. Verify DATABASE_URL in .env")
        print("")
        return False

async def close_db():
    """Close the database connection pool"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("[OK] Database pool closed")

async def get_connection():
    """Get a connection from the pool"""
    if not _pool:
        raise RuntimeError("Database pool not initialized. Call init_db() first.")
    return await _pool.acquire()

async def release_connection(conn):
    """Release a connection back to the pool."""
    if _pool is not None and conn is not None:
        try:
            await _pool.release(conn)
        except Exception:
            pass  # already released or pool closed — safe to ignore

async def normalize_project_id(project_id: str) -> Optional[str]:
    """Normalize an incoming project identifier to the internal project UUID."""
    conn = await get_connection()
    try:
        row = await conn.fetchrow("SELECT id FROM projects WHERE id = $1", project_id)
        if row:
            return str(row["id"])
        row = await conn.fetchrow("SELECT id FROM projects WHERE erp_project_id = $1", project_id)
        return str(row["id"]) if row else None
    finally:
        await release_connection(conn)

# ─────────────────────────────────────────────────────────────────────────────
# QUERIES: PROJECTS
# ─────────────────────────────────────────────────────────────────────────────

async def create_or_get_project(
    erp_project_id: str,
    project_name: str,
    project_type: str,
    client_id: Optional[str] = None,
    pm_employee_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Create or retrieve a project"""
    conn = await get_connection()
    try:
        # Try to get existing
        row = await conn.fetchrow(
            "SELECT id FROM projects WHERE erp_project_id = $1",
            erp_project_id
        )
        if row:
            return {"id": str(row["id"]), "created": False}

        # Create new
        project_id = await conn.fetchval(
            """
            INSERT INTO projects (
                erp_project_id, client_id, project_name, project_type,
                pm_employee_id, start_date, end_date, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'active')
            RETURNING id
            """,
            erp_project_id, client_id, project_name, project_type,
            pm_employee_id, start_date, end_date
        )
        return {"id": str(project_id), "created": True}
    finally:
        await release_connection(conn)

async def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a project"""
    conn = await get_connection()
    try:
        row = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        return dict(row) if row else None
    finally:
        await release_connection(conn)

# ─────────────────────────────────────────────────────────────────────────────
# QUERIES: MEETING INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────

async def ingest_meeting_insights(
    project_id: str,
    meeting_id: str,
    meeting_type: str,
    meeting_date: date,
    raw_yaml: Dict[str, Any],
) -> Dict[str, Any]:
    """Ingest a meeting from IRIS"""
    conn = await get_connection()
    try:
        # Upsert: if meeting_id exists, skip (IRIS is source of truth)
        row = await conn.fetchrow(
            "SELECT id FROM meeting_insights WHERE meeting_id = $1",
            meeting_id
        )
        if row:
            return {"id": str(row["id"]), "inserted": False, "action": "skipped"}

        insight_id = await conn.fetchval(
            """
            INSERT INTO meeting_insights (
                project_id, meeting_id, meeting_type, meeting_date, raw_yaml
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            project_id, meeting_id, meeting_type, meeting_date,
            json.dumps(raw_yaml)
        )
        return {"id": str(insight_id), "inserted": True, "action": "created"}
    finally:
        await _pool.release(conn)

async def get_meeting_insights(project_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent meetings for a project"""
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT * FROM meeting_insights
            WHERE project_id = $1
            ORDER BY meeting_date DESC
            LIMIT $2
            """,
            project_id, limit
        )
        return [dict(row) for row in rows]
    finally:
        await _pool.release(conn)

# ─────────────────────────────────────────────────────────────────────────────
# QUERIES: HEALTH SCORES
# ─────────────────────────────────────────────────────────────────────────────

async def insert_health_score(
    project_id: str,
    score: int,
    band: str,
    components: Dict[str, int],
    computed_after_meeting_id: Optional[str] = None,
) -> str:
    """Insert a health score record"""
    conn = await get_connection()
    try:
        score_id = await conn.fetchval(
            """
            INSERT INTO project_health_scores (
                project_id, score, band, components, computed_after_meeting_id
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            project_id, score, band, json.dumps(components), computed_after_meeting_id
        )
        return str(score_id)
    finally:
        await _pool.release(conn)

async def get_latest_health_score(project_id: str) -> Optional[Dict[str, Any]]:
    """Get the most recent health score for a project"""
    conn = await get_connection()
    try:
        row = await conn.fetchrow(
            """
            SELECT * FROM project_health_scores
            WHERE project_id = $1
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            project_id
        )
        return dict(row) if row else None
    finally:
        await _pool.release(conn)

# ─────────────────────────────────────────────────────────────────────────────
# QUERIES: PROJECT MEMORY
# ─────────────────────────────────────────────────────────────────────────────

async def get_or_create_project_memory(project_id: str) -> Dict[str, Any]:
    """Get or create project memory record"""
    conn = await get_connection()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM project_memory WHERE project_id = $1",
            project_id
        )
        if row:
            return dict(row)

        # Create new
        memory_id = await conn.fetchval(
            """
            INSERT INTO project_memory (project_id, recent_context, updated_at)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            project_id, json.dumps({"meetings": []}), datetime.utcnow()
        )
        return {
            "id": memory_id,
            "project_id": project_id,
            "recent_context": {"meetings": []},
        }
    finally:
        await _pool.release(conn)

async def update_project_memory(
    project_id: str,
    memory_data: Dict[str, Any]
) -> bool:
    """Update project memory"""
    conn = await get_connection()
    try:
        await conn.execute(
            """
            UPDATE project_memory
            SET recent_context = $1,
                relationship_trajectory = $2,
                sentiment_history = $3,
                risk_register = $4,
                blocker_log = $5,
                updated_at = $6
            WHERE project_id = $7
            """,
            json.dumps(memory_data.get("recent_context", {})),
            json.dumps(memory_data.get("relationship_trajectory", {})),
            json.dumps(memory_data.get("sentiment_history", [])),
            json.dumps(memory_data.get("risk_register", [])),
            json.dumps(memory_data.get("blocker_log", [])),
            datetime.utcnow(),
            project_id
        )
        return True
    finally:
        await _pool.release(conn)

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────────────────────────────────
-- CLIENTS
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_name TEXT NOT NULL,
    erp_client_id TEXT UNIQUE,
    industry TEXT,
    relationship_status TEXT CHECK (relationship_status IN ('prospect','active','closed','churned')) DEFAULT 'prospect',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- PROJECTS
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    erp_project_id TEXT UNIQUE NOT NULL,
    client_id UUID REFERENCES clients(id),
    project_name TEXT NOT NULL,
    project_type TEXT CHECK (project_type IN ('client','internal')) NOT NULL,
    pm_employee_id TEXT NOT NULL,
    status TEXT CHECK (status IN ('pre_project','active','at_risk','on_hold','closed')) DEFAULT 'pre_project',
    start_date DATE,
    end_date DATE,
    idea_doc_r2_key TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- PROJECT MILESTONES
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS project_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    description TEXT,
    original_due_date DATE NOT NULL,
    current_due_date DATE NOT NULL,
    status TEXT CHECK (status IN ('not_started','in_progress','at_risk','completed','missed')) DEFAULT 'not_started',
    completed_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, name)
);

-- ─────────────────────────────────────────────────────────────────────────
-- CALIBRATION EVENTS
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS calibration_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    created_by TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    before_state JSONB,
    after_state JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- MEETING INSIGHTS (FROM IRIS)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meeting_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    meeting_id TEXT UNIQUE NOT NULL,
    meeting_type TEXT NOT NULL,
    meeting_date DATE NOT NULL,
    raw_yaml JSONB NOT NULL,
    enriched_yaml JSONB,
    summary_embedding vector(1536),
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- PROJECT MEMORY (STITCHED NARRATIVE)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS project_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID UNIQUE NOT NULL REFERENCES projects(id),
    recent_context JSONB,
    relationship_trajectory JSONB,
    sentiment_history JSONB,
    risk_register JSONB,
    blocker_log JSONB,
    milestone_status JSONB,
    previous_meeting_ref JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- PROJECT HEALTH SCORES
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS project_health_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    band TEXT CHECK (band IN ('green','amber','red')) NOT NULL,
    components JSONB NOT NULL,
    computed_after_meeting_id TEXT,
    computed_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- CLIENT STAKEHOLDERS
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS client_stakeholders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES clients(id),
    project_id UUID REFERENCES projects(id),
    name TEXT,
    name_hash TEXT,
    role_at_client TEXT,
    is_champion BOOLEAN DEFAULT FALSE,
    first_seen_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- STAKEHOLDER SENTIMENT LOG
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stakeholder_sentiment_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stakeholder_id UUID NOT NULL REFERENCES client_stakeholders(id),
    meeting_id TEXT NOT NULL,
    meeting_date DATE NOT NULL,
    sentiment_score NUMERIC(3,2),
    sentiment_label TEXT,
    notes TEXT
);

-- ─────────────────────────────────────────────────────────────────────────
-- PROJECT DOCUMENTS
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS project_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    doc_type TEXT NOT NULL CHECK (doc_type IN (
        'sow','solution_architecture','timeline',
        'proposal','milestone_deliverable',
        'status_report','kt_document','onboarding_brief','renewal_proposal','other'
    )),
    version TEXT NOT NULL DEFAULT 'v1.0',
    status TEXT CHECK (status IN ('uploaded','draft','review','approved','sent','superseded')) DEFAULT 'draft',
    source TEXT CHECK (source IN ('manual_upload','generated')) NOT NULL,
    r2_key TEXT NOT NULL,
    extracted_data JSONB,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    notes TEXT
);

-- ─────────────────────────────────────────────────────────────────────────
-- PM TASK PLANS (WEEKLY)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pm_task_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    week_start DATE NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    plan_yaml TEXT NOT NULL,
    health_score_at_generation INTEGER,
    velocity_data JSONB,
    sent_to_slack BOOLEAN DEFAULT FALSE,
    pm_acknowledged BOOLEAN DEFAULT FALSE
);

-- ─────────────────────────────────────────────────────────────────────────
-- AGENT ACTIONS (AUDIT LOG)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    action_type TEXT NOT NULL,
    payload JSONB,
    triggered_by TEXT,
    status TEXT DEFAULT 'ok',
    error_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────
-- INDEXES
-- ─────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_projects_erp_id ON projects(erp_project_id);
CREATE INDEX IF NOT EXISTS idx_projects_client_id ON projects(client_id);
CREATE INDEX IF NOT EXISTS idx_projects_pm_employee_id ON projects(pm_employee_id);
CREATE INDEX IF NOT EXISTS idx_meeting_insights_project ON meeting_insights(project_id);
CREATE INDEX IF NOT EXISTS idx_meeting_insights_date ON meeting_insights(meeting_date);
CREATE INDEX IF NOT EXISTS idx_meeting_insights_embedding ON meeting_insights USING ivfflat (summary_embedding vector_cosine_ops) WITH (lists=100);
CREATE INDEX IF NOT EXISTS idx_health_scores_project ON project_health_scores(project_id);
CREATE INDEX IF NOT EXISTS idx_health_scores_computed_at ON project_health_scores(computed_at);
CREATE INDEX IF NOT EXISTS idx_project_milestones_project ON project_milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_calibration_events_project ON calibration_events(project_id);
CREATE INDEX IF NOT EXISTS idx_project_documents_project ON project_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_pm_task_plans_project ON pm_task_plans(project_id);
CREATE INDEX IF NOT EXISTS idx_pm_task_plans_week_start ON pm_task_plans(week_start);
CREATE INDEX IF NOT EXISTS idx_agent_actions_project ON agent_actions(project_id);
CREATE INDEX IF NOT EXISTS idx_stakeholder_sentiment_log_stakeholder ON stakeholder_sentiment_log(stakeholder_id);
"""

async def init_schema():
    """Initialize database schema"""
    if not _pool:
        print("[WARN] No database connection. Skipping schema init.")
        return True

    conn = await _pool.acquire()
    try:
        # Try pgvector — if not available, strip the vector column and index
        pgvector_ok = False
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            pgvector_ok = True
        except Exception as e:
            print(f"[WARN] pgvector not available: {e}")
            print("[INFO] Continuing without vector search — embeddings will be disabled.")

        # Build schema SQL — strip vector parts if pgvector not installed
        schema_sql = SCHEMA_SQL
        if not pgvector_ok:
            # Remove the vector column and ivfflat index so schema still creates cleanly
            schema_sql = "\n".join(
                line for line in schema_sql.splitlines()
                if "vector" not in line.lower() and "ivfflat" not in line.lower()
            )

        await conn.execute(schema_sql)

        # Deduplicate existing project milestone rows and enforce one milestone name per project
        await conn.execute("""
            DELETE FROM project_milestones a
            USING project_milestones b
            WHERE a.project_id = b.project_id
              AND a.name = b.name
              AND a.id > b.id;
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_milestones_project_name
            ON project_milestones(project_id, name);
        """)

        # Ensure project_memory schema upgrades for older databases
        await conn.execute("""
            ALTER TABLE project_memory
                ADD COLUMN IF NOT EXISTS recent_context JSONB,
                ADD COLUMN IF NOT EXISTS relationship_trajectory JSONB,
                ADD COLUMN IF NOT EXISTS sentiment_history JSONB,
                ADD COLUMN IF NOT EXISTS risk_register JSONB,
                ADD COLUMN IF NOT EXISTS blocker_log JSONB,
                ADD COLUMN IF NOT EXISTS milestone_status JSONB,
                ADD COLUMN IF NOT EXISTS previous_meeting_ref JSONB;
        """)

        print("[OK] Database schema initialized")
        return True
    except Exception as e:
        print(f"[WARN] Schema init failed: {e}")
        print("Continuing in stub mode...")
        return True
    finally:
        await _pool.release(conn)