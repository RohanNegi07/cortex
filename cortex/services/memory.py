"""
CORTEX Memory Stitch Service (Step 2)
Loads project memory, recent meetings, fills previous_meeting_ref,
updates sentiment history, merges risks, ages blockers.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, date, timedelta
import asyncpg
from cortex.models.db import get_connection, release_connection

log = logging.getLogger("cortex.memory")

async def stitch_meeting_memory(
    project_id: str,
    insight_id: str
) -> Optional[Dict[str, Any]]:
    """
    Step 2: Stitch cross-meeting memory.
    - Load project_memory
    - Load last 3 meetings (short-term window)
    - Fill previous_meeting_ref by finding last meeting
    - Update sentiment_history
    - Merge risks into risk_register
    - Age blockers in blocker_log
    - Update milestone_status
    """
    try:
        conn = await get_connection()

        # 1. Get the newly ingested meeting
        meeting = await conn.fetchrow(
            "SELECT * FROM meeting_insights WHERE id = $1",
            insight_id
        )
        if not meeting:
            log.error(f"Meeting insight {insight_id} not found")
            return None

        raw_yaml = json.loads(meeting["raw_yaml"])

        # 2. Get or create project_memory
        memory_row = await conn.fetchrow(
            "SELECT * FROM project_memory WHERE project_id = $1",
            project_id
        )

        if memory_row:
            memory = {
                "recent_context": json.loads(memory_row["recent_context"] or "{}"),
                "relationship_trajectory": json.loads(memory_row["relationship_trajectory"] or "{}"),
                "sentiment_history": json.loads(memory_row["sentiment_history"] or "[]"),
                "risk_register": json.loads(memory_row["risk_register"] or "[]"),
                "blocker_log": json.loads(memory_row["blocker_log"] or "[]"),
                "milestone_status": json.loads(memory_row["milestone_status"] or "[]"),
                "previous_meeting_ref": json.loads(memory_row["previous_meeting_ref"] or "{}"),
            }
        else:
            memory = {
                "recent_context": {},
                "relationship_trajectory": {},
                "sentiment_history": [],
                "risk_register": [],
                "blocker_log": [],
                "milestone_status": [],
                "previous_meeting_ref": {},
            }
            # Create new memory row
            await conn.execute(
                """
                INSERT INTO project_memory (project_id, recent_context, updated_at)
                VALUES ($1, $2, $3)
                """,
                project_id,
                json.dumps({"meetings": []}),
                datetime.utcnow()
            )

        # 3. Load last 3 meetings (short-term window)
        recent_meetings = await conn.fetch(
            """
            SELECT * FROM meeting_insights
            WHERE project_id = $1
            ORDER BY meeting_date DESC
            LIMIT 3
            """,
            project_id
        )

        # 4. Fill previous_meeting_ref
        if len(recent_meetings) > 1:
            prev_meeting = recent_meetings[1]  # Second most recent
            prev_yaml = json.loads(prev_meeting["raw_yaml"])
            memory["previous_meeting_ref"] = {
                "meeting_id": prev_meeting["meeting_id"],
                "date": prev_meeting["meeting_date"].isoformat(),
                "key_carryovers": []
            }
            # TODO: Implement carryover detection (open actions, blockers)

        # 5. Update sentiment_history
        sentiment = raw_yaml.get("sentiment", {})
        if sentiment:
            memory["sentiment_history"].append({
                "date": meeting["meeting_date"].isoformat(),
                "score": sentiment.get("score", 0),
                "label": sentiment.get("label", "neutral"),
                "drivers": sentiment.get("drivers", []),
                "meeting_id": meeting["meeting_id"]
            })
            # Keep only last 12 entries
            memory["sentiment_history"] = memory["sentiment_history"][-12:]

        # 6. Merge risks
        new_risks = raw_yaml.get("risks", [])
        for risk in new_risks:
            existing = next((r for r in memory["risk_register"] if r.get("description") == risk.get("description")), None)
            if not existing:
                risk_entry = {
                    "id": f"risk_{len(memory['risk_register'])}",
                    "description": risk.get("description", ""),
                    "severity": risk.get("severity", "low"),
                    "status": "open",
                    "raised_date": meeting["meeting_date"].isoformat(),
                    "resolved_date": None,
                    "source_meeting_id": meeting["meeting_id"]
                }
                memory["risk_register"].append(risk_entry)

        # 7. Age blockers and merge
        new_blockers = raw_yaml.get("blockers", [])
        for blocker in new_blockers:
            existing = next((b for b in memory["blocker_log"] if b.get("description") == blocker.get("description")), None)
            if not existing:
                blocker_entry = {
                    "id": f"blocker_{len(memory['blocker_log'])}",
                    "description": blocker.get("description", ""),
                    "raised_date": meeting["meeting_date"].isoformat(),
                    "resolved_date": None,
                    "resolved_by": None,
                    "days_open": 0
                }
                memory["blocker_log"].append(blocker_entry)

        # Age unresolved blockers
        today = date.today()
        for blocker in memory["blocker_log"]:
            if not blocker.get("resolved_date"):
                raised = datetime.fromisoformat(blocker["raised_date"]).date()
                blocker["days_open"] = (today - raised).days

        # 8. Update milestone_status
        new_milestones = raw_yaml.get("milestones", [])
        for milestone in new_milestones:
            existing = next((m for m in memory.get("milestone_status", []) if m.get("name") == milestone.get("name")), None)
            if not existing:
                milestone_entry = {
                    "name": milestone.get("name", ""),
                    "due_date": milestone.get("due_date"),
                    "status": milestone.get("status", "not_started")
                }
                if "milestone_status" not in memory:
                    memory["milestone_status"] = []
                memory["milestone_status"].append(milestone_entry)

        # 9. Update recent_context (rolling window of meetings)
        if "meetings" not in memory.get("recent_context", {}):
            memory["recent_context"] = {"meetings": []}

        memory["recent_context"]["meetings"] = [
            {
                "meeting_id": m["meeting_id"],
                "date": m["meeting_date"].isoformat(),
                "type": m["meeting_type"],
                "summary": json.loads(m["raw_yaml"]).get("summary", ""),
                "sentiment_score": json.loads(m["raw_yaml"]).get("sentiment", {}).get("score", 0),
                "open_actions": [],
                "unresolved_blockers": [b.get("description") for b in json.loads(m["raw_yaml"]).get("blockers", [])]
            }
            for m in recent_meetings
        ]

        # 10. Save updated memory
        await conn.execute(
            """
            UPDATE project_memory
            SET recent_context = $1,
                relationship_trajectory = $2,
                sentiment_history = $3,
                risk_register = $4,
                blocker_log = $5,
                milestone_status = $6,
                previous_meeting_ref = $7,
                updated_at = $8
            WHERE project_id = $9
            """,
            json.dumps(memory["recent_context"]),
            json.dumps(memory["relationship_trajectory"]),
            json.dumps(memory["sentiment_history"]),
            json.dumps(memory["risk_register"]),
            json.dumps(memory["blocker_log"]),
            json.dumps(memory["milestone_status"]),
            json.dumps(memory["previous_meeting_ref"]),
            datetime.utcnow(),
            project_id
        )

        log.info(f"✓ Memory stitched for {project_id}")
        return memory

    except Exception as e:
        log.error(f"Memory stitch failed: {e}", exc_info=True)
        return None
    finally:
        if 'conn' in locals():
            await release_connection(conn)
