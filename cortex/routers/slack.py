"""
Slack Router
Inbound webhooks for Slack notifications:
- Health alerts
- Action briefs
- Weekly summaries
"""

import logging
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from cortex.config import CORTEX_API_KEY
from cortex.models.db import get_connection, release_connection
from cortex.services.slack_notifier import (
    send_health_alert,
    send_action_brief,
    send_weekly_summary
)

log = logging.getLogger("cortex.routers.slack")

router = APIRouter(prefix="/cortex/slack", tags=["slack"])


class HealthAlertPayload(BaseModel):
    project_id: str
    score: int
    band: str
    old_score: int = None
    components: dict = None


class ActionBriefPayload(BaseModel):
    project_id: str
    meeting_id: str
    brief_content: str
    meeting_type: str = "client-call"


class WeeklySummaryPayload(BaseModel):
    project_id: str
    week_ref: str
    completion_rate: float
    risks: list = None
    blockers: list = None
    upcoming_milestones: list = None


@router.post("/health-alert")
async def post_health_alert(
    payload: HealthAlertPayload,
    x_api_key: str = Header(None)
) -> dict:
    """
    Receive health alert and post to Slack.
    Expected payload:
    {
        "project_id": "proj-123",
        "score": 75,
        "band": "amber",
        "old_score": 82,
        "components": {"sentiment": -10, "risks": 5, "blockers": 0}
    }
    """
    # Validate API key
    if CORTEX_API_KEY and x_api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    try:
        success = await send_health_alert(
            project_id=payload.project_id,
            score=payload.score,
            band=payload.band,
            components=payload.components
        )

        if success:
            # Log to agent_actions
            conn = await get_connection()
            try:
                await conn.execute(
                    """INSERT INTO agent_actions
                       (project_id, action_type, payload, triggered_by, status)
                       VALUES ($1, $2, $3, $4, $5)""",
                    payload.project_id,
                    "slack_health_alert",
                    f"score={payload.score}, band={payload.band}",
                    "webhook",
                    "success"
                )
            finally:
                if conn:
                    await release_connection(conn)

            return {
                "status": "ok",
                "project_id": payload.project_id,
                "message": "Health alert posted to Slack"
            }
        else:
            return {
                "status": "error",
                "project_id": payload.project_id,
                "message": "Failed to post health alert"
            }
    except Exception as e:
        log.error(f"Error posting health alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/action-brief")
async def post_action_brief(
    payload: ActionBriefPayload,
    x_api_key: str = Header(None)
) -> dict:
    """
    Receive action brief and post to Slack.
    """
    if CORTEX_API_KEY and x_api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    try:
        success = await send_action_brief(
            project_id=payload.project_id,
            meeting_id=payload.meeting_id,
            brief_content=payload.brief_content,
            meeting_type=payload.meeting_type
        )

        if success:
            conn = await get_connection()
            try:
                await conn.execute(
                    """INSERT INTO agent_actions
                       (project_id, action_type, payload, triggered_by, status)
                       VALUES ($1, $2, $3, $4, $5)""",
                    payload.project_id,
                    "slack_action_brief",
                    f"meeting_type={payload.meeting_type}",
                    "webhook",
                    "success"
                )
            finally:
                if conn:
                    await release_connection(conn)

            return {
                "status": "ok",
                "project_id": payload.project_id,
                "message": "Action brief posted to Slack"
            }
        else:
            return {
                "status": "error",
                "project_id": payload.project_id,
                "message": "Failed to post action brief"
            }
    except Exception as e:
        log.error(f"Error posting action brief: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/weekly-summary")
async def post_weekly_summary(
    payload: WeeklySummaryPayload,
    x_api_key: str = Header(None)
) -> dict:
    """
    Receive weekly summary and post to Slack.
    """
    if CORTEX_API_KEY and x_api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    try:
        summary_dict = {
            "completion_rate": payload.completion_rate,
            "risks": payload.risks or [],
            "blockers": payload.blockers or [],
            "upcoming_milestones": payload.upcoming_milestones or []
        }

        success = await send_weekly_summary(
            project_id=payload.project_id,
            week_ref=payload.week_ref,
            summary=summary_dict
        )

        if success:
            conn = await get_connection()
            try:
                await conn.execute(
                    """INSERT INTO agent_actions
                       (project_id, action_type, payload, triggered_by, status)
                       VALUES ($1, $2, $3, $4, $5)""",
                    payload.project_id,
                    "slack_weekly_summary",
                    f"week={payload.week_ref}, completion={payload.completion_rate}",
                    "webhook",
                    "success"
                )
            finally:
                if conn:
                    await release_connection(conn)

            return {
                "status": "ok",
                "project_id": payload.project_id,
                "week_ref": payload.week_ref,
                "message": "Weekly summary posted to Slack"
            }
        else:
            return {
                "status": "error",
                "project_id": payload.project_id,
                "message": "Failed to post weekly summary"
            }
    except Exception as e:
        log.error(f"Error posting weekly summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
