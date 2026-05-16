"""Build prompts for document generation based on templates and context."""

from typing import Dict, Any
import json


def build_document_generation_prompt(template: str, context: Dict[str, Any]) -> str:
    return f"""
Fill in the following template using the supplied project context.
Return only the completed document text with no extra explanation.

Template:
{template}

Context:
{json.dumps(context, indent=2)}

Rules:
1. Replace placeholders with context values.
2. Preserve formatting.
3. Provide reasonable defaults for missing values.
""".strip()
