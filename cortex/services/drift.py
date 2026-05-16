"""
CORTEX Milestone Drift Detection (Step 5)
Detects when milestones are at risk of missing due dates.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, date
import asyncpg
from cortex.models.db import get_connection, release_connection

log = logging.getLogger("cortex.drift")

async def detect_milestone_drift(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Step 5: Detect milestone drift.
    Compares current_due_date vs original_due_date.
    Flags if drift > 3 days.
    """
    try:
        conn = await get_connection()

        # Get all open milestones
        milestones = await conn.fetch(
            """
            SELECT * FROM project_milestones
            WHERE project_id = $1 AND status IN ('not_started', 'in_progress', 'at_risk')
            """,
            project_id
        )

        drifted = []
        for m in milestones:
            original = m["original_due_date"]
            current = m["current_due_date"]
            drift_days = (current - original).days if isinstance(current, date) else 0

            if drift_days > 3:
                drifted.append({
                    "milestone_id": str(m["id"]),
                    "name": m["name"],
                    "original_due_date": original.isoformat() if original else None,
                    "current_due_date": current.isoformat() if current else None,
                    "drift_days": drift_days
                })

                # Update milestone status to at_risk if not already
                if m["status"] != "at_risk":
                    await conn.execute(
                        "UPDATE project_milestones SET status = 'at_risk' WHERE id = $1",
                        m["id"]
                    )

        if drifted:
            log.info(f"✓ Detected {len(drifted)} drifted milestones for {project_id}")

        return {"drifted_count": len(drifted), "milestones": drifted}

    except Exception as e:
        log.error(f"Drift detection failed: {e}")
        return None
    finally:
        if 'conn' in locals():
            await release_connection(conn)
