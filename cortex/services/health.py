"""
CORTEX Health Score Service (Step 4)
Deterministic, zero-LLM health scoring adapted from phase4_monday.py.
Scores 6 dimensions based on project memory: sentiment, risks, blockers,
milestones, trajectory, and velocity from CELL.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, date, timedelta
import asyncpg
from cortex.integrations.cell_api import get_velocity_summary
from cortex.models.db import get_connection, release_connection
from cortex.models.schemas import HealthBand

log = logging.getLogger("cortex.health")

# Configurable score rules (from CORTEX_ARCHITECTURE.md §11)
SCORE_RULES = {
    "weights": {
        "sentiment": 0.20,
        "open_risks": 0.20,
        "blockers": 0.20,
        "milestones": 0.20,
        "trajectory": 0.10,
        "velocity": 0.10,
        "artifacts": 0.10,
    },
    "sentiment_threshold": 0.3,  # below this = penalty
    "red_threshold": 60,
    "amber_threshold": 80,
}


def _artifact_penalty_from_artifacts(artifacts: Dict[str, Any]) -> int:
    """Compute an additional penalty based on NERVE-provided EOD/SOW/doc artifacts."""
    if not artifacts or not isinstance(artifacts, dict):
        return 0

    penalty = 0
    eod_entries = artifacts.get("eod_reports") or artifacts.get("eods") or artifacts.get("eod") or []
    if isinstance(eod_entries, dict):
        eod_entries = [eod_entries]

    for entry in eod_entries:
        status = str(entry.get("status", "")).lower()
        if status in ("blocked", "at_risk", "at risk", "off_track", "off track"):
            penalty += 8
        elif status == "leave":
            penalty += 3

    if isinstance(eod_entries, list) and len(eod_entries) == 0 and artifacts.get("expects_eod"):
        penalty += 5

    doc_entries = artifacts.get("documents") or artifacts.get("source_docs") or artifacts.get("docs") or []
    if isinstance(doc_entries, dict):
        doc_entries = [doc_entries]

    sow_docs = [d for d in doc_entries if str(d.get("doc_type", "")).lower() == "sow" or str(d.get("type", "")).lower() == "sow"]
    if sow_docs:
        for doc in sow_docs:
            status = str(doc.get("status", "")).lower()
            if status in ("draft", "pending", "missing", "not_uploaded", "not uploaded", "waiting"):
                penalty += 10
    elif artifacts.get("requires_sow"):
        penalty += 8

    return min(penalty, 50)


def _artifact_health_signal(artifacts: Dict[str, Any]) -> Optional[int]:
    if not artifacts or not isinstance(artifacts, dict):
        return None

    raw_score = artifacts.get("health_score")
    if isinstance(raw_score, (int, float)):
        return max(0, min(100, int(raw_score)))
    return None


async def compute_health_score(
    project_id: str,
    insight_id: str
) -> Optional[Dict[str, Any]]:
    """
    Step 4: Compute deterministic health score 0-100.
    Uses project_memory + recent meetings + velocity data.
    Returns: {score, band, components} or None on failure.
    """
    try:
        conn = await get_connection()

        # 1. Get project memory
        memory_row = await conn.fetchrow(
            "SELECT * FROM project_memory WHERE project_id = $1",
            project_id
        )
        if not memory_row:
            log.warning(f"No project memory for {project_id}")
            return None

        sentiment_history = json.loads(memory_row["sentiment_history"] or "[]")
        risk_register = json.loads(memory_row["risk_register"] or "[]")
        blocker_log = json.loads(memory_row["blocker_log"] or "[]")
        milestone_status = json.loads(memory_row["milestone_status"] or "[]")
        relationship_trajectory = json.loads(memory_row["relationship_trajectory"] or "{}")

        # 2. Get recent meetings and current meeting artifacts
        recent_meetings = await conn.fetch(
            """
            SELECT * FROM meeting_insights
            WHERE project_id = $1
            ORDER BY meeting_date DESC
            LIMIT 3
            """,
            project_id
        )

        current_meeting = await conn.fetchrow(
            "SELECT raw_yaml FROM meeting_insights WHERE id = $1",
            insight_id
        )
        current_yaml = json.loads(current_meeting["raw_yaml"]) if current_meeting else {}

        # 3. Compute components
        components = {}

        # ── SENTIMENT (last 3 meetings average)
        if len(sentiment_history) >= 1:
            avg_sentiment = sum(s.get("score", 0) for s in sentiment_history[-3:]) / min(len(sentiment_history), 3)
        else:
            avg_sentiment = 0.5

        sentiment_penalty = 0
        if avg_sentiment < 0:
            sentiment_penalty = 20
        elif avg_sentiment < SCORE_RULES["sentiment_threshold"]:
            sentiment_penalty = 10
        components["sentiment_penalty"] = sentiment_penalty

        # ── OPEN HIGH-SEVERITY RISKS
        open_high = [r for r in risk_register if r.get("severity") == "high" and r.get("status") == "open"]
        risk_penalty = len(open_high) * 10
        components["open_risks_penalty"] = risk_penalty

        # ── UNRESOLVED BLOCKERS BY AGE
        blocker_penalty = 0
        today = date.today()
        for b in blocker_log:
            if not b.get("resolved_date"):
                raised = datetime.fromisoformat(b["raised_date"]).date()
                days = (today - raised).days
                if days > 7:
                    blocker_penalty += 15
                elif days > 3:
                    blocker_penalty += 7
        components["blocker_penalty"] = blocker_penalty

        # ── MILESTONES AT RISK
        at_risk = [m for m in milestone_status if m.get("status") == "at_risk"]
        milestone_penalty = len(at_risk) * 8
        components["milestone_penalty"] = milestone_penalty

        # ── RELATIONSHIP TRAJECTORY TREND
        trajectory_penalty = 0
        if relationship_trajectory.get("trend") == "declining":
            trajectory_penalty = 10
        components["trajectory_penalty"] = trajectory_penalty

        # ── VELOCITY (CELL integration)
        velocity_penalty = 0
        try:
            week_ref = f"{datetime.utcnow().isocalendar()[0]}-W{datetime.utcnow().isocalendar()[1]:02d}"
            velocity_data = await get_velocity_summary(project_id, week_ref)
            if velocity_data and isinstance(velocity_data, dict):
                completion_rate = float(velocity_data.get("completion_rate", 1.0))
                if completion_rate < 0.5:
                    velocity_penalty = 15
                elif completion_rate < 0.7:
                    velocity_penalty = 8
                elif completion_rate < 0.85:
                    velocity_penalty = 5
            else:
                log.warning(f"Velocity data unavailable for {project_id}")
        except Exception as e:
            log.warning(f"Velocity integration failed for {project_id}: {e}")
        components["velocity_penalty"] = velocity_penalty

        # ── ARTIFACT SIGNALS FROM NERVE
        artifact_penalty = _artifact_penalty_from_artifacts(current_yaml.get("meeting_artifacts", {}))
        components["artifact_penalty"] = artifact_penalty

        # 4. Compute final score
        score = 100
        for penalty_key in ["sentiment_penalty", "open_risks_penalty", "blocker_penalty", "milestone_penalty", "trajectory_penalty", "velocity_penalty", "artifact_penalty"]:
            score -= components[penalty_key]

        artifact_health_signal = _artifact_health_signal(current_yaml.get("meeting_artifacts", {}))
        score = max(0, min(100, score))
        if artifact_health_signal is not None:
            score = int(round((score * 0.7) + (artifact_health_signal * 0.3)))

        score = max(0, min(100, score))

        # 5. Determine band
        if score >= SCORE_RULES["amber_threshold"]:
            band = HealthBand.GREEN
        elif score >= SCORE_RULES["red_threshold"]:
            band = HealthBand.AMBER
        else:
            band = HealthBand.RED

        # 6. Insert into project_health_scores
        health_score_id = await conn.fetchval(
            """
            INSERT INTO project_health_scores (
                project_id, score, band, components, computed_after_meeting_id
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            project_id,
            score,
            band.value,
            json.dumps(components),
            str(insight_id)
        )

        log.info(f"✓ Health score computed for {project_id}: {score}/100 ({band.value})")

        return {
            "id": str(health_score_id),
            "score": score,
            "band": band.value,
            "components": components
        }

    except Exception as e:
        log.error(f"Health score computation failed: {e}", exc_info=True)
        return None
    finally:
        if 'conn' in locals():
            await release_connection(conn)
