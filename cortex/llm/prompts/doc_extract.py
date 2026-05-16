"""Build prompts for structured document extraction."""

from typing import Dict, Any


def build_document_extraction_prompt(doc_type: str, document_text: str) -> str:
    return f"""
Extract structured data from the following {doc_type} content.
Return only valid JSON.

Document Content:
{document_text}

Expected output:
{{
  "title": "...",
  "milestones": [{{"name": "...", "due_date": "YYYY-MM-DD", "deliverables": [...]}}, ...],
  "scope": [...],
  "out_of_scope": [...],
  "stakeholders": [...]
}}
""".strip()
