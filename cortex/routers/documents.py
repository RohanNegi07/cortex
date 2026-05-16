"""
CORTEX Documents Router
Generate and manage project documents (reports, KT, deliverables)
"""

from fastapi import APIRouter, HTTPException
import logging
from cortex.models.schemas import DocumentRequest, DocumentResponse
from cortex.services.documents import generate_document

log = logging.getLogger("cortex.documents")

router = APIRouter(prefix="/cortex", tags=["DOCUMENTS"])

@router.post("/documents/status-report", response_model=DocumentResponse)
async def generate_status_report(request: DocumentRequest):
    """Generate weekly status report"""
    try:
        result = await generate_document(request, "status_report")
        return result
    except Exception as e:
        log.error(f"Document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents/kt-document", response_model=DocumentResponse)
async def generate_kt_document(request: DocumentRequest):
    """Generate knowledge transfer document"""
    try:
        result = await generate_document(request, "kt_document")
        return result
    except Exception as e:
        log.error(f"Document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents/milestone-deliverable", response_model=DocumentResponse)
async def generate_milestone_doc(request: DocumentRequest):
    """Generate milestone deliverable document"""
    try:
        result = await generate_document(request, "milestone_deliverable")
        return result
    except Exception as e:
        log.error(f"Document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
