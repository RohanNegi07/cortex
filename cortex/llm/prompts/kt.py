"""
LLM Prompt for KT Document Generation
Used by cortex/services/kt.py
"""

KT_SYSTEM_PROMPT = """You are a senior project documentation specialist preparing a knowledge transfer document.
Create a comprehensive handoff document for a PM transition that captures all critical project knowledge.
Be specific, factual, and actionable. Include all context needed for the incoming PM to take over smoothly."""

KT_USER_PROMPT = """
Generate a Knowledge Transfer Document for project: {project_id}

PROJECT BACKGROUND:
- Name: {project_name}
- Client: {client_name}
- Duration: {start_date} to {end_date}
- Current Status: {health_status} (Health Score: {health_score}/100)
- PM (outgoing): {outgoing_pm}
- PM (incoming): {incoming_pm}
- Effective Date: {effective_date}

PROJECT SUMMARY:
{project_overview}

MILESTONE STATUS:
{milestone_status}

SCOPE & ARCHITECTURE:
{scope_and_tech}

KEY DECISIONS MADE (and why):
{key_decisions}

CALIBRATION EVENTS (scope changes, rebaselines):
{calibration_events}

CLIENT RELATIONSHIP:
- Primary Stakeholder: {primary_stakeholder}
- Key Contacts: {stakeholders}
- Relationship Status: {relationship_narrative}

CRITICAL RISKS & MITIGATIONS:
{risks_and_mitigations}

OPEN BLOCKERS:
{open_blockers}

PENDING DELIVERABLES:
{pending_deliverables}

TEAM INFORMATION:
{team_info}

RECOMMENDED FIRST ACTIONS FOR INCOMING PM:
{first_actions}

INSTRUCTIONS:
Generate a markdown document with clear sections covering all the above categories.
Use professional tone. Be concise but thorough.
Include specific examples and timelines where relevant.
Focus on what the incoming PM needs to know to take over immediately.
"""

def build_kt_prompt(
    project_id: str,
    project_name: str,
    client_name: str,
    start_date: str,
    end_date: str,
    health_score: int,
    health_status: str,
    outgoing_pm: str,
    incoming_pm: str,
    effective_date: str,
    project_overview: str,
    milestone_status: str,
    scope_and_tech: str,
    key_decisions: str,
    calibration_events: str,
    primary_stakeholder: str,
    stakeholders: str,
    relationship_narrative: str,
    risks_and_mitigations: str,
    open_blockers: str,
    pending_deliverables: str,
    team_info: str,
    first_actions: str
) -> str:
    """Build the complete KT prompt"""
    return KT_USER_PROMPT.format(
        project_id=project_id,
        project_name=project_name,
        client_name=client_name,
        start_date=start_date,
        end_date=end_date,
        health_score=health_score,
        health_status=health_status,
        outgoing_pm=outgoing_pm,
        incoming_pm=incoming_pm,
        effective_date=effective_date,
        project_overview=project_overview or "N/A",
        milestone_status=milestone_status or "N/A",
        scope_and_tech=scope_and_tech or "N/A",
        key_decisions=key_decisions or "N/A",
        calibration_events=calibration_events or "None",
        primary_stakeholder=primary_stakeholder or "N/A",
        stakeholders=stakeholders or "N/A",
        relationship_narrative=relationship_narrative or "N/A",
        risks_and_mitigations=risks_and_mitigations or "None",
        open_blockers=open_blockers or "None",
        pending_deliverables=pending_deliverables or "None",
        team_info=team_info or "N/A",
        first_actions=first_actions or "Review project status and stakeholder alignment"
    )
