"""
Knowledge Transfer Document Generation Service
Generates KT documents on PM team changes.
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

from cortex.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from cortex.models.db import get_connection, release_connection
from cortex.integrations.r2 import get_r2_client
from cortex.integrations.intranet import resolve_employee_details, resolve_project_details
from cortex.services.slack_notifier import send_document_ready
from cortex.llm.prompts.kt import build_kt_prompt

log = logging.getLogger("cortex.kt")

try:
    from anthropic import Anthropic
    if ANTHROPIC_API_KEY:
        claude_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    else:
        claude_client = None
except Exception as e:
    log.warning(f"Could not initialize Claude client: {e}")
    claude_client = None


async def generate_kt_document(
    project_id: str,
    outgoing_employee_id: str,
    incoming_employee_id: str,
    effective_date: str
) -> Optional[Dict[str, Any]]:
    """
    Generate KT document for PM transition.
    Returns: {status, document_id, r2_url, slack_posted}
    """
    try:
        conn = await get_connection()
        try:
            # Get project details
            project = await conn.fetchrow(
                "SELECT * FROM projects WHERE id = $1",
                project_id
            )
            if not project:
                log.warning(f"Project {project_id} not found")
                return None

            external_project_id = project["erp_project_id"]
            project_details = await resolve_project_details(external_project_id)
            outgoing_pm = await resolve_employee_details(outgoing_employee_id)
            incoming_pm = await resolve_employee_details(incoming_employee_id)

            # Get project history
            all_meetings = await conn.fetch(
                """SELECT meeting_date, meeting_type, summary FROM meeting_insights
                   WHERE project_id = $1
                   ORDER BY meeting_date DESC""",
                project_id
            )

            # Get calibration events
            calibration_events = await conn.fetch(
                """SELECT event_date, event_type, description FROM calibration_events
                   WHERE project_id = $1
                   ORDER BY event_date DESC""",
                project_id
            )

            # Get project memory
            memory = await conn.fetchrow(
                "SELECT * FROM project_memory WHERE project_id = $1",
                project_id
            )

            # Get milestones
            milestones = await conn.fetch(
                """SELECT name, status, due_date FROM project_milestones
                   WHERE project_id = $1
                   ORDER BY due_date ASC""",
                project_id
            )

            # Get health score
            health = await conn.fetchrow(
                """SELECT score, health_band FROM project_health_scores
                   WHERE project_id = $1
                   ORDER BY computed_at DESC LIMIT 1""",
                project_id
            )

            # Build context strings
            project_overview = f"Project: {project_details.get('name')}. Client: {project_details.get('client')}. "
            project_overview += f"Started: {project_details.get('start_date')}. "
            project_overview += f"Expected end: {project_details.get('end_date')}."

            milestone_status_text = "\n".join([
                f"- {m['name']}: {m['status']} (due {m['due_date']})"
                for m in milestones
            ]) if milestones else "No milestones"

            scope_and_tech = "See project documentation in R2."

            calibration_text = "\n".join([
                f"- {e['event_date']}: {e['event_type']} - {e['description']}"
                for e in calibration_events
            ]) if calibration_events else "None"

            risks_text = ""
            if memory and memory.get("risk_register"):
                risks = json.loads(memory["risk_register"])
                risks_text = "\n".join([f"- {r}" for r in risks[:5]])

            blockers_text = ""
            if memory and memory.get("blocker_log"):
                blockers = json.loads(memory["blocker_log"])
                blockers_text = "\n".join([
                    f"- {b.get('description')}: {(datetime.utcnow() - datetime.fromisoformat(b.get('raised_date', ''))).days} days old"
                    for b in blockers if not b.get("resolved_date")
                ][:5])

            relationship_narrative = ""
            if memory and memory.get("relationship_trajectory"):
                traj = json.loads(memory["relationship_trajectory"])
                relationship_narrative = traj.get("narrative", "Stable relationship with client")

            stakeholders_text = ", ".join([
                s.get("name", s.get("employee_id", "Unknown"))
                for s in (project_details.get("stakeholders", []) if isinstance(project_details.get("stakeholders"), list) else [])
            ]) or "TBD"

            # Build KT prompt
            prompt = build_kt_prompt(
                project_id=project_id,
                project_name=project_details.get("name", project_id),
                client_name=project_details.get("client", "Unknown"),
                start_date=project_details.get("start_date", "N/A"),
                end_date=project_details.get("end_date", "N/A"),
                health_score=health["score"] if health else 75,
                health_status=health["health_band"] if health else "amber",
                outgoing_pm=outgoing_pm.get("name") if outgoing_pm else outgoing_employee_id,
                incoming_pm=incoming_pm.get("name") if incoming_pm else incoming_employee_id,
                effective_date=effective_date,
                project_overview=project_overview,
                milestone_status=milestone_status_text,
                scope_and_tech=scope_and_tech,
                key_decisions="See calibration events and project memory",
                calibration_events=calibration_text,
                primary_stakeholder=project_details.get("stakeholders", [None])[0] if project_details.get("stakeholders") else "TBD",
                stakeholders=stakeholders_text,
                relationship_narrative=relationship_narrative,
                risks_and_mitigations=risks_text,
                open_blockers=blockers_text,
                pending_deliverables="Review project_milestones table",
                team_info=f"Outgoing PM: {outgoing_pm.get('name') if outgoing_pm else 'N/A'}",
                first_actions="Review recent meeting notes and call with outgoing PM"
            )

            # Generate KT document via Claude
            kt_content = "ERROR: Could not generate KT document"
            if claude_client:
                try:
                    response = claude_client.messages.create(
                        model=ANTHROPIC_MODEL,
                        max_tokens=3000,
                        system_prompt="You are a senior project documentation specialist. Generate comprehensive markdown KT documents.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    kt_content = response.content[0].text
                    log.info(f"Generated KT document for {project_id} via Claude")
                except Exception as e:
                    log.error(f"Claude error generating KT: {e}")
            else:
                log.warning("Claude client not available, using stub KT document")
                kt_content = f"""# Knowledge Transfer: {project_details.get('name')}

## Overview
{project_overview}

## Current Status
- Health: {health['health_band'] if health else 'amber'}
- Score: {health['score'] if health else 75}/100

## Milestones
{milestone_status_text}

## Key Risks
{risks_text or "None"}

## Team Contacts
{stakeholders_text}

## Next Steps
1. Review all recent meeting notes
2. Call with outgoing PM
3. Meet with client stakeholders
4. Review project memory and decisions
"""

            # Upload to R2
            r2 = get_r2_client()
            filename = f"kt_document_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"
            r2_key = await r2.upload_document(
                project_id=project_id,
                doc_type="kt_document",
                filename=filename,
                content=kt_content.encode("utf-8"),
                version="v1.0"
            )

            # Insert project_documents
            doc_id = f"kt_{project_id}_{datetime.utcnow().strftime('%Y%m%d')}"
            await conn.execute(
                """INSERT INTO project_documents
                   (project_id, doc_type, version, status, source, r2_key)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                project_id,
                "kt_document",
                "v1.0",
                "draft",
                "generated",
                r2_key
            )

            # Send to incoming PM via Slack
            slack_posted = False
            if incoming_pm and incoming_pm.get("email"):
                try:
                    slack_posted = await send_document_ready(
                        project_id=external_project_id,
                        doc_type="kt_document",
                        r2_url=f"https://r2.example.com/{r2_key}",
                        pm_email=incoming_pm.get("email")
                    )
                except Exception as e:
                    log.warning(f"Could not post KT to Slack: {e}")

            # Log action
            await conn.execute(
                """INSERT INTO agent_actions
                   (project_id, action_type, payload, triggered_by, status)
                   VALUES ($1, $2, $3, $4, $5)""",
                project_id,
                "kt_document_generated",
                f"outgoing={outgoing_employee_id}, incoming={incoming_employee_id}",
                "team_change",
                "success"
            )

            return {
                "status": "ok",
                "project_id": project_id,
                "document_id": doc_id,
                "r2_url": r2_key,
                "slack_posted": slack_posted
            }

        finally:
            if conn:
                await release_connection(conn)

    except Exception as e:
        log.error(f"KT document generation failed for {project_id}: {e}", exc_info=True)
        return None
