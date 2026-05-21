"""
CORTEX NERVE Webhook Router
Receives IRIS extraction.complete events and triggers the full ingest pipeline.
"""

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import logging
from datetime import date, datetime
from cortex.models.schemas import NERVEEvent
from cortex.models.db import normalize_project_id, create_or_get_project
from cortex.services.ingest import ingest_meeting_insights
from cortex.services.memory import stitch_meeting_memory
from cortex.services.narrative import update_narrative
from cortex.services.health import compute_health_score
from cortex.services.drift import detect_milestone_drift
from cortex.services.enrich import write_enriched_yaml
from cortex.services.triggers import process_post_ingest_triggers

log = logging.getLogger("cortex.nerve")

router = APIRouter(prefix="/cortex", tags=["NERVE"])

@router.post("/ingest-nerve")
async def ingest_nerve(
    event: NERVEEvent,
    x_api_key: str = Header(None)
):
    """
    IRIS sends NERVE events here after extraction is complete.
    Triggers the full 7-step ingest pipeline.

    Pipeline:
      1. INGEST — parse, validate, embed insights
      2. MEMORY STITCH — cross-meeting narrative
      3. NARRATIVE UPDATE — LLM relationship trajectory
      4. HEALTH SCORE — deterministic scoring
      5. MILESTONE DRIFT — detect delays
      6. ENRICH YAML — write insights_enriched.yaml
      7. CONDITIONAL TRIGGERS — action briefs, docs, alerts
    """
    try:
        project_id = event.project_id
        meeting_id = event.meeting_id

        # Normalize or create the project so the full pipeline uses internal UUIDs.
        internal_project_id = await normalize_project_id(project_id)
        if not internal_project_id:
            log.warning(f"Project {project_id} not found. Creating local stub project record.")
            created_project = await create_or_get_project(
                erp_project_id=project_id,
                project_name=f"Local stub project {project_id}",
                project_type="client",
                client_id=None,
                pm_employee_id="local-pm",
                start_date=None,
                end_date=None,
            )
            internal_project_id = created_project["id"]
        project_id = internal_project_id

        log.info(f"NERVE event received: {project_id} / {meeting_id}")

        # ─────────────────────────────────────────────────────────────────
        # Step 1: INGEST
        # ─────────────────────────────────────────────────────────────────
        ingest_result = await ingest_meeting_insights(
            project_id,
            meeting_id,
            insights_data=event.insights.dict() if event.insights else None,
            meeting_artifacts=event.meeting_artifacts,
            meeting_date=event.meeting_date
        )
        if not ingest_result:
            log.error(f"Ingest failed for {meeting_id}")
            raise HTTPException(status_code=500, detail="Ingest failed")

        if ingest_result.get("action") == "skipped":
            log.info(f"Meeting already ingested. Returning.")
            return {"status": "skipped", "meeting_id": meeting_id}

        insight_id = ingest_result["id"]
        log.info(f"✓ Step 1: Ingested {meeting_id}")

        # ─────────────────────────────────────────────────────────────────
        # Step 2: MEMORY STITCH
        # ─────────────────────────────────────────────────────────────────
        memory_result = await stitch_meeting_memory(project_id, insight_id)
        if not memory_result:
            log.error(f"Memory stitch failed for {project_id}")
            # Don't fail the whole pipeline, but log it
        else:
            log.info(f"✓ Step 2: Memory stitched for {project_id}")

        # ─────────────────────────────────────────────────────────────────
        # Step 3: NARRATIVE UPDATE (LLM)
        # ─────────────────────────────────────────────────────────────────
        narrative_result = await update_narrative(project_id)
        if not narrative_result:
            log.warning(f"Narrative update failed for {project_id}")
        else:
            log.info(f"✓ Step 3: Narrative updated for {project_id}")

        # ─────────────────────────────────────────────────────────────────
        # Step 4: HEALTH SCORE
        # ─────────────────────────────────────────────────────────────────
        health_result = await compute_health_score(project_id, insight_id)
        if not health_result:
            log.warning(f"Health score computation failed for {project_id}")
            health_score = None
        else:
            health_score = health_result.get("score")
            log.info(f"✓ Step 4: Health score = {health_score} ({health_result.get('band')})")

        # ─────────────────────────────────────────────────────────────────
        # Step 5: MILESTONE DRIFT
        # ─────────────────────────────────────────────────────────────────
        drift_result = await detect_milestone_drift(project_id)
        if not drift_result:
            log.warning(f"Milestone drift detection failed for {project_id}")
        else:
            log.info(f"✓ Step 5: Milestone drift checked")

        # ─────────────────────────────────────────────────────────────────
        # Step 6: ENRICH YAML
        # ─────────────────────────────────────────────────────────────────
        enrich_result = await write_enriched_yaml(project_id, insight_id)
        if not enrich_result:
            log.warning(f"YAML enrichment failed for {project_id}")
        else:
            log.info(f"✓ Step 6: Enriched YAML written")

        # ─────────────────────────────────────────────────────────────────
        # Step 7: CONDITIONAL TRIGGERS
        # ─────────────────────────────────────────────────────────────────
        trigger_result = await process_post_ingest_triggers(project_id, insight_id)
        if trigger_result:
            log.info(f"✓ Step 7: Triggers processed: {trigger_result}")

        # Return success
        return {
            "status": "success",
            "project_id": project_id,
            "meeting_id": meeting_id,
            "health_score": health_score,
            "steps_completed": 7
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"NERVE pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")
