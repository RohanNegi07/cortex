"""
CELL Integration Client
Interfaces with CELL Agent for velocity tracking and task management.
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx

from cortex.config import CELL_API_BASE_URL, CELL_API_KEY
from cortex.models.db import get_connection, release_connection

log = logging.getLogger("cortex.cell_api")

# In-memory cache for velocity summaries (1 hour TTL)
VELOCITY_CACHE: Dict[str, tuple] = {}
CACHE_TTL_MINUTES = 60


async def get_velocity_summary(
    project_id: str,
    week_ref: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch weekly velocity summary from CELL.
    Format: "2026-W20"
    Cached for 1 hour (velocity doesn't change mid-week).
    """
    cache_key = f"{project_id}:{week_ref}"

    # Check cache
    if cache_key in VELOCITY_CACHE:
        cached_data, cached_at = VELOCITY_CACHE[cache_key]
        if datetime.utcnow() - cached_at < timedelta(minutes=CACHE_TTL_MINUTES):
            log.debug(f"Velocity summary for {cache_key} loaded from cache")
            return cached_data

    # Fetch from CELL
    try:
        url = f"{CELL_API_BASE_URL}/cell/summary/{project_id}"
        params = {"week": week_ref}
        headers = {"X-API-Key": CELL_API_KEY} if CELL_API_KEY else {}

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()
            VELOCITY_CACHE[cache_key] = (data, datetime.utcnow())
            log.info(f"Fetched velocity summary for {project_id}/{week_ref}")
            return data

    except httpx.HTTPError as e:
        log.error(f"CELL API error fetching velocity: {e}")
        return None
    except Exception as e:
        log.error(f"Failed to get velocity summary: {e}")
        return None


async def push_tasks_to_cell(
    project_id: str,
    tasks: List[Dict[str, Any]],
    external_project_id: Optional[str] = None
) -> bool:
    """
    Push POC todos/tasks to CELL for tracking.
    Endpoint: POST /cell/ingest-tasks
    """
    try:
        external_id = external_project_id or project_id
        url = f"{CELL_API_BASE_URL}/cell/ingest-tasks"
        headers = {"X-API-Key": CELL_API_KEY} if CELL_API_KEY else {}

        payload = {
            "project_id": external_id,
            "tasks": tasks,
            "source": "cortex",
            "pushed_at": datetime.utcnow().isoformat()
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            log.info(f"Pushed {len(tasks)} tasks to CELL for {project_id}")

            # Log to agent_actions
            conn = await get_connection()
            try:
                await conn.execute(
                    """INSERT INTO agent_actions
                       (project_id, action_type, payload, triggered_by, status)
                       VALUES ($1, $2, $3, $4, $5)""",
                    project_id,
                    "cell_task_push",
                    f"tasks_count={len(tasks)}",
                    "weekly_plan",
                    "success"
                )
            except Exception as e:
                log.warning(f"Could not log cell_task_push: {e}")
            finally:
                if conn:
                    await release_connection(conn)

            return True

    except httpx.HTTPError as e:
        log.error(f"CELL API error pushing tasks: {e}")
        return False
    except Exception as e:
        log.error(f"Failed to push tasks to CELL: {e}")
        return False


async def clear_velocity_cache(project_id: Optional[str] = None):
    """Clear velocity cache (all or specific project)"""
    if project_id:
        keys_to_delete = [k for k in VELOCITY_CACHE.keys() if k.startswith(project_id)]
        for k in keys_to_delete:
            del VELOCITY_CACHE[k]
        log.info(f"Cleared velocity cache for {project_id}")
    else:
        VELOCITY_CACHE.clear()
        log.info("Cleared all velocity cache")
