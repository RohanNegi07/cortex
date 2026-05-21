"""
EOD ingestion and weekly health aggregation service.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from cortex.models.db import get_connection, release_connection
from cortex.models.schemas import (
    EODReportRequest,
    WeeklyEODHealth,
    EODStatus,
    HealthBand,
)

log = logging.getLogger("cortex.eod")


def _week_start(report_date: date) -> date:
    return report_date - timedelta(days=report_date.weekday())


def _parse_eod_row(row: Any) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "reporter_id": row["reporter_id"],
        "report_date": row["report_date"],
        "status": row["status"],
        "summary": row["summary"],
        "tasks_completed": json.loads(row["tasks_completed"] or "[]"),
        "tasks_blocked": json.loads(row["tasks_blocked"] or "[]"),
        "leave_reason": row["leave_reason"],
        "created_at": row["created_at"],
    }


def _serialize_tasks(tasks: List[Dict[str, Any]]) -> str:
    return json.dumps(tasks)


async def ingest_eod_report(project_id: str, payload: EODReportRequest) -> Dict[str, Any]:
    conn = await get_connection()
    try:
        existing = await conn.fetchrow(
            "SELECT id FROM project_eod_reports WHERE project_id = $1 AND reporter_id = $2 AND report_date = $3",
            project_id,
            payload.reporter_id,
            payload.report_date,
        )

        tasks_completed = [
            task.model_dump() if hasattr(task, "model_dump") else task.dict()
            for task in payload.tasks_completed
        ]
        tasks_blocked = [
            task.model_dump() if hasattr(task, "model_dump") else task.dict()
            for task in payload.tasks_blocked
        ]

        if existing:
            await conn.execute(
                """
                UPDATE project_eod_reports
                SET status = $1,
                    summary = $2,
                    tasks_completed = $3,
                    tasks_blocked = $4,
                    leave_reason = $5
                WHERE id = $6
                """,
                payload.status.value,
                payload.summary,
                _serialize_tasks(tasks_completed),
                _serialize_tasks(tasks_blocked),
                payload.leave_reason,
                existing["id"],
            )
            report_id = existing["id"]
        else:
            report_id = await conn.fetchval(
                """
                INSERT INTO project_eod_reports (
                    project_id, reporter_id, report_date, status,
                    summary, tasks_completed, tasks_blocked, leave_reason
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                project_id,
                payload.reporter_id,
                payload.report_date,
                payload.status.value,
                payload.summary,
                _serialize_tasks(tasks_completed),
                _serialize_tasks(tasks_blocked),
                payload.leave_reason,
            )

        row = await conn.fetchrow(
            "SELECT * FROM project_eod_reports WHERE id = $1",
            report_id,
        )
        return _parse_eod_row(row)
    finally:
        await release_connection(conn)


async def get_weekly_eod_reports(project_id: str, week_start: date) -> List[Dict[str, Any]]:
    week_end = week_start + timedelta(days=6)
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT * FROM project_eod_reports
            WHERE project_id = $1
              AND report_date >= $2
              AND report_date <= $3
            ORDER BY report_date ASC
            """,
            project_id,
            week_start,
            week_end,
        )
        return [_parse_eod_row(row) for row in rows]
    finally:
        await release_connection(conn)


async def get_projects_with_weekly_eod_reports(week_start: date) -> List[str]:
    week_end = week_start + timedelta(days=6)
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT project_id
            FROM project_eod_reports
            WHERE report_date >= $1
              AND report_date <= $2
            """,
            week_start,
            week_end,
        )
        return [str(row["project_id"]) for row in rows]
    finally:
        await release_connection(conn)


async def compute_weekly_health_for_week(week_start: date) -> Dict[str, Any]:
    project_ids = await get_projects_with_weekly_eod_reports(week_start)
    results: Dict[str, Any] = {
        "week_start": week_start,
        "total_projects": len(project_ids),
        "computed": 0,
        "failed": 0,
        "projects": []
    }

    for project_id in project_ids:
        health = await compute_weekly_health(project_id, week_start)
        if health:
            results["computed"] += 1
            results["projects"].append({
                "project_id": project_id,
                "score": health.score,
                "band": health.band,
                "eod_count": health.eod_count,
            })
        else:
            results["failed"] += 1
            results["projects"].append({
                "project_id": project_id,
                "error": "could not compute weekly health"
            })

    return results


def compute_weekly_eod_health(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    eod_count = len(reports)
    leave_count = sum(1 for r in reports if r["status"] == EODStatus.LEAVE.value)
    at_risk_count = sum(1 for r in reports if r["status"] == EODStatus.AT_RISK.value)
    blocked_count = sum(1 for r in reports if r["status"] == EODStatus.BLOCKED.value)
    blocked_task_count = sum(len(r["tasks_blocked"]) for r in reports)

    coverage_penalty = 10 if eod_count < 3 else 0
    leave_penalty = min(30, leave_count * 10)
    risk_penalty = min(20, at_risk_count * 5)
    blocked_status_penalty = min(25, blocked_count * 8)
    blocked_task_penalty = min(20, blocked_task_count * 3)

    score = 100 - (
        coverage_penalty
        + leave_penalty
        + risk_penalty
        + blocked_status_penalty
        + blocked_task_penalty
    )
    score = max(0, min(100, score))

    if score >= 80:
        band = HealthBand.GREEN
    elif score >= 60:
        band = HealthBand.AMBER
    else:
        band = HealthBand.RED

    return {
        "score": score,
        "band": band,
        "components": {
            "eod_count": eod_count,
            "coverage_penalty": coverage_penalty,
            "leave_penalty": leave_penalty,
            "at_risk_penalty": risk_penalty,
            "blocked_status_penalty": blocked_status_penalty,
            "blocked_task_penalty": blocked_task_penalty,
        },
        "eod_count": eod_count,
    }


async def compute_weekly_health(project_id: str, week_start: date) -> Optional[WeeklyEODHealth]:
    reports = await get_weekly_eod_reports(project_id, week_start)
    health = compute_weekly_eod_health(reports)

    conn = await get_connection()
    try:
        await conn.execute(
            """
            INSERT INTO project_weekly_health (
                project_id, week_start, score, band, components, eod_count
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (project_id, week_start)
            DO UPDATE SET
                score = EXCLUDED.score,
                band = EXCLUDED.band,
                components = EXCLUDED.components,
                eod_count = EXCLUDED.eod_count,
                created_at = NOW()
            """,
            project_id,
            week_start,
            health["score"],
            health["band"].value,
            json.dumps(health["components"]),
            health["eod_count"],
        )

        row = await conn.fetchrow(
            "SELECT * FROM project_weekly_health WHERE project_id = $1 AND week_start = $2",
            project_id,
            week_start,
        )
        if not row:
            return None

        return WeeklyEODHealth(
            project_id=str(row["project_id"]),
            week_start=row["week_start"],
            score=row["score"],
            band=row["band"],
            components=json.loads(row["components"]),
            eod_count=row["eod_count"],
            created_at=row["created_at"],
        )
    finally:
        await release_connection(conn)


async def get_weekly_health(project_id: str, week_start: date) -> Optional[WeeklyEODHealth]:
    conn = await get_connection()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM project_weekly_health WHERE project_id = $1 AND week_start = $2",
            project_id,
            week_start,
        )
        if not row:
            return None
        return WeeklyEODHealth(
            project_id=str(row["project_id"]),
            week_start=row["week_start"],
            score=row["score"],
            band=row["band"],
            components=json.loads(row["components"]),
            eod_count=row["eod_count"],
            created_at=row["created_at"],
        )
    finally:
        await release_connection(conn)
