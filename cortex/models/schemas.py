"""
Pydantic schemas for request/response validation
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum

# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class ProjectType(str, Enum):
    CLIENT = "client"
    INTERNAL = "internal"

class ProjectStatus(str, Enum):
    PRE_PROJECT = "pre_project"
    ACTIVE = "active"
    AT_RISK = "at_risk"
    ON_HOLD = "on_hold"
    CLOSED = "closed"

class MeetingType(str, Enum):
    STANDUP = "standup"
    CLIENT_CALL = "client-call"
    MILESTONE_REVIEW = "milestone-review"
    INTERNAL = "internal"
    VENDOR = "vendor"
    OTHER = "other"

class HealthBand(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"

class DocumentType(str, Enum):
    SOW = "sow"
    SOLUTION_ARCHITECTURE = "solution_architecture"
    TIMELINE = "timeline"
    PROPOSAL = "proposal"
    MILESTONE_DELIVERABLE = "milestone_deliverable"
    STATUS_REPORT = "status_report"
    KT_DOCUMENT = "kt_document"
    ONBOARDING_BRIEF = "onboarding_brief"
    RENEWAL_PROPOSAL = "renewal_proposal"
    OTHER = "other"

# ─────────────────────────────────────────────────────────────────────────────
# INGEST / NERVE
# ─────────────────────────────────────────────────────────────────────────────

class NERVEEvent(BaseModel):
    """IRIS sends this to trigger CORTEX ingestion"""
    event_type: str  # "iris.extraction.complete"
    project_id: str
    meeting_id: str
    meeting_date: date
    timestamp: datetime
    insights: Optional[InsightsYAML] = None
    meeting_artifacts: Optional[Dict[str, Any]] = None  # transcripts, EODs, docs, etc.

class InsightsYAML(BaseModel):
    """IRIS output structure that CORTEX ingests"""
    meeting_id: str
    project_id: str
    meeting_type: MeetingType
    meeting_date: date
    summary: str

    risks: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []
    sentiment: Dict[str, Any] = {}
    milestones: List[Dict[str, Any]] = []

    previous_meeting_ref: Optional[Dict[str, Any]] = None  # CORTEX fills
    relationship_trajectory: Optional[Dict[str, Any]] = None  # CORTEX fills

    class Config:
        extra = "allow"

# ─────────────────────────────────────────────────────────────────────────────
# HEALTH SCORE
# ─────────────────────────────────────────────────────────────────────────────

class HealthScoreComponents(BaseModel):
    sentiment_penalty: int = 0
    open_risks_penalty: int = 0
    blocker_penalty: int = 0
    milestone_penalty: int = 0
    trajectory_penalty: int = 0
    velocity_penalty: int = 0

class HealthScoreResult(BaseModel):
    score: int = Field(..., ge=0, le=100)
    band: HealthBand
    components: HealthScoreComponents

class ProjectHealthScore(BaseModel):
    project_id: str
    score: int
    band: HealthBand
    components: HealthScoreComponents
    computed_after_meeting_id: Optional[str] = None
    computed_at: datetime

# ─────────────────────────────────────────────────────────────────────────────
# PROJECT MEMORY
# ─────────────────────────────────────────────────────────────────────────────

class MeetingContext(BaseModel):
    meeting_id: str
    date: date
    meeting_type: MeetingType
    summary: str
    sentiment_score: float
    open_actions: List[str] = []
    unresolved_blockers: List[str] = []

class SentimentHistory(BaseModel):
    date: date
    score: float
    label: str
    drivers: List[str] = []
    meeting_id: str

class Risk(BaseModel):
    id: str
    description: str
    severity: str  # "high", "medium", "low"
    status: str  # "open", "mitigated", "resolved"
    raised_date: date
    resolved_date: Optional[date] = None
    source_meeting_id: str

class Blocker(BaseModel):
    id: str
    description: str
    raised_date: date
    resolved_date: Optional[date] = None
    resolved_by: Optional[str] = None
    days_open: int = 0

class ProjectMemory(BaseModel):
    project_id: str

    # Short-term: rolling 3-meeting window
    recent_context: List[MeetingContext] = []

    # Long-term: narrative
    relationship_trajectory: Optional[Dict[str, Any]] = None

    # History tracking
    sentiment_history: List[SentimentHistory] = []
    risk_register: List[Risk] = []
    blocker_log: List[Blocker] = []

    updated_at: datetime

# ─────────────────────────────────────────────────────────────────────────────
# CHAT
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    project_id: str
    question: str
    user_role: str = "pm"  # pm, director, ba, apm
    conversation_history: List[ChatMessage] = []

class ChatResponse(BaseModel):
    answer: str
    project_id: str
    user_role: str
    health_score: Optional[int] = None
    status: Optional[str] = None  # green, amber, red
    confidence: float = 0.8
    sources: List[str] = []  # meeting IDs used for context
    generated_at: datetime

# EOD reporting and weekly EOD health have been removed.

# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENTS
# ─────────────────────────────────────────────────────────────────────────────

class DocumentRequest(BaseModel):
    project_id: str
    document_type: str  # status_report, kt_document, milestone_deliverable
    meeting_id: Optional[str] = None  # for specific meeting context
    milestone_name: Optional[str] = None  # for milestone docs

class DocumentResponse(BaseModel):
    project_id: str
    document_type: str
    content: str
    file_path: Optional[str] = None
    version: int = 1
    generated_at: datetime

class HealthCheckResponse(BaseModel):
    status: str
    message: str
    database_connected: bool
    version: str = "0.1.0"
