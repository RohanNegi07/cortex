"""Build prompts for action brief generation after meetings."""

from typing import Dict, Any
import json


def build_action_brief_prompt(meeting_summary: str, meeting_type: str, risks: str, blockers: str) -> str:
    return f"""
You are a project operations specialist. Generate a concise action brief from the meeting summary.
Include:
- key decisions
- open actions
- blockers
- recommended next steps

Meeting Type: {meeting_type}
Meeting Summary:
{meeting_summary}

Risks:
{risks}

Blockers:
{blockers}

Output in markdown with bullet points and short headings.
""".strip()
