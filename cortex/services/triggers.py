"""
CORTEX Post-Ingest Triggers (Step 7)
Conditional actions after ingestion:
- Generate action brief for client-call/milestone-review meetings
- Auto-draft milestone deliverable on completion
- Flag blockers > 48h unresolved
- Detect health score changes (Slack notifications disabled)
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from cortex.models.db import get_connection, release_connection

log = logging.getLogger("cortex.triggers")


async def trigger_health_alert_if_changed(
    project_id: str,
    current_score: int,
    current_band: str
) -> bool:
    """
    Check if health score changed from previous.
    If band changed or score_delta > threshold, record that an alert would have been sent.
    """
    try:
        conn = await get_connection()
        try:
            # Get previous health score
            prev_row = await conn.fetchrow(
                """SELECT score, health_band
                   FROM project_health_scores
                   WHERE project_id = $1
                   ORDER BY computed_at DESC
                   OFFSET 1 LIMIT 1""",
                project_id
            )

            if not prev_row:
                return False

            prev_score = prev_row["score"]
            prev_band = prev_row["health_band"]

            band_changed = prev_band != current_band
            score_delta = abs(current_score - prev_score)
            alert_threshold = 10

            if band_changed or score_delta > alert_threshold:
                log.info(
                    f"Health alert would have triggered for {project_id}: "
                    f"{prev_score}/{prev_band} → {current_score}/{current_band}. "
                    "Slack notifications are disabled."
                )
                return False
        finally:
            if conn:
                await release_connection(conn)

    except Exception as e:
        log.error(f"Health alert trigger failed: {e}", exc_info=True)

    return False

async def process_post_ingest_triggers(
    project_id: str,
    insight_id: str
) -> Optional[Dict[str, Any]]:
    """
    Step 7: Process conditional triggers.
    Returns dict with triggered actions.
    """
    try:
        conn = await get_connection()

        # Get the meeting
        meeting = await conn.fetchrow(
            "SELECT * FROM meeting_insights WHERE id = $1",
            insight_id
        )
        if not meeting:
            return None

        raw_yaml = json.loads(meeting["raw_yaml"])
        meeting_type = meeting["meeting_type"]
        triggered = []

        # 1. Action brief for client-call or milestone-review
        if meeting_type in ["client-call", "milestone-review"]:
            # TODO: Implement LLM action brief generation
            triggered.append({
                "trigger": "action_brief",
                "status": "deferred",
                "message": f"Action brief generation for {meeting_type} meeting"
            })

        # 2. Auto-draft milestone deliverable
        milestones = raw_yaml.get("milestones", [])
        for m in milestones:
            if m.get("status") == "completed":
                # TODO: Implement auto-draft
                triggered.append({
                    "trigger": "milestone_deliverable_draft",
                    "milestone": m.get("name"),
                    "status": "deferred"
                })

        # 3. Flag blockers > 48h unresolved
        memory_row = await conn.fetchrow(
            "SELECT blocker_log FROM project_memory WHERE project_id = $1",
            project_id
        )
        if memory_row:
            blocker_log = json.loads(memory_row["blocker_log"] or "[]")
            now = datetime.utcnow()
            for b in blocker_log:
                if not b.get("resolved_date"):
                    raised = datetime.fromisoformat(b["raised_date"])
                    hours_open = (now - raised).total_seconds() / 3600
                    if hours_open > 48:
                        triggered.append({
                            "trigger": "blocker_alert",
                            "blocker": b.get("description"),
                            "hours_open": round(hours_open),
                            "status": "deferred"
                        })

        if triggered:
            log.info(f"✓ {len(triggered)} triggers processed for {project_id}")

        return {"triggers": triggered, "count": len(triggered)}

    except Exception as e:
        log.error(f"Trigger processing failed: {e}", exc_info=True)
        return None
    finally:
        if 'conn' in locals():
            await release_connection(conn)
