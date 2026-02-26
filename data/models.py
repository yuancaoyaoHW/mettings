"""纪要/议题/附件等 Pydantic 或持久化模型。"""
from typing import Optional

from pydantic import BaseModel


class MeetingMeta(BaseModel):
    """会议标识。"""

    meeting_type: Optional[str] = None
    meeting_name: Optional[str] = None
    venue_name: Optional[str] = None
    meeting_id: Optional[str] = None


class ChunkRef(BaseModel):
    """向量库中的单条 chunk。"""

    pk: Optional[int] = None
    source: str = ""  # minutes / attachment / draft
    type: str = ""
    level1: str = ""
    level2: str = ""
    topic: str = ""
    author: str = ""
    time: str = ""
    text: str = ""
