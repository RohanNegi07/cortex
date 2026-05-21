"""
CORTEX Enrich YAML Service (Step 6)
Persists enriched meeting insights to the database with filled previous_meeting_ref
and relationship_trajectory.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import asyncpg
from cortex.models.db import get_connection, release_connection

log = logging.getLogger("cortex.enrich")

async def write_enriched_yaml(
    project_id: str,
    insight_id: str
) -> Optional[Dict[str, Any]]:
    """
    Step 6: Persist enriched YAML into the database.
    Adds previous_meeting_ref and relationship_trajectory from project_memory.
    """
    try:
        conn = await get_connection()

        # 1. Get the meeting insight
        meeting = await conn.fetchrow(
            "SELECT * FROM meeting_insights WHERE id = $1",
            insight_id
        )
        if not meeting:
            log.error(f"Meeting insight {insight_id} not found")
            return None

        raw_yaml = json.loads(meeting["raw_yaml"])

        # 2. Get project memory
        memory_row = await conn.fetchrow(
            "SELECT * FROM project_memory WHERE project_id = $1",
            project_id
        )
        if not memory_row:
            log.warning(f"No project memory for {project_id}")
            enriched = raw_yaml
        else:
            # Add enriched fields
            enriched = {
                **raw_yaml,
                "previous_meeting_ref": json.loads(memory_row["previous_meeting_ref"] or "{}"),
                "relationship_trajectory": json.loads(memory_row["relationship_trajectory"] or "{}")
            }

        # 3. Get health score for this meeting
        health = await conn.fetchrow(
            """
            SELECT score, band FROM project_health_scores
            WHERE computed_after_meeting_id = $1
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            str(insight_id)
        )
        if health:
            enriched["health_score"] = {
                "score": health["score"],
                "band": health["band"]
            }

        # 4. Persist enriched YAML into the database
        await conn.execute(
            "UPDATE meeting_insights SET enriched_yaml = $1 WHERE id = $2",
            json.dumps(enriched),
            insight_id
        )
        log.info(f"✓ Enriched YAML persisted for {meeting['meeting_id']}")
        return {"status": "ok", "insight_id": insight_id}

    except Exception as e:
        log.error(f"Enrich failed: {e}", exc_info=True)
        return None
    finally:
        if 'conn' in locals():
            await release_connection(conn)
