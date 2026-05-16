"""
CORTEX Scheduler
APScheduler setup for recurring jobs:
- Daily health scans
- Weekly plan generation
- Cadence monitoring
- Renewal signals
"""

import logging
from datetime import datetime, time
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from cortex.config import TIMEZONE, WEEKLY_PLAN_TIME, HEALTH_SCAN_TIME

log = logging.getLogger("cortex.scheduler")

scheduler: Optional[AsyncIOScheduler] = None


def init_scheduler() -> AsyncIOScheduler:
    """Initialize APScheduler with configured jobs"""
    global scheduler

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Parse time strings (HH:MM)
    def parse_time(time_str: str) -> tuple:
        """Parse 'HH:MM' to (hour, minute)"""
        try:
            h, m = time_str.split(":")
            return int(h), int(m)
        except:
            return 8, 0

    # Weekly plan generation (Monday 07:30)
    plan_hour, plan_minute = parse_time(WEEKLY_PLAN_TIME)
    scheduler.add_job(
        weekly_plan_job,
        CronTrigger(day_of_week="mon", hour=plan_hour, minute=plan_minute, timezone=TIMEZONE),
        id="weekly_plan_monday",
        name="Generate weekly plans",
        replace_existing=True
    )
    log.info(f"Scheduled: Weekly plans at Monday {WEEKLY_PLAN_TIME}")

    # Daily health scan (08:00)
    scan_hour, scan_minute = parse_time(HEALTH_SCAN_TIME)
    scheduler.add_job(
        health_scan_job,
        CronTrigger(hour=scan_hour, minute=scan_minute, timezone=TIMEZONE),
        id="daily_health_scan",
        name="Daily health scan",
        replace_existing=True
    )
    log.info(f"Scheduled: Daily health scan at {HEALTH_SCAN_TIME}")

    # Cadence check (Monday 09:00)
    scheduler.add_job(
        cadence_check_job,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=TIMEZONE),
        id="cadence_check_monday",
        name="Check meeting cadence",
        replace_existing=True
    )
    log.info("Scheduled: Cadence check on Monday at 09:00")

    # Renewal signal (Sunday 08:00)
    scheduler.add_job(
        renewal_signal_job,
        CronTrigger(day_of_week="sun", hour=8, minute=0, timezone=TIMEZONE),
        id="renewal_signal_sunday",
        name="Check renewal signals",
        replace_existing=True
    )
    log.info("Scheduled: Renewal signal check on Sunday at 08:00")

    return scheduler


async def weekly_plan_job():
    """Generate weekly plans for all active projects (Monday 07:30)"""
    from cortex.services.weekly_plan import generate_plans_for_all_projects

    log.info("=== WEEKLY PLAN JOB STARTED ===")
    try:
        result = await generate_plans_for_all_projects()
        log.info(
            f"Weekly plan job completed: {result['successful']}/{result['total']} successful"
        )
    except Exception as e:
        log.error(f"Weekly plan job failed: {e}", exc_info=True)


async def health_scan_job():
    """Re-scan all projects and post alerts if score changed (Daily 08:00)"""
    from cortex.models.db import get_connection, release_connection
    from cortex.services.slack_notifier import send_health_alert

    log.info("=== DAILY HEALTH SCAN JOB STARTED ===")
    try:
        conn = await get_connection()
        try:
            # Get all active projects with recent health scores
            projects = await conn.fetch(
                """SELECT DISTINCT p.project_id, p.name,
                     h.score, h.health_band
                   FROM projects p
                   LEFT JOIN project_health_scores h ON p.project_id = h.project_id
                   WHERE p.status = 'active'
                   ORDER BY h.computed_at DESC"""
            )

            alert_count = 0
            for proj in projects:
                project_id = proj["project_id"]
                score = proj["score"] or 75
                band = proj["health_band"] or "amber"

                # Send alert
                success = await send_health_alert(
                    project_id=project_id,
                    score=score,
                    band=band
                )

                if success:
                    alert_count += 1
                    log.debug(f"Health alert sent for {project_id}")

            log.info(f"Health scan complete: {alert_count} alerts posted")

        finally:
            if conn:
                await release_connection(conn)

    except Exception as e:
        log.error(f"Health scan job failed: {e}", exc_info=True)


async def cadence_check_job():
    """Check for missing meetings and flag if gap exceeds threshold (Monday 09:00)"""
    from cortex.models.db import get_connection, release_connection
    from cortex.config import CADENCE_GAP_DAYS_CLIENT
    from datetime import timedelta

    log.info("=== CADENCE CHECK JOB STARTED ===")
    try:
        conn = await get_connection()
        try:
            # Find projects missing client calls
            projects = await conn.fetch(
                """SELECT p.project_id, p.name,
                     MAX(m.meeting_date) as last_meeting,
                     EXTRACT(DAY FROM NOW() - MAX(m.meeting_date)) as days_since
                   FROM projects p
                   LEFT JOIN meeting_insights m ON p.project_id = m.project_id
                     AND m.meeting_type IN ('client-call', 'milestone-review')
                   WHERE p.status = 'active'
                   GROUP BY p.project_id, p.name
                   HAVING EXTRACT(DAY FROM NOW() - MAX(m.meeting_date)) > $1""",
                CADENCE_GAP_DAYS_CLIENT
            )

            for proj in projects:
                log.warning(
                    f"Project {proj['project_id']}: "
                    f"No client call for {proj['days_since']:.0f} days"
                )

            log.info(f"Cadence check complete: {len(projects)} projects flagged")

        finally:
            if conn:
                await release_connection(conn)

    except Exception as e:
        log.error(f"Cadence check job failed: {e}", exc_info=True)


async def renewal_signal_job():
    """Flag projects with end_date < 6 weeks (Sunday 08:00)"""
    from cortex.models.db import get_connection, release_connection
    from cortex.config import RENEWAL_SIGNAL_WEEKS
    from datetime import timedelta

    log.info("=== RENEWAL SIGNAL JOB STARTED ===")
    try:
        conn = await get_connection()
        try:
            threshold = datetime.utcnow() + timedelta(weeks=RENEWAL_SIGNAL_WEEKS)

            projects = await conn.fetch(
                """SELECT project_id, name, end_date
                   FROM projects
                   WHERE status = 'active'
                   AND end_date < $1
                   AND end_date > NOW()""",
                threshold
            )

            for proj in projects:
                days_left = (proj["end_date"] - datetime.utcnow()).days
                log.warning(
                    f"Renewal signal: {proj['project_id']} "
                    f"ends in {days_left} days"
                )

            log.info(f"Renewal check complete: {len(projects)} projects require renewal")

        finally:
            if conn:
                await release_connection(conn)

    except Exception as e:
        log.error(f"Renewal signal job failed: {e}", exc_info=True)


async def start_scheduler():
    """Start the scheduler"""
    global scheduler
    if not scheduler:
        scheduler = init_scheduler()

    if not scheduler.running:
        scheduler.start()
        log.info(f"Scheduler started (timezone: {TIMEZONE})")


async def stop_scheduler():
    """Stop the scheduler"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        log.info("Scheduler stopped")


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Get scheduler instance"""
    return scheduler
