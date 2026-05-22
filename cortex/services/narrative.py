"""
CORTEX Narrative Service (Step 3)
Calls Claude to generate relationship_trajectory based on sentiment history,
risks, milestones, and recent context.
"""

import json
import logging
import re
from typing import Optional, Dict, Any
from datetime import datetime
import asyncpg
from cortex.models.db import get_connection, release_connection
from cortex.llm.client import get_async_anthropic_client, get_groq_client
from cortex.llm.prompts.narrative import build_narrative_prompt
from cortex.config import ANTHROPIC_MODEL, GROQ_MODEL

log = logging.getLogger("cortex.narrative")

anthropic_client = get_async_anthropic_client()
groq_client = get_groq_client()

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
        prompt = build_narrative_prompt(
            sentiment_history=sentiment_history,
            risk_register=risk_register,
            milestone_status=milestone_status,
            recent_meetings=recent_context.get("meetings", [])
        )

        # 3. Call Claude or GROQ
        def _extract_text(content_value):
            if isinstance(content_value, str):
                return content_value.strip()
            if isinstance(content_value, (list, tuple)):
                return "".join(
                    getattr(block, "text", "")
                    for block in content_value
                    if getattr(block, "type", None) == "text"
                ).strip()
            return str(content_value).strip()

        def _parse_json_text(text_value):
            if not text_value:
                return None
            text_value = text_value.strip()
            try:
                return json.loads(text_value)
            except json.JSONDecodeError:
                cleaned = re.sub(r"```(?:json)?", "", text_value, flags=re.IGNORECASE).strip()
                match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
                if match:
                    candidate = match.group(0)
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
                lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
                if lines and lines[0].startswith("{") and lines[-1].endswith("}"):
                    candidate = "\n".join(lines)
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
            return None

        narrative = None
        if anthropic_client:
            try:
                response = await anthropic_client.messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=300,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                response_text = _extract_text(getattr(response, "content", []) or [])
                if not response_text and hasattr(response, "content"):
                    response_text = _extract_text(response.content)
                if response_text:
                    narrative = _parse_json_text(response_text)
                    if narrative is None:
                        narrative = {
                            "trend": "stable",
                            "narrative": response_text
                        }
            except Exception as e:
                log.warning(f"Anthropic narrative failed: {e}")

        if narrative is None and groq_client:
            try:
                response = groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a senior project manager analyzing a client engagement over time."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1500,
                    temperature=0.3
                )
                response_text = ""
                if getattr(response, "choices", None):
                    choice = response.choices[0]
                    message = getattr(choice, "message", None)
                    response_text = _extract_text(getattr(message, "content", None))
                if not response_text:
                    response_text = _extract_text(getattr(response, "text", None) or getattr(response, "content", None))
                if response_text:
                    narrative = _parse_json_text(response_text)
                    if narrative is None:
                        narrative = {
                            "trend": "stable",
                            "narrative": response_text
                        }
            except Exception as e:
                log.warning(f"GROQ narrative failed: {e}")

        if narrative is None:
            log.warning("Narrative generation unavailable or failed.")
            return None

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
