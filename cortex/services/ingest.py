"""
CORTEX Ingest Service (Step 1)
Accepts direct Nerve insights payloads, parses, validates, embeds, and stores in DB.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, date
import asyncpg
from cortex.models.db import (
    get_connection,
    insert_health_score,
    release_connection,
    normalize_project_id,
)
from cortex.models.schemas import InsightsYAML
from cortex.config import OPENAI_API_KEY, EMBEDDING_MODEL

log = logging.getLogger("cortex.ingest")

async def ingest_meeting_insights(
    project_id: str,
    meeting_id: str,
    insights_data: Optional[Dict[str, Any]] = None,
    meeting_artifacts: Optional[Dict[str, Any]] = None,
    meeting_date: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """
    Step 1: Parse, validate, embed and store meeting insights.
    Accepts direct NERVE payloads for insights and artifacts.
    Returns: insight record with id, or None on failure.
    """
    try:
        conn = await get_connection()

        # Normalize the project ID to the internal UUID.
        normalized_project_id = await normalize_project_id(project_id)
        if not normalized_project_id:
            log.error(f"Project {project_id} not found")
            return None
        project_id = normalized_project_id

        # 1. Check if already ingested (duplicate prevention)
        existing = await conn.fetchrow(
            "SELECT id FROM meeting_insights WHERE meeting_id = $1",
            meeting_id
        )
        if existing:
            log.info(f"Meeting {meeting_id} already ingested. Skipping.")
            return {"id": str(existing["id"]), "action": "skipped"}

        # 2. Use direct NERVE insights payload;
        if insights_data is None:
            if meeting_artifacts is not None:
                insights_data = {
                    "meeting_id": meeting_id,
                    "project_id": project_id,
                    "meeting_type": "other",
                    "meeting_date": meeting_date or date.today(),
                    "summary": meeting_artifacts.get("summary", "Nerve-provided artifact payload"),
                    "meeting_artifacts": meeting_artifacts
                }
            else:
                log.error(f"No insights payload or artifacts provided for {meeting_id}")
                return None
        elif meeting_artifacts is not None:
            insights_data["meeting_artifacts"] = meeting_artifacts

        # 3. Parse and validate
        try:
            meeting_yaml = InsightsYAML(**insights_data)
        except Exception as e:
            log.error(f"Invalid insights.yaml schema for {meeting_id}: {e}")
            return None

        # 4. Generate embedding for summary (for semantic retrieval)
        embedding = await _embed_text(meeting_yaml.summary)
        if not embedding:
            log.warning(f"Failed to generate embedding for {meeting_id}. Continuing without embedding.")

        # 5. Upsert meeting_insights row
        if embedding is not None and await _table_has_column(conn, "meeting_insights", "summary_embedding"):
            insight_id = await conn.fetchval(
                """
                INSERT INTO meeting_insights (
                    project_id, meeting_id, meeting_type, meeting_date, raw_yaml, summary_embedding
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                project_id,
                meeting_id,
                meeting_yaml.meeting_type.value,
                meeting_yaml.meeting_date,
                json.dumps(insights_data),
                embedding
            )
        else:
            insight_id = await conn.fetchval(
                """
                INSERT INTO meeting_insights (
                    project_id, meeting_id, meeting_type, meeting_date, raw_yaml
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                project_id,
                meeting_id,
                meeting_yaml.meeting_type.value,
                meeting_yaml.meeting_date,
                json.dumps(insights_data)
            )

        log.info(f"✓ Ingested meeting {meeting_id} → insight {insight_id}")

        # 6. Log action in agent_actions
        await conn.execute(
            """
            INSERT INTO agent_actions (project_id, action_type, payload, triggered_by, status)
            VALUES ($1, $2, $3, $4, $5)
            """,
            project_id,
            "ingest_yaml",
            json.dumps({"meeting_id": meeting_id, "insight_id": str(insight_id)}),
            "nerve_webhook",
            "ok"
        )

        return {
            "id": str(insight_id),
            "meeting_id": meeting_id,
            "action": "created",
            "has_embedding": embedding is not None
        }

    except Exception as e:
        log.error(f"Ingest failed for {meeting_id}: {e}")
        return None
    finally:
        if 'conn' in locals():
            await release_connection(conn)

async def _embed_text(text: str) -> Optional[list]:
    """
    Generate embedding for text using OpenAI text-embedding-3-small.
    Returns: list of 1536 floats, or None on failure.
    """
    try:
        if not OPENAI_API_KEY:
            log.warning("OPENAI_API_KEY not configured. Skipping embedding.")
            return None

        from openai import AsyncOpenAI 
        client = AsyncOpenAI (api_key=OPENAI_API_KEY)

        response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return response.data[0].embedding
    except Exception as e:
        log.error(f"Embedding generation failed: {e}")
        return None

async def _table_has_column(conn: asyncpg.Connection, table_name: str, column_name: str) -> bool:
    """Return True if the given table contains the specified column."""
    try:
        result = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = $1 AND column_name = $2
            )
            """,
            table_name,
            column_name
        )
        return bool(result)
    except Exception as e:
        log.warning(f"Could not check table column {table_name}.{column_name}: {e}")
        return False
