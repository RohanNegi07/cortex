"""
CORTEX Chat Service
Processes user queries and generates context-aware responses.
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

from cortex.config import ANTHROPIC_API_KEY, CORTEX_ENV
from cortex.models.schemas import ChatRequest, ChatResponse
from cortex.models.db import get_connection, _pool

log = logging.getLogger("cortex.chat")

try:
    from anthropic import Anthropic
    if ANTHROPIC_API_KEY:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
    else:
        client = None
except Exception as e:
    log.warning(f"Could not initialize Anthropic client: {e}")
    client = None

async def get_project_context(project_id: str) -> Dict[str, Any]:
    """Retrieve project health, memory, and recent meetings"""
    conn = await get_connection()
    try:
        # Get latest health score
        health = await conn.fetchrow(
            "SELECT score, health_band FROM project_health_scores WHERE project_id = $1 ORDER BY computed_at DESC LIMIT 1",
            project_id
        )

        # Get recent meetings (last 3)
        meetings = await conn.fetch(
            """SELECT meeting_id, meeting_date, meeting_type, summary
               FROM meeting_insights
               WHERE project_id = $1
               ORDER BY meeting_date DESC
               LIMIT 3""",
            project_id
        )

        # Get project memory
        memory = await conn.fetchrow(
            "SELECT sentiment_history, risk_register FROM project_memory WHERE project_id = $1",
            project_id
        )

        # If no project data, return stub for demo
        if not health and not meetings and not memory:
            log.warning(f"No data for project {project_id}, returning demo context")
            return {
                "health": {"score": 75, "status": "amber"},
                "recent_meetings": [
                    {
                        "meeting_id": "demo_001",
                        "meeting_date": "2026-05-15",
                        "meeting_type": "client-call",
                        "summary": "Client review of Phase 1 deliverables. Good progress on API layer."
                    }
                ],
                "sentiment_history": [],
                "risks": []
            }

        return {
            "health": {
                "score": health["score"] if health else 75,
                "status": health["health_band"] if health else "amber"
            },
            "recent_meetings": [dict(m) for m in (meetings or [])],
            "sentiment_history": json.loads(memory["sentiment_history"]) if memory and memory["sentiment_history"] else [],
            "risks": json.loads(memory["risk_register"]) if memory and memory["risk_register"] else []
        }
    except Exception as e:
        log.error(f"Error retrieving project context: {e}")
        return {
            "health": {"score": 75, "status": "amber"},
            "recent_meetings": [],
            "sentiment_history": [],
            "risks": []
        }
    finally:
        await _pool.release(conn)


def format_context_for_role(context: Dict[str, Any], role: str) -> str:
    """Format context based on user role"""
    health = context.get("health", {})
    score = health.get("score", 0)
    status = health.get("status", "unknown")

    base_context = f"""Project Health Score: {score}/100 ({status})

Recent Meetings:"""
    for m in context.get("recent_meetings", [])[:2]:
        base_context += f"\n- {m.get('meeting_date')}: {m.get('meeting_type')} - {m.get('summary', '')[:100]}"

    if role == "director":
        base_context += f"\n\nFocus: Business impact, timeline, expansion opportunities"
    elif role == "ba":
        base_context += f"\n\nFocus: Client champion sentiment, discovery insights, expansion signals"
    elif role == "apm":
        base_context += f"\n\nFocus: Tasks, blockers, velocity, team performance"
    else:  # pm
        base_context += f"\n\nFocus: Operational health, risks, client relationships, delivery"

    return base_context


def generate_demo_response(question: str, role: str, context: Dict[str, Any]) -> str:
    """Generate a demo response for development/testing"""
    health_score = context.get("health", {}).get("score", 75)

    responses = {
        "How is this project going?": f"Project status is stable at {health_score}/100 health. Last client call was positive. No critical blockers at the moment.",
        "What are the risks?": "Key risks: Milestone 2 could slip if database migration doesn't complete by Friday. Client is aware and agreed to contingency plan.",
        "Are we on track?": "Yes, we're 60% through the timeline with good velocity. One area to watch: the auth module complexity is 15% higher than estimated.",
        "What blockers do we have?": "Currently 1 open blocker: staging database credentials not configured. This is blocking QA testing for Feature A."
    }

    return responses.get(question, f"Project {context.get('project_id', 'N/A')} is progressing. Health score: {health_score}/100. Ready to help with specific questions.")


async def process_chat_query(request: ChatRequest) -> ChatResponse:
    """
    Process a chat query:
    1. Retrieve project context
    2. Build role-aware system prompt
    3. Call GROQ (or use demo if no API key)
    4. Return formatted response
    """
    project_id = request.project_id
    question = request.question
    role = request.user_role

    log.info(f"Chat query: {project_id} / {role} / {question[:50]}")

    # Get context
    context = await get_project_context(project_id)
    context_str = format_context_for_role(context, role)

    # Determine if we can use real API
    use_demo = not client or not GROQ_API_KEY

    if use_demo:
        log.warning("Using demo mode (no valid GROQ client)")
        answer = generate_demo_response(question, role, context)
    else:
        try:
            # Build system prompt
            system_prompt = f"""You are CORTEX, an intelligent project management assistant for a consultancy.
You are answering a {role.upper()}.

Current Project Context:
{context_str}

Guidelines:
- Be concise and actionable
- Highlight risks and blockers
- Use the {role} perspective to frame your answer
- If health is red/amber, prioritize escalation actions"""

            # Build messages - include system prompt in messages for GROQ
            messages = [{"role": "system", "content": system_prompt}]
            for msg in request.conversation_history:
                messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": question})

            # Call GROQ
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            answer = response.choices[0].message.content
        except Exception as e:
            log.error(f"GROQ API error: {e}. Falling back to demo mode.")
            answer = generate_demo_response(question, role, context)
            use_demo = True

    return ChatResponse(
        answer=answer,
        project_id=project_id,
        user_role=role,
        health_score=context.get("health", {}).get("score"),
        status=context.get("health", {}).get("status"),
        confidence=0.9 if not use_demo else 0.5,
        sources=[m.get("meeting_id") for m in context.get("recent_meetings", [])],
        generated_at=datetime.utcnow()
    )
