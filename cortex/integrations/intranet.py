"""
Intranet Integration Client
Resolves employee roles and project metadata from intranet.
Mock implementation for now.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

log = logging.getLogger("cortex.intranet")

# Mock employee roles for now
MOCK_EMPLOYEES = {
    "p-rohan-001": {"name": "Rohan Mehta", "role": "pm", "email": "rohan@example.com"},
    "p-priya-002": {"name": "Priya Sharma", "role": "apm", "email": "priya@example.com"},
    "p-arjun-001": {"name": "Arjun Nair", "role": "architect", "email": "arjun@example.com"},
    "p-vikram-001": {"name": "Vikram Desai", "role": "director", "email": "vikram@example.com"},
}

# Cache for role lookups (24 hour TTL)
ROLE_CACHE: Dict[str, tuple] = {}
ROLE_CACHE_TTL_MINUTES = 1440

# Mock projects
MOCK_PROJECTS = {
    "PROJ-CRM-0014": {
        "name": "CRM Field Agent",
        "client": "Acme Corp",
        "pm_id": "p-rohan-001",
        "start_date": "2026-05-01",
        "end_date": "2026-11-30",
        "stakeholders": ["p-vikram-001"],
    },
    "proj-123": {
        "name": "Sample Project",
        "client": "Sample Client",
        "pm_id": "p-priya-002",
        "start_date": "2026-06-01",
        "end_date": "2026-12-31",
        "stakeholders": [],
    }
}


async def resolve_employee_role(employee_id: str) -> Optional[str]:
    """
    Resolve employee role from intranet.
    Cached for 24 hours.
    Mock implementation.
    """
    # Check cache
    if employee_id in ROLE_CACHE:
        role, cached_at = ROLE_CACHE[employee_id]
        if datetime.utcnow() - cached_at < timedelta(minutes=ROLE_CACHE_TTL_MINUTES):
            log.debug(f"Role for {employee_id} loaded from cache: {role}")
            return role

    # Mock lookup
    if employee_id in MOCK_EMPLOYEES:
        role = MOCK_EMPLOYEES[employee_id]["role"]
        ROLE_CACHE[employee_id] = (role, datetime.utcnow())
        log.info(f"Resolved role for {employee_id}: {role}")
        return role

    log.warning(f"Employee {employee_id} not found")
    return None


async def resolve_employee_details(employee_id: str) -> Optional[Dict[str, Any]]:
    """
    Resolve full employee details from intranet.
    Mock implementation.
    """
    if employee_id in MOCK_EMPLOYEES:
        return MOCK_EMPLOYEES[employee_id]

    log.warning(f"Employee {employee_id} not found")
    return None


async def resolve_project_details(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Resolve project metadata from intranet.
    Mock implementation.
    """
    if project_id in MOCK_PROJECTS:
        return MOCK_PROJECTS[project_id]

    log.warning(f"Project {project_id} not found in mock data")
    # Return sensible defaults
    return {
        "name": project_id,
        "client": "Unknown Client",
        "pm_id": "p-unknown",
        "start_date": datetime.utcnow().isoformat(),
        "end_date": (datetime.utcnow() + timedelta(days=180)).isoformat(),
        "stakeholders": []
    }


async def resolve_project_slack_channel(project_id: str) -> Optional[str]:
    """
    Resolve Slack channel for project.
    Convention: #project-{project_id}
    Mock implementation.
    """
    # Generate standard Slack channel name
    channel = f"project-{project_id.replace('_', '-').lower()}"
    log.debug(f"Resolved Slack channel for {project_id}: {channel}")
    return channel


def clear_role_cache(employee_id: Optional[str] = None):
    """Clear role cache (all or specific employee)"""
    if employee_id:
        if employee_id in ROLE_CACHE:
            del ROLE_CACHE[employee_id]
            log.info(f"Cleared role cache for {employee_id}")
    else:
        ROLE_CACHE.clear()
        log.info("Cleared all role cache")
