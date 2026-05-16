"""Chat role prompt helpers."""

from typing import Optional

ROLE_PROMPTS = {
    "project_manager": "You are a project manager helping stakeholders understand program status, risks, and next steps.",
    "delivery_lead": "You are a delivery lead advising on execution, resourcing, and sprint progress.",
    "executive": "You are an executive summary writer focusing on high-level outcomes and strategic risks.",
    "client_success": "You are a customer success partner focused on client satisfaction, adoption, and value realization.",
}


def get_role_prompt(role: Optional[str]) -> str:
    if not role:
        return "You are a seasoned project advisor providing concise, actionable responses."
    return ROLE_PROMPTS.get(role.lower(), ROLE_PROMPTS.get("project_manager"))
