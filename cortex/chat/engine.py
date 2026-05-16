"""Chat engine implementation for CORTEX."""

import logging
from datetime import datetime
from typing import Any, Dict, List

from cortex.chat.role_prompts import get_role_prompt
from cortex.chat.retrieval import get_project_context
from cortex.llm.client import get_anthropic_client, get_groq_client
from cortex.models.schemas import ChatRequest, ChatResponse
from cortex.config import ANTHROPIC_MODEL, GROQ_MODEL

log = logging.getLogger("cortex.chat.engine")


async def process_chat_query(request: ChatRequest) -> ChatResponse:
    project_context = await get_project_context(request.project_id)
    role_prompt = get_role_prompt(request.user_role)

    # Build system and user messages consistently
    system_message = {
        "role": "system",
        "content": (
            f"{role_prompt}\n"
            f"Project context: {project_context}\n"
            "Answer clearly and keep responses actionable."
        )
    }
    user_message = {
        "role": "user",
        "content": request.question
    }
    messages = [system_message, user_message]

    anthropic_client = get_anthropic_client()
    if anthropic_client:
        try:
            response = anthropic_client.messages.create(
                model=ANTHROPIC_MODEL,
                messages=messages,
                max_tokens=600,
                temperature=0.7
            )
            response_text = response.get("content", "") if isinstance(response, dict) else getattr(response, "content", "")
            return ChatResponse(
                answer=response_text,
                project_id=request.project_id,
                user_role=request.user_role,
                confidence=0.9,
                generated_at=datetime.utcnow()
            )
        except Exception as e:
            log.warning(f"Anthropic chat failed: {e}")

    groq_client = get_groq_client()
    if groq_client:
        try:
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=600
            )
            response_text = response.get("content", "") if isinstance(response, dict) else getattr(response, "content", "")
            return ChatResponse(
                answer=response_text,
                project_id=request.project_id,
                user_role=request.user_role,
                confidence=0.9,
                generated_at=datetime.utcnow()
            )
        except Exception as e:
            log.warning(f"GROQ chat failed: {e}")

    return ChatResponse(
        answer="I am unable to generate a response at this time. Please try again later.",
        project_id=request.project_id,
        user_role=request.user_role,
        confidence=0.5,
        generated_at=datetime.utcnow(),
        sources=[]
    )
