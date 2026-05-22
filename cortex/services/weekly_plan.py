"""
Weekly Plan Generation Service
Generates PM plans every Monday 07:30, hands off POC todos to CELL.
"""

import logging
import json
import yaml
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from cortex.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from cortex.models.db import get_connection, release_connection
from cortex.integrations.cell_api import get_velocity_summary, push_tasks_to_cell
from cortex.integrations.intranet import resolve_project_details, resolve_employee_details
from cortex.llm.prompts.weekly_plan import build_weekly_plan_prompt

log = logging.getLogger("cortex.weekly_plan")

try:
    from anthropic import Anthropic
    if ANTHROPIC_API_KEY:
        claude_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    else:
        claude_client = None
except Exception as e:
    log.warning(f"Could not initialize Claude client: {e}")
    claude_client = None


async def generate_weekly_plan(
    project_id: str
) -> Optional[Dict[str, Any]]:
    """
    Generate weekly plan for a single project.
    Returns: {status, plan_id, plan_content, todos_pushed}
    """
    try:
        conn = await get_connection()
        try:
            # Get current week reference
            now = datetime.utcnow()
            week_ref = f"{now.year}-W{now.isocalendar()[1]:02d}"

            # Load project by internal UUID
            project = await conn.fetchrow(
                "SELECT * FROM projects WHERE id = $1",
                project_id
            )
            if not project:
                log.warning(f"Project {project_id} not found")
                return None

            external_project_id = project["erp_project_id"]
            project_details = await resolve_project_details(external_project_id)
            if not project_details:
                log.error(f"Project details unavailable for {external_project_id}")
                return None

            # Get velocity summary from CELL
            velocity = await get_velocity_summary(project_id, week_ref)
            if not velocity:
                log.error(f"Could not get velocity for {project_id}")
                return None

            # Get health score
            health = await conn.fetchrow(
                """SELECT score, health_band FROM project_health_scores
                   WHERE project_id = $1
                   ORDER BY computed_at DESC LIMIT 1""",
                project_id
            )
            health_score = health["score"] if health else 75
            health_status = health["health_band"] if health else "amber"

            # Get risks
            memory = await conn.fetchrow(
                "SELECT risk_register FROM project_memory WHERE project_id = $1",
                project_id
            )
            risks = []
            if memory and memory["risk_register"]:
                risks = json.loads(memory["risk_register"])[:3]
            risks_text = "\n".join([f"- {r}" for r in risks]) if risks else "None"

            # Get upcoming milestones
            milestones = await conn.fetch(
                """SELECT name, due_date FROM project_milestones
                   WHERE project_id = $1 AND status != 'completed'
                   ORDER BY due_date ASC LIMIT 3""",
                project_id
            )
            milestones_text = "\n".join(
                [f"- {m['name']} (due {m['due_date']})" for m in milestones]
            ) if milestones else "None"

            # Get blockers
            blocker_text = "None"  # Could fetch from project_memory

            # Get PM details
            pm_id = project_details.get("pm_id", "p-unknown")
            pm = await resolve_employee_details(pm_id)
            pm_name = pm.get("name") if pm else "TBD"

            week_start = (now - timedelta(days=now.weekday())).date()
            # Build LLM prompt
            prompt = build_weekly_plan_prompt(
                project_id=external_project_id,
                project_name=project_details.get("name", external_project_id),
                client_name=project_details.get("client", "Unknown"),
                health_score=health_score,
                health_status=health_status,
                completion_rate=velocity.get("completion_rate", 0.7),
                upcoming_milestones=milestones_text,
                open_risks=risks_text,
                blockers=blocker_text,
                pm_name=pm_name,
                poc_name="POC Team",
                due_date=(datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
            )

            # Generate plan via Claude
            plan_content = None
            if claude_client:
                try:
                    response = claude_client.messages.create(
                        model=ANTHROPIC_MODEL,
                        max_tokens=1500,
                        system="You are a senior PM planning execution. Output YAML format without markdown.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    plan_content = response.content[0].text
                    log.info(f"Generated weekly plan for {project_id} via Claude")
                except Exception as e:
                    log.error(f"Claude error generating plan: {e}")
            else:
                log.error("Claude client not available for weekly plan generation")

            if not plan_content:
                log.error(f"Weekly plan generation failed for {project_id}")
                return None

            # Parse plan YAML
            try:
                plan_yaml = yaml.safe_load(plan_content)
                if not isinstance(plan_yaml, dict):
                    log.error(f"Invalid weekly plan format generated for {project_id}")
                    return None
            except Exception as e:
                log.error(f"Could not parse plan YAML for {project_id}: {e}")
                return None

            # Insert pm_task_plans
            plan_id = f"plan_{project_id}_{week_ref}"
            await conn.execute(
                """INSERT INTO pm_task_plans
                   (project_id, week_start, plan_yaml, health_score_at_generation, velocity_data, sent_to_slack)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                project_id,
                week_start,
                yaml.safe_dump(plan_yaml),
                health_score,
                json.dumps(velocity),
                False
            )

            # Push POC todos to CELL
            poc_todos = plan_yaml.get("poc_todos", [])
            todos_pushed = False
            if poc_todos:
                todos_pushed = await push_tasks_to_cell(project_id, poc_todos, external_project_id=external_project_id)

            # Log action
            await conn.execute(
                """INSERT INTO agent_actions
                   (project_id, action_type, payload, triggered_by, status)
                   VALUES ($1, $2, $3, $4, $5)""",
                project_id,
                "weekly_plan_generated",
                f"week={week_ref}, todos={len(poc_todos)}",
                "scheduler",
                "success"
            )

            return {
                "status": "ok",
                "project_id": project_id,
                "plan_id": plan_id,
                "week_ref": week_ref,
                "plan_content": plan_content,
                "todos_pushed": todos_pushed,
            }

        finally:
            if conn:
                await release_connection(conn)

    except Exception as e:
        log.error(f"Weekly plan generation failed for {project_id}: {e}", exc_info=True)
        return None


async def generate_plans_for_all_projects() -> Dict[str, Any]:
    """
    Generate plans for all active projects.
    Called by scheduler Monday 07:30.
    """
    log.info("=== GENERATING WEEKLY PLANS FOR ALL PROJECTS ===")

    try:
        conn = await get_connection()
        try:
            # Get all active projects
            projects = await conn.fetch(
                "SELECT id FROM projects WHERE status = 'active'"
            )

            results = {
                "total": len(projects),
                "successful": 0,
                "failed": 0,
                "projects": []
            }

            for proj in projects:
                project_id = proj["id"]
                result = await generate_weekly_plan(project_id)

                if result and result.get("status") == "ok":
                    results["successful"] += 1
                    results["projects"].append({
                        "project_id": project_id,
                        "status": "ok",
                        "todos_pushed": result.get("todos_pushed")
                    })
                else:
                    results["failed"] += 1
                    results["projects"].append({
                        "project_id": project_id,
                        "status": "failed"
                    })

            log.info(f"Weekly plans completed: {results['successful']}/{results['total']} successful")
            return results

        finally:
            if conn:
                await release_connection(conn)

    except Exception as e:
        log.error(f"Weekly plan batch generation failed: {e}", exc_info=True)
        return {"total": 0, "successful": 0, "failed": 0, "projects": [], "error": str(e)}
