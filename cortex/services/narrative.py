"""
CORTEX Narrative Service (Step 3)
Calls Claude to generate relationship_trajectory based on sentiment history,
risks, milestones, and recent context.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import asyncpg
from cortex.models.db import get_connection, release_connection
from cortex.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

log = logging.getLogger("cortex.narrative")

try:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except Exception as e:
    log.warning(f"Could not initialize AsyncAnthropic client: {e}")
    client = None

async def update_narrative(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Step 3: Update relationship_trajectory narrative using Claude.
    Reads sentiment_history, risk_register, milestone_status, recent context.
    Outputs: trend (improving/stable/declining) + narrative (2-3 sentences).
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
        milestone_status = json.loads(memory_row["milestone_status"] or "[]")
        recent_context = json.loads(memory_row["recent_context"] or "{}")

        # 2. Build prompt
        prompt = f"""
You are a senior project manager analyzing a client engagement over time.
Given the following data, produce a brief relationship trajectory analysis.

Sentiment History (last 6 meetings):
{json.dumps(sentiment_history[-6:], indent=2)}

Open Risks:
{json.dumps([r for r in risk_register if r.get('status') == 'open'], indent=2)}

Milestone Status:
{json.dumps(milestone_status, indent=2)}

Recent Meeting Summaries:
{json.dumps(recent_context.get('meetings', [])[:3], indent=2)}

Output a JSON object with:
{{
    "trend": "improving" | "stable" | "declining",
    "narrative": "2-3 sentences. Concrete. Reference specific dates and events."
}}

Be precise. Reference dates. Focus on actionable patterns.
"""

        # 3. Call Claude
        if not ANTHROPIC_API_KEY:
            log.warning("ANTHROPIC_API_KEY not configured. Using stub narrative.")
            narrative = {
                "trend": "stable",
                "narrative": "Project proceeding as planned."
            }
        else:
            client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=300,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            response_text = response.content[0].text
            # Parse JSON from response
            try:
                narrative = json.loads(response_text)
            except:
                # Fallback if Claude doesn't return valid JSON
                narrative = {
                    "trend": "stable",
                    "narrative": response_text[:200]
                }

        # 4. Update project_memory
        trajectory = {
            "trend": narrative.get("trend", "stable"),
            "narrative": narrative.get("narrative", ""),
            "updated_at": datetime.utcnow().isoformat()
        }

        await conn.execute(
            """
            UPDATE project_memory
            SET relationship_trajectory = $1, updated_at = $2
            WHERE project_id = $3
            """,
            json.dumps(trajectory),
            datetime.utcnow(),
            project_id
        )

        log.info(f"✓ Narrative updated for {project_id}: trend={trajectory['trend']}")
        return trajectory

    except Exception as e:
        log.error(f"Narrative update failed: {e}", exc_info=True)
        return None
    finally:
        if 'conn' in locals():
            await release_connection(conn)
