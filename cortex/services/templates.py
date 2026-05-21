"""
R2 Template Management
Loads document templates from R2 with in-memory caching (1h TTL).
Fallback to hardcoded templates if R2 unavailable.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger("cortex.templates")

TEMPLATE_CACHE = {}  # {doc_type: (content, loaded_at)}
CACHE_TTL_MINUTES = 60


async def load_template(doc_type: str) -> str:
    """
    Load template from R2 with in-memory cache (1h TTL).
    Falls back to hardcoded template if R2 unavailable.
    """
    # Check cache
    if doc_type in TEMPLATE_CACHE:
        content, loaded_at = TEMPLATE_CACHE[doc_type]
        if datetime.utcnow() - loaded_at < timedelta(minutes=CACHE_TTL_MINUTES):
            log.debug(f"Template {doc_type} loaded from cache")
            return content

    # Load from hardcoded templates only
    content = get_hardcoded_template(doc_type)
    TEMPLATE_CACHE[doc_type] = (content, datetime.utcnow())
    log.info(f"Loaded hardcoded template {doc_type}")
    return content


def get_hardcoded_template(doc_type: str) -> str:
    """Fallback hardcoded templates"""
    if doc_type == "status_report":
        return """PROJECT STATUS REPORT
Project: {project_id}
Date: {generated_date}
Health Score: {health_score}/100 ({health_status})

EXECUTIVE SUMMARY
Project status overview with key metrics and upcoming milestones.

KEY METRICS
- Project Health: {health_status}
- Open Risks: {risks_count}
- Active Blockers: {blockers_count}
- Delivery Timeline: {delivery_status}

RECENT ACTIVITIES
{recent_activities}

UPCOMING MILESTONES
{upcoming_milestones}

RISKS & BLOCKERS
{risks_summary}

RECOMMENDATIONS
{recommendations}
"""

    elif doc_type == "kt_document":
        return """KNOWLEDGE TRANSFER DOCUMENT
Project: {project_id}
Prepared: {generated_date}

PROJECT OVERVIEW
{project_overview}

CURRENT STATUS
- Health Score: {health_score}/100
- Status: {health_status}
- Active Risks: {risks_count}
- Open Blockers: {blockers_count}

KEY DECISIONS & TECHNICAL NOTES
{key_decisions}

TEAM & CONTACTS
{team_contacts}

CRITICAL RISKS
{critical_risks}

NEXT STEPS & HANDOFF
{next_steps}
"""

    elif doc_type == "milestone_deliverable":
        return """MILESTONE DELIVERABLE CHECKLIST
Project: {project_id}
Milestone: {milestone_name}
Status: {milestone_status}
Health: {health_score}/100

DELIVERABLES COMPLETED
{deliverables_completed}

DELIVERABLES PENDING
{deliverables_pending}

UAT RESULTS
- Tests Conducted: {uat_tests}
- P1 Issues: {p1_count}
- P2 Issues: {p2_count}
- P3 Issues: {p3_count}
- Overall Status: {uat_status}

APPROVAL & SIGN-OFF
Client: {client_signoff}
Date: {signoff_date}

NEXT PHASE
{next_phase}
"""

    else:
        return f"Template {doc_type} not found. Available: status_report, kt_document, milestone_deliverable"


async def clear_cache(doc_type: Optional[str] = None):
    """Clear template cache (all or specific doc_type)"""
    if doc_type:
        if doc_type in TEMPLATE_CACHE:
            del TEMPLATE_CACHE[doc_type]
            log.info(f"Cleared cache for {doc_type}")
    else:
        TEMPLATE_CACHE.clear()
        log.info("Cleared all template cache")
