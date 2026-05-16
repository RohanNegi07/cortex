"""Build prompts for relationship trajectory and narrative generation."""

import json
from typing import List, Dict, Any


def build_narrative_prompt(
    sentiment_history: List[Dict[str, Any]],
    risk_register: List[Dict[str, Any]],
    milestone_status: List[Dict[str, Any]],
    recent_meetings: List[Dict[str, Any]]
) -> str:
    return f"""
You are a senior project manager analyzing a client engagement over time.
Given the following data, produce a brief relationship trajectory analysis.

Sentiment History (last 6 meetings):
{json.dumps(sentiment_history[-6:], indent=2)}

Open Risks:
{json.dumps([r for r in risk_register if r.get('status') == 'open'], indent=2)}

Milestone Status:
{json.dumps(milestone_status, indent=2)}

Recent Meeting Summaries:
{json.dumps(recent_meetings[:3], indent=2)}

Output a JSON object with:
{{
    "trend": "improving" | "stable" | "declining",
    "narrative": "2-3 sentences. Concrete. Reference specific dates and events."
}}

Be precise. Reference dates. Focus on actionable patterns.
""".strip()
