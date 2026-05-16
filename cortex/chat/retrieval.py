"""Project retrieval utilities for chat context."""

import logging
from typing import Optional, Dict, Any

from cortex.models.db import get_connection, release_connection

log = logging.getLogger("cortex.chat.retrieval")


async def get_project_context(project_id: str) -> Dict[str, Any]:
    connection = await get_connection()
    try:
        query = """
            SELECT project_name, current_phase, health_score, risk_register, milestone_status
            FROM projects WHERE project_id = $1
        """
        result = await connection.fetchrow(query, project_id)
        if not result:
            return {}

        return {
            "project_name": result.get("project_name"),
            "current_phase": result.get("current_phase"),
            "health_score": result.get("health_score"),
            "risk_register": result.get("risk_register") or [],
            "milestone_status": result.get("milestone_status") or []
        }
    except Exception as e:
        log.error(f"Error loading project context for {project_id}: {e}")
        return {}
    finally:
        await release_connection(connection)
