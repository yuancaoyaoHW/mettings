"""Pydantic/SQL models for minutes, topics, attachments (optional)."""
from typing import Optional

from pydantic import BaseModel


class MeetingMeta(BaseModel):
    """Meeting identifier."""

    meeting_type: Optional[str] = None
    meeting_name: Optional[str] = None
    venue_name: Optional[str] = None
    meeting_id: Optional[str] = None


class ChunkRef(BaseModel):
    """One chunk from vector store."""

    pk: Optional[int] = None
    source: str = ""
    type: str = ""
    level1: str = ""
    level2: str = ""
    topic: str = ""
    author: str = ""
    time: str = ""
    text: str = ""
