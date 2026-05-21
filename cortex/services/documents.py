"""
CORTEX Documents Service
Generates documents: status reports, KT docs, milestone deliverables
Uses hardcoded templates + GROQ for filling
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

from cortex.config import GROQ_API_KEY, GROQ_MODEL
from cortex.models.schemas import DocumentRequest, DocumentResponse
from cortex.models.db import get_connection, release_connection, normalize_project_id
from cortex.services.templates import load_template

log = logging.getLogger("cortex.documents")

try:
    from groq import Groq
    if GROQ_API_KEY:
        groq_client = Groq(api_key=GROQ_API_KEY)
    else:
        groq_client = None
except Exception as e:
    log.warning(f"Could not initialize Groq client: {e}")
    groq_client = None


async def get_project_summary(project_id: str) -> Dict[str, Any]:
    """Get project summary for document context"""
    try:
        conn = await get_connection()

        # Get health
        health = await conn.fetchrow(
            "SELECT score, health_band FROM project_health_scores WHERE project_id = $1 ORDER BY computed_at DESC LIMIT 1",
            project_id
        )

        # Get meetings
        meetings = await conn.fetch(
            """SELECT meeting_id, meeting_date, meeting_type, summary
               FROM meeting_insights
               WHERE project_id = $1
               ORDER BY meeting_date DESC
               LIMIT 5""",
            project_id
        )

        # Get memory
        memory = await conn.fetchrow(
            "SELECT sentiment_history, risk_register FROM project_memory WHERE project_id = $1",
            project_id
        )

        return {
            "health": {
                "score": health["score"] if health else 75,
                "status": health["health_band"] if health else "amber"
            },
            "meetings": [dict(m) for m in (meetings or [])],
            "risks": json.loads(memory["risk_register"]) if memory and memory["risk_register"] else [],
            "sentiment": json.loads(memory["sentiment_history"]) if memory and memory["sentiment_history"] else []
        }
    except Exception as e:
        log.error(f"Error getting project summary: {e}")
        return {"health": {"score": 75, "status": "amber"}, "meetings": [], "risks": [], "sentiment": []}




async def generate_document(request: DocumentRequest, doc_type: str) -> DocumentResponse:
    """
    Generate a document:
    1. Load template from R2 (or hardcoded fallback)
    2. Get project context
    3. Fill template with data using GROQ
    4. Upload to R2 and return
    """
    project_id = request.project_id
    log.info(f"Generating document: {project_id} / {doc_type}")

    # Get summary
    summary = await get_project_summary(project_id)

    # Load template from R2
    try:
        template = await load_template(doc_type)
    except Exception as e:
        log.error(f"Failed to load template: {e}")
        template = None

    if not template:
        log.error(f"Could not load template for {doc_type}")
        return DocumentResponse(
            project_id=project_id,
            document_type=doc_type,
            content="ERROR: Could not load template",
            file_path="",
            version=1,
            generated_at=datetime.utcnow()
        )

    # Prepare template variables
    health = summary.get("health", {})
    score = health.get("score", 75)
    status = health.get("status", "amber")
    risks = summary.get("risks", [])
    meetings = summary.get("meetings", [])
    sentiment = summary.get("sentiment", [])

    # Build context for GROQ
    context = {
        "project_id": project_id,
        "generated_date": datetime.now().strftime('%Y-%m-%d'),
        "health_score": score,
        "health_status": status.upper(),
        "risks_count": len(risks),
        "blockers_count": 0,  # Could fetch from database
        "delivery_status": "On Track",
        "recent_activities": f"{len(meetings)} recent meetings",
        "upcoming_milestones": "Check project milestones",
        "risks_summary": "\n".join([f"- {r}" for r in risks[:3]]) if risks else "No open risks",
        "recommendations": "Monitor health score weekly",
    }

    # Use GROQ to fill template or fallback to simple injection
    use_groq = groq_client and GROQ_API_KEY

    if use_groq:
        try:
            prompt = f"""Fill in the following template with the given context.
Template variable reference:
{template}

Context (use these to fill the template):
{json.dumps(context, indent=2)}

Rules:
1. Replace all {{variable}} placeholders with actual values from context
2. If context doesn't have a value, provide reasonable defaults
3. Keep markdown formatting intact
4. Return only the filled template, no extra text

Fill the template now:"""

            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional project documentation specialist. Fill templates accurately."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.3
            )
            content = response.choices[0].message.content
            log.info(f"Document generated via GROQ for {project_id}/{doc_type}")
        except Exception as e:
            log.error(f"GROQ error: {e}. Using simple template injection.")
            content = template.format(**context)
    else:
        log.debug("GROQ not available, using simple template injection")
        content = template.format(**context)

    filename = f"{doc_type}_v1.0_{datetime.now().strftime('%Y%m%d')}.md"
    document_path = f"generated/{project_id}/{filename}"
    log.info(f"Document generated at {document_path}")

    return DocumentResponse(
        project_id=project_id,
        document_type=doc_type,
        content=content,
        file_path=document_path,
        version=1,
        generated_at=datetime.utcnow()
    )


async def handle_document_upload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist an uploaded document record reported by the intranet.

    Expected keys: project_id, document_type, r2_key, source (optional), uploader (optional)
    Returns: dict with inserted document id and r2_key
    """
    project_id = payload.get("project_id")
    doc_type = payload.get("document_type")
    r2_key = payload.get("r2_key")
    source = payload.get("source", "manual_upload")
    uploader = payload.get("uploader")
    extracted_data = payload.get("extracted_data")

    if not project_id or not doc_type or not r2_key:
        raise ValueError("project_id, document_type and r2_key are required")

    # Normalize external project id to internal UUID
    internal_project_id = await normalize_project_id(project_id)
    if not internal_project_id:
        raise ValueError(f"Project not found: {project_id}")

    # Ensure the document path is not empty and belongs to the project prefix
    if not r2_key.startswith(f"projects/{project_id}/") and not r2_key.startswith(f"projects/{internal_project_id}/"):
        raise ValueError("document path must begin with the project prefix")

    conn = await get_connection()
    try:
        doc_id = await conn.fetchval(
            """
            INSERT INTO project_documents (
                project_id, doc_type, version, status, source, r2_key, extracted_data, notes, generated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            RETURNING id
            """,
            internal_project_id,
            doc_type,
            "v1.0",
            "uploaded",
            source,
            r2_key,
            extracted_data if extracted_data is not None else {},
            f"uploaded_by={uploader}" if uploader else None
        )
        log.info(f"Stored document for {project_id}: {doc_id}")
        return {"id": str(doc_id), "r2_key": r2_key}
    finally:
        await release_connection(conn)
