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


def _extract_response_text(response: Any) -> str:
    content = response.get("content", "") if isinstance(response, dict) else getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for chunk in content:
            if isinstance(chunk, str):
                text_parts.append(chunk)
            else:
                value = getattr(chunk, "text", None) or getattr(chunk, "content", None)
                if value is None:
                    try:
                        text_parts.append(str(chunk))
                    except Exception:
                        pass
                else:
                    text_parts.append(value)
        return "".join(text_parts)
    if isinstance(content, dict):
        return content.get("text", content.get("content", ""))
    return str(content) if content is not None else ""


async def process_chat_query(request: ChatRequest) -> ChatResponse:
    project_context = await get_project_context(request.project_id)
    role_prompt = get_role_prompt(request.user_role)
    health_score = project_context.get("health_score")
    health_status = project_context.get("health_band")

    # Build system prompt + user message for Anthropic
    system_prompt = (
        f"{role_prompt}\n"
        f"Project context: {project_context}\n"
        "Answer clearly and keep responses actionable."
    )
    user_message = {
        "role": "user",
        "content": request.question
    }

    messages = [
        {"role": "system", "content": system_prompt},
        user_message
    ]

    anthropic_client = get_anthropic_client()
    if anthropic_client:
        try:
            response = anthropic_client.messages.create(
                model=ANTHROPIC_MODEL,
                system=system_prompt,
                messages=[user_message],
                max_tokens=600,
                temperature=0.7
            )
            response_text = _extract_response_text(response)
            return ChatResponse(
                answer=response_text,
                project_id=request.project_id,
                user_role=request.user_role,
                health_score=health_score,
                status=health_status,
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
            response_text = _extract_response_text(response)
            return ChatResponse(
                answer=response_text,
                project_id=request.project_id,
                user_role=request.user_role,
                health_score=health_score,
                status=health_status,
                confidence=0.9,
                generated_at=datetime.utcnow()
            )
        except Exception as e:
            log.warning(f"GROQ chat failed: {e}")

    return ChatResponse(
        answer="I am unable to generate a response at this time. Please try again later.",
        project_id=request.project_id,
        user_role=request.user_role,
        health_score=health_score,
        status=health_status,
        confidence=0.5,
        generated_at=datetime.utcnow(),
        sources=[]
    )
