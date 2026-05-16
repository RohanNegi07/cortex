"""
Calibration events router
"""
from fastapi import APIRouter, Header, HTTPException
import logging
from pydantic import BaseModel
import json
from typing import Optional, Dict, Any
from cortex.models.db import get_connection, release_connection, normalize_project_id
from cortex.config import CORTEX_API_KEY

log = logging.getLogger("cortex.calibrate")

router = APIRouter(prefix="/cortex", tags=["CALIBRATE"])


class CalibratePayload(BaseModel):
    project_id: str
    event_type: str
    description: str
    created_by: str
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None


@router.post("/calibrate")
async def calibrate(payload: CalibratePayload, x_api_key: Optional[str] = Header(None)):
    """Record a calibration event for a project (manual re-baseline).

    Validates API key when configured and inserts a `calibration_events` row.
    """
    if CORTEX_API_KEY and x_api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

    # Normalize project id
    internal_project_id = await normalize_project_id(payload.project_id)
    if not internal_project_id:
        raise HTTPException(status_code=404, detail="Project not found")

    conn = await get_connection()
    try:
        event_id = await conn.fetchval(
            """
            INSERT INTO calibration_events (
                project_id, created_by, event_type, description, before_state, after_state, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
            RETURNING id
            """,
            internal_project_id,
            payload.created_by,
            payload.event_type,
            payload.description,
            json.dumps(payload.before_state) if payload.before_state is not None else None,
            json.dumps(payload.after_state) if payload.after_state is not None else None,
        )
        log.info(f"Calibration event recorded: {event_id} for project {internal_project_id}")
        return {"status": "ok", "event_id": str(event_id)}
    except Exception as e:
        log.error(f"Calibration insert error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await release_connection(conn)
