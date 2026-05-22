"""Alerting wrappers.

This module intentionally left as a thin wrapper for alerting
APIs to preserve imports across the codebase. Slack/EOD
functionality has been disabled; callers should import from
`cortex.services.alerts` but no external posts will occur.
"""

async def send_health_alert(*args, **kwargs):
    return False


async def send_action_brief(*args, **kwargs):
    return False


async def send_weekly_summary(*args, **kwargs):
    return False


async def send_document_ready(*args, **kwargs):
    return False
