"""Request/response Pydantic models (public contract)."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RealtimeSpeakerInput(BaseModel):
    """Current segment face/voice/venue result from external service."""

    face_result: Optional[Any] = None
    voice_result: Optional[Any] = None
    venue_name: Optional[str] = None


class MinutesRequest(BaseModel):
    """Structured request for smart minutes generation."""

    meeting_type: Optional[str] = None
    meeting_name: Optional[str] = None
    venue_name: Optional[str] = None
    meeting_id: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    person_names: List[str] = Field(default_factory=list)
    oral_names: List[str] = Field(default_factory=list)
    draft_text: Optional[str] = None
    draft_segments_by_topic: Optional[Dict[str, str]] = None
    realtime_speaker: Optional[RealtimeSpeakerInput] = None
    open_issues: List[str] = Field(default_factory=list)
    conclusions: List[str] = Field(default_factory=list)
    options: Optional[Dict[str, Any]] = None


class ReferenceItem(BaseModel):
    """One reference chunk used for generation."""

    pk: Optional[int] = None
    score: float = 0.0
    page_content: str = ""
    source: str = ""
    level1: str = ""
    level2: str = ""
    author: str = ""
    time: str = ""
    version: str = ""
    topic: str = ""


class ErrorItem(BaseModel):
    """Single error entry."""

    code: str = ""
    message: str = ""


class MinutesResponse(BaseModel):
    """Structured response from smart minutes."""

    minutes_content: str = ""
    references: List[ReferenceItem] = Field(default_factory=list)
    resolved_speakers: List[str] = Field(default_factory=list)
    mapped_terms: List[str] = Field(default_factory=list)
    errors: List[ErrorItem] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    partial: bool = False
