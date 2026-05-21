"""Project retrieval utilities for chat context."""

import json
import logging
from typing import Optional, Dict, Any

from cortex.models.db import get_connection, release_connection

log = logging.getLogger("cortex.chat.retrieval")


async def get_project_context(project_id: str) -> Dict[str, Any]:
    connection = await get_connection()
    try:
        project = await connection.fetchrow(
            "SELECT id, project_name FROM projects WHERE erp_project_id = $1 OR id::text = $1",
            project_id
        )
        if not project:
            return {}

        memory = await connection.fetchrow(
            "SELECT risk_register, milestone_status FROM project_memory WHERE project_id = $1",
            project["id"]
        )

        health = await connection.fetchrow(
            "SELECT score, band FROM project_health_scores WHERE project_id = $1 ORDER BY computed_at DESC LIMIT 1",
            project["id"]
        )

        return {
            "project_name": project.get("project_name"),
            "current_phase": None,
            "health_score": health.get("score") if health else None,
            "health_band": health.get("band") if health else None,
            "risk_register": json.loads(memory["risk_register"]) if memory and memory["risk_register"] else [],
            "milestone_status": json.loads(memory["milestone_status"]) if memory and memory["milestone_status"] else []
        }
    except Exception as e:
        log.error(f"Error loading project context for {project_id}: {e}")
        return {}
    finally:
        await release_connection(connection)
