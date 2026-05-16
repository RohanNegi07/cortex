"""
CORTEX Chat Router
Conversational interface for project queries.
Retrieves context from memory and responds via Claude API.
"""

from fastapi import APIRouter, HTTPException
import logging
from cortex.models.schemas import ChatRequest, ChatResponse
from cortex.services.chat import process_chat_query

log = logging.getLogger("cortex.chat")

router = APIRouter(prefix="/cortex", tags=["CHAT"])

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    PM/stakeholder query endpoint.

    Retrieves project context (health, memory, recent meetings)
    and generates a role-aware response via Claude.

    Request:
      - project_id: str (required)
      - question: str (required)
      - user_role: str (optional: pm, director, ba, apm. defaults to pm)

    Response:
      - answer: str (the response)
      - health_score: int (current project health)
      - status: str (green/amber/red)
      - confidence: float (0-1)
    """
    try:
        result = await process_chat_query(request)
        return result
    except Exception as e:
        log.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
