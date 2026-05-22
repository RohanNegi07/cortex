"""
Intranet Integration Client
Resolves employee roles and project metadata from intranet.
"""

import logging
from typing import Optional, Dict, Any

log = logging.getLogger("cortex.intranet")

ROLE_CACHE: Dict[str, tuple] = {}
ROLE_CACHE_TTL_MINUTES = 1440


async def resolve_employee_role(employee_id: str) -> Optional[str]:
    """
    Resolve employee role from intranet.
    Integration not implemented.
    """
    log.warning(f"Intranet integration not implemented: cannot resolve role for {employee_id}")
    return None


async def resolve_employee_details(employee_id: str) -> Optional[Dict[str, Any]]:
    """
    Resolve full employee details from intranet.
    Integration not implemented.
    """
    log.warning(f"Intranet integration not implemented: cannot resolve employee details for {employee_id}")
    return None


async def resolve_project_details(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Resolve project metadata from intranet.
    Integration not implemented.
    """
    log.warning(f"Intranet integration not implemented: cannot resolve project details for {project_id}")
    return None


async def resolve_project_slack_channel(project_id: str) -> Optional[str]:
    """
    Resolve Slack channel for project.
    Returns a naming convention-based channel if available.
    """
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
