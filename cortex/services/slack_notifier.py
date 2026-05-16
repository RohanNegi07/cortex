"""
Slack Notifier Service
Sends health alerts, action briefs, and weekly summaries to Slack
"""

import logging
import json
from typing import Optional, Dict, Any

from cortex.config import SLACK_BOT_TOKEN
from cortex.integrations.intranet import resolve_project_slack_channel

log = logging.getLogger("cortex.slack_notifier")

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    if SLACK_BOT_TOKEN:
        slack_client = WebClient(token=SLACK_BOT_TOKEN)
    else:
        slack_client = None
except Exception as e:
    log.warning(f"Could not initialize Slack client: {e}")
    slack_client = None


EMOJI_MAP = {
    "green": "🟢",
    "amber": "🟡",
    "red": "🔴",
    "HEALTHY": "🟢",
    "AT_RISK": "🟡",
    "CRITICAL": "🔴"
}


async def get_project_slack_channel(project_id: str) -> Optional[str]:
    """Resolve Slack channel for a project."""
    try:
        channel = await resolve_project_slack_channel(project_id)
        return channel
    except Exception as e:
        log.error(f"Failed to resolve Slack channel for {project_id}: {e}")
        return None


async def send_health_alert(
    project_id: str,
    score: int,
    band: str,
    components: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Send health score change alert to project's Slack channel.
    Format: emoji + health band + score + components breakdown
    """
    if not slack_client:
        log.warning("Slack client not initialized, skipping health alert")
        return False

    channel = await get_project_slack_channel(project_id)
    if not channel:
        log.warning(f"No Slack channel configured for {project_id}")
        return False

    try:
        emoji = EMOJI_MAP.get(band.lower(), "❓")
        color = {"green": "#36a64f", "amber": "#ff9900", "red": "#ff0000"}.get(band.lower(), "#999999")

        # Build component breakdown
        components_text = ""
        if components:
            components_text = "\n".join([
                f"  • {comp}: {value}"
                for comp, value in components.items()
                if isinstance(value, (int, str))
            ])

        message = {
            "text": f"{emoji} Health Alert: {project_id}",
            "attachments": [
                {
                    "color": color,
                    "title": f"Health Score: {score}/100 ({band.upper()})",
                    "fields": [
                        {"title": "Project", "value": project_id, "short": True},
                        {"title": "Score", "value": f"{score}/100", "short": True},
                        {"title": "Status", "value": band.upper(), "short": True},
                        {"title": "Components", "value": components_text or "N/A", "short": False}
                    ],
                    "footer": "CORTEX Health Monitoring"
                }
            ]
        }

        response = slack_client.chat_postMessage(channel=channel, **message)
        log.info(f"Health alert sent to {channel} for {project_id}")
        return True

    except SlackApiError as e:
        log.error(f"Slack API error sending health alert: {e.response['error']}")
        return False
    except Exception as e:
        log.error(f"Failed to send health alert: {e}")
        return False


async def send_action_brief(
    project_id: str,
    meeting_id: str,
    brief_content: str,
    meeting_type: str = "client-call"
) -> bool:
    """
    Send action brief to project Slack channel.
    Posts in thread if available.
    """
    if not slack_client:
        log.warning("Slack client not initialized, skipping action brief")
        return False

    channel = await get_project_slack_channel(project_id)
    if not channel:
        log.warning(f"No Slack channel configured for {project_id}")
        return False

    try:
        message = {
            "text": f"📋 Action Brief: {meeting_type}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"Action Brief - {meeting_type.title()}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": brief_content
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Project: {project_id} | Meeting: {meeting_id}"
                        }
                    ]
                }
            ]
        }

        response = slack_client.chat_postMessage(channel=channel, **message)
        log.info(f"Action brief sent to {channel} for {project_id}")
        return True

    except SlackApiError as e:
        log.error(f"Slack API error sending action brief: {e.response['error']}")
        return False
    except Exception as e:
        log.error(f"Failed to send action brief: {e}")
        return False


async def send_weekly_summary(
    project_id: str,
    week_ref: str,
    summary: Dict[str, Any]
) -> bool:
    """
    Send weekly summary to project Slack channel.
    Includes: completion rate, risks, blockers, upcoming milestones
    """
    if not slack_client:
        log.warning("Slack client not initialized, skipping weekly summary")
        return False

    channel = await get_project_slack_channel(project_id)
    if not channel:
        log.warning(f"No Slack channel configured for {project_id}")
        return False

    try:
        completion_rate = summary.get("completion_rate", 0)
        risks = summary.get("risks", [])
        blockers = summary.get("blockers", [])
        upcoming = summary.get("upcoming_milestones", [])

        # Color based on completion rate
        if completion_rate >= 0.8:
            color = "#36a64f"  # green
        elif completion_rate >= 0.6:
            color = "#ff9900"  # amber
        else:
            color = "#ff0000"  # red

        # Format risks and blockers
        risks_text = "\n".join([f"  • {r}" for r in risks[:3]]) if risks else "  • None"
        blockers_text = "\n".join([f"  • {b}" for b in blockers[:3]]) if blockers else "  • None"
        upcoming_text = "\n".join([f"  • {m}" for m in upcoming[:3]]) if upcoming else "  • None"

        message = {
            "text": f"📊 Weekly Summary: {week_ref}",
            "attachments": [
                {
                    "color": color,
                    "title": f"Week {week_ref}",
                    "fields": [
                        {"title": "Completion Rate", "value": f"{completion_rate*100:.0f}%", "short": True},
                        {"title": "Project", "value": project_id, "short": True},
                        {"title": "Open Risks", "value": risks_text, "short": False},
                        {"title": "Blockers", "value": blockers_text, "short": False},
                        {"title": "Upcoming Milestones", "value": upcoming_text, "short": False}
                    ],
                    "footer": "CORTEX Weekly Dashboard"
                }
            ]
        }

        response = slack_client.chat_postMessage(channel=channel, **message)
        log.info(f"Weekly summary sent to {channel} for {project_id}")
        return True

    except SlackApiError as e:
        log.error(f"Slack API error sending weekly summary: {e.response['error']}")
        return False
    except Exception as e:
        log.error(f"Failed to send weekly summary: {e}")
        return False


async def send_document_ready(
    project_id: str,
    doc_type: str,
    r2_url: str,
    pm_email: Optional[str] = None
) -> bool:
    """
    Notify PM that document is ready for review.
    """
    if not slack_client:
        log.warning("Slack client not initialized, skipping document notification")
        return False

    channel = await get_project_slack_channel(project_id)
    if not channel:
        log.warning(f"No Slack channel configured for {project_id}")
        return False

    try:
        message = {
            "text": f"📄 Document Ready: {doc_type}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ *{doc_type.replace('_', ' ').title()}* is ready for review\n\n<{r2_url}|View Document>"
                    }
                }
            ]
        }

        if pm_email:
            message["blocks"].append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Prepared for: <mailto:{pm_email}|{pm_email}>"
                    }
                ]
            })

        response = slack_client.chat_postMessage(channel=channel, **message)
        log.info(f"Document notification sent to {channel}")
        return True

    except SlackApiError as e:
        log.error(f"Slack API error sending document notification: {e.response['error']}")
        return False
    except Exception as e:
        log.error(f"Failed to send document notification: {e}")
        return False
