"""
LLM Prompt for Weekly Plan Generation
Used by cortex/services/weekly_plan.py
"""

WEEKLY_PLAN_SYSTEM_PROMPT = """You are a senior project manager planning weekly execution.
Generate a concise, actionable weekly plan based on project context.

Output format: YAML
Do not include markdown formatting or triple backticks.
Just output the YAML directly."""

WEEKLY_PLAN_USER_PROMPT = """
Generate a weekly plan for project: {project_id}

PROJECT CONTEXT:
- Name: {project_name}
- Client: {client_name}
- Current Health: {health_score}/100 ({health_status})
- Completion Rate (this week): {completion_rate}%

UPCOMING MILESTONES (next 2 weeks):
{upcoming_milestones}

OPEN RISKS (top 3):
{open_risks}

CURRENT BLOCKERS:
{blockers}

TEAM:
- PM: {pm_name}
- POC Lead: {poc_name}

INSTRUCTIONS:
1. Generate 3-5 key focus areas for this week
2. Create 5-10 specific, actionable POC todos (tasks to hand off to CELL)
3. List any documents due this week
4. Flag risks that need monitoring
5. Add a brief recommendation for next week

Output format:
---
focus_areas:
  - area 1
  - area 2
  - area 3

poc_todos:
  - task: "Description"
    priority: "high|medium|low"
    assignee: "POC name or role"
    due_date: "{due_date}"
  - ...

documents_due:
  - "Document 1"
  - "Document 2"

risks_to_watch:
  - risk: "Description"
    impact: "high|medium|low"
    mitigation: "Action to take"
  - ...

recommendation: "Brief recommendation for next week and key success metrics"
---
"""

def build_weekly_plan_prompt(
    project_id: str,
    project_name: str,
    client_name: str,
    health_score: int,
    health_status: str,
    completion_rate: float,
    upcoming_milestones: str,
    open_risks: str,
    blockers: str,
    pm_name: str,
    poc_name: str,
    due_date: str
) -> str:
    """Build the complete weekly plan prompt"""
    return WEEKLY_PLAN_USER_PROMPT.format(
        project_id=project_id,
        project_name=project_name,
        client_name=client_name,
        health_score=health_score,
        health_status=health_status,
        completion_rate=int(completion_rate * 100),
        upcoming_milestones=upcoming_milestones or "None scheduled",
        open_risks=open_risks or "None",
        blockers=blockers or "None",
        pm_name=pm_name or "TBD",
        poc_name=poc_name or "TBD",
        due_date=due_date
    )
