"""
CORTEX Documents Router
Generate and manage project documents (reports, KT, deliverables)
"""

from fastapi import APIRouter, HTTPException, Header
import logging
from cortex.models.schemas import DocumentRequest, DocumentResponse
from cortex.models.db import get_connection, release_connection
from cortex.services.documents import generate_document, handle_document_upload
from pydantic import BaseModel
from typing import Optional, Dict, Any
from cortex.config import CORTEX_API_KEY

log = logging.getLogger("cortex.documents")

router = APIRouter(prefix="/cortex", tags=["DOCUMENTS"])


class DocumentUploadPayload(BaseModel):
    project_id: str
    document_type: str
    r2_key: str
    source: Optional[str] = "manual_upload"
    uploader: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None

    class Config:
        schema_extra = {
            "example": {
                "project_id": "erp-1234",
                "document_type": "sow",
                "r2_key": "projects/erp-1234/source-docs/statement_of_work.pdf",
                "source": "manual_upload",
                "uploader": "pm@example.com",
                "extracted_data": {"title": "Statement of Work"}
            }
        }


@router.post("/document-upload")
async def document_upload(payload: DocumentUploadPayload, x_api_key: Optional[str] = Header(None)):
    """Register a document that was uploaded to R2 by the intranet.

    Example payload:
    {
      "project_id": "erp-1234",
      "document_type": "sow",
      "r2_key": "projects/erp-1234/source-docs/statement_of_work.pdf",
      "source": "manual_upload",
      "uploader": "pm@example.com"
    }

    Requires `x-api-key` header when `CORTEX_API_KEY` is configured.
    """
    # API key enforcement
    if CORTEX_API_KEY and x_api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

    try:
        result = await handle_document_upload(payload.dict())
        return {"status": "ok", "document_id": result["id"], "r2_key": result["r2_key"]}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        log.error(f"Document upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class DocumentApprovalPayload(BaseModel):
    document_id: str
    approved_by: str
    notes: Optional[str] = None


@router.post("/documents/approve")
async def approve_document(payload: DocumentApprovalPayload, x_api_key: Optional[str] = Header(None)):
    """Mark an uploaded document as approved."""
    if CORTEX_API_KEY and x_api_key != CORTEX_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

    conn = None
    try:
        conn = await get_connection()
        await conn.execute(
            """
            UPDATE project_documents
            SET approved = TRUE, approved_at = NOW(), approved_by = $1, approval_notes = $2
            WHERE id = $3
            """,
            payload.approved_by,
            payload.notes,
            payload.document_id
        )
        return {"status": "ok", "document_id": payload.document_id}
    except Exception as e:
        log.error(f"Document approval error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            await release_connection(conn)


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
