"""
ERP Integration Client
Interfaces with ERP system for milestone updates.
"""

import logging
from typing import Optional, Dict, Any
import httpx
from datetime import datetime

from cortex.config import ERP_API_BASE_URL, ERP_API_KEY
from cortex.models.db import get_connection

log = logging.getLogger("cortex.erp")


async def update_milestone_status(
    milestone_id: str,
    status: str,
    deliverable_url: Optional[str] = None,
    approved_by: Optional[str] = None
) -> bool:
    """
    Update milestone status in ERP system.
    Endpoint: PATCH /api/milestones/{milestone_id}

    Status values: "draft", "in_progress", "completed", "approved", "invoiced"
    """
    try:
        url = f"{ERP_API_BASE_URL}/api/milestones/{milestone_id}"
        headers = {"X-API-Key": ERP_API_KEY} if ERP_API_KEY else {}

        payload = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat()
        }

        if deliverable_url:
            payload["deliverable_link"] = deliverable_url

        if approved_by:
            payload["approved_by"] = approved_by
            payload["approved_date"] = datetime.utcnow().isoformat()

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.patch(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            log.info(f"Updated milestone {milestone_id} status to {status}")
            return True

    except httpx.HTTPError as e:
        log.error(f"ERP API error updating milestone: {e}")
        return False
    except Exception as e:
        log.error(f"Failed to update milestone: {e}")
        return False


async def get_milestone_status(milestone_id: str) -> Optional[Dict[str, Any]]:
    """Fetch current milestone status from ERP"""
    try:
        url = f"{ERP_API_BASE_URL}/api/milestones/{milestone_id}"
        headers = {"X-API-Key": ERP_API_KEY} if ERP_API_KEY else {}

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            log.debug(f"Fetched milestone {milestone_id} status from ERP")
            return data

    except httpx.HTTPError as e:
        log.error(f"ERP API error fetching milestone: {e}")
        return None
    except Exception as e:
        log.error(f"Failed to fetch milestone: {e}")
        return None


async def create_milestone(
    project_id: str,
    milestone_name: str,
    due_date: str,
    deliverables: list
) -> Optional[str]:
    """
    Create new milestone in ERP.
    Returns milestone_id if successful.
    """
    try:
        url = f"{ERP_API_BASE_URL}/api/milestones"
        headers = {"X-API-Key": ERP_API_KEY} if ERP_API_KEY else {}

        payload = {
            "project_id": project_id,
            "name": milestone_name,
            "due_date": due_date,
            "deliverables": deliverables,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat()
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            milestone_id = result.get("milestone_id")
            log.info(f"Created milestone {milestone_id} in ERP for {project_id}")
            return milestone_id

    except httpx.HTTPError as e:
        log.error(f"ERP API error creating milestone: {e}")
        return None
    except Exception as e:
        log.error(f"Failed to create milestone: {e}")
        return None
