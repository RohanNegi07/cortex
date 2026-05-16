"""Alerting wrappers for Slack notifications."""

from cortex.services.slack_notifier import (
    send_health_alert as _send_health_alert,
    send_action_brief as _send_action_brief,
    send_weekly_summary as _send_weekly_summary,
    send_document_ready as _send_document_ready,
)


async def send_health_alert(*args, **kwargs):
    return await _send_health_alert(*args, **kwargs)


async def send_action_brief(*args, **kwargs):
    return await _send_action_brief(*args, **kwargs)


async def send_weekly_summary(*args, **kwargs):
    return await _send_weekly_summary(*args, **kwargs)


async def send_document_ready(*args, **kwargs):
    return await _send_document_ready(*args, **kwargs)
