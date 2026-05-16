"""LLM client factory for Anthropic and Groq."""

import logging
from typing import Optional

from cortex.config import ANTHROPIC_API_KEY, GROQ_API_KEY

log = logging.getLogger("cortex.llm.client")

try:
    from anthropic import Anthropic, AsyncAnthropic
    anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
    async_anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except Exception as e:
    log.warning(f"Could not initialize Anthropic client: {e}")
    anthropic_client = None
    async_anthropic_client = None

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except Exception as e:
    log.warning(f"Could not initialize Groq client: {e}")
    groq_client = None


def get_anthropic_client() -> Optional[object]:
    return anthropic_client


def get_async_anthropic_client() -> Optional[object]:
    return async_anthropic_client


def get_groq_client() -> Optional[object]:
    return groq_client
