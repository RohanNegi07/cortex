"""
EOD router for daily end-of-day submissions and weekly health aggregation.
"""

import logging
from datetime import date
from fastapi import APIRouter, Header, HTTPException, status

from cortex.config import CORTEX_API_KEY
from cortex.models.db import normalize_project_id
from cortex.models.schemas import EODReportRequest, EODReportResponse, WeeklyEODHealth
from cortex.services.eod import (
    ingest_eod_report,
    compute_weekly_health,
    get_weekly_health,
)

log = logging.getLogger("cortex.routers.eod")
router = APIRouter(prefix="/cortex/eod", tags=["eod"])


def _verify_api_key(x_api_key: str):
    if CORTEX_API_KEY and x_api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@router.post("/", response_model=EODReportResponse)
async def post_eod_report(
    payload: EODReportRequest,
    x_api_key: str = Header(None)
):
    _verify_api_key(x_api_key)

    internal_project_id = await normalize_project_id(payload.project_id)
    if not internal_project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    report = await ingest_eod_report(internal_project_id, payload)
    return EODReportResponse(**report)


@router.post("/{project_id}/weekly/{week_start}/compute", response_model=WeeklyEODHealth)
async def post_compute_weekly_health(
    project_id: str,
    week_start: date,
    x_api_key: str = Header(None)
):
    _verify_api_key(x_api_key)

    internal_project_id = await normalize_project_id(project_id)
    if not internal_project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    health = await compute_weekly_health(internal_project_id, week_start)
    if not health:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekly health could not be computed")
    return health

