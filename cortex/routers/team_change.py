"""
Team Change Router
Handles PM/POC reassignment webhooks.
Triggers KT document generation.
"""

import logging
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from datetime import datetime

from cortex.config import CORTEX_API_KEY
from cortex.models.db import get_connection, release_connection, normalize_project_id
from cortex.services.kt import generate_kt_document

log = logging.getLogger("cortex.routers.team_change")

router = APIRouter(prefix="/cortex/team", tags=["team"])


class TeamChangePayload(BaseModel):
    project_id: str
    change_type: str  # "pm_reassignment", "poc_added", "poc_removed"
    outgoing_employee_id: str
    incoming_employee_id: str
    effective_date: str


@router.post("/change")
async def post_team_change(
    payload: TeamChangePayload,
    x_api_key: str = Header(None)
) -> dict:
    """
    Handle PM/POC team changes.
    Triggers KT document generation.

    Expected payload:
    {
        "project_id": "proj-123",
        "change_type": "pm_reassignment",
        "outgoing_employee_id": "p-ananya-001",
        "incoming_employee_id": "p-priya-002",
        "effective_date": "2026-05-20"
    }
    """
    # Validate API key
    if CORTEX_API_KEY and x_api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    try:
        log.info(f"Team change webhook received for {payload.project_id}")

        # Validate project exists and normalize external project identifier
        internal_project_id = await normalize_project_id(payload.project_id)
        if not internal_project_id:
            raise HTTPException(status_code=404, detail=f"Project {payload.project_id} not found")

        # Generate KT document if PM reassignment
        kt_result = None
        if payload.change_type == "pm_reassignment":
            kt_result = await generate_kt_document(
                project_id=internal_project_id,
                outgoing_employee_id=payload.outgoing_employee_id,
                incoming_employee_id=payload.incoming_employee_id,
                effective_date=payload.effective_date
            )

            if not kt_result:
                log.warning(f"KT document generation failed for {payload.project_id}")
                return {
                    "status": "error",
                    "project_id": payload.project_id,
                    "message": "Failed to generate KT document"
                }

        # Log team change
        conn = await get_connection()
        try:
            await conn.execute(
                """INSERT INTO agent_actions
                   (project_id, action_type, payload, triggered_by, status)
                   VALUES ($1, $2, $3, $4, $5)""",
                internal_project_id,
                f"team_change_{payload.change_type}",
                f"outgoing={payload.outgoing_employee_id}, incoming={payload.incoming_employee_id}, effective={payload.effective_date}",
                "webhook",
                "success"
            )
        finally:
            if conn:
                await release_connection(conn)

        response = {
            "status": "ok",
            "project_id": payload.project_id,
            "change_type": payload.change_type,
            "message": f"Team change processed for {payload.project_id}"
        }

        if kt_result:
            response["kt_document"] = {
                "document_id": kt_result.get("document_id"),
                "r2_url": kt_result.get("r2_url")
            }

        return response

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error processing team change: {e}")
        raise HTTPException(status_code=500, detail=str(e))
