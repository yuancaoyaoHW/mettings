"""请求/响应 Pydantic 模型（对外契约）。"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RealtimeSpeakerInput(BaseModel):
    """当前片段的人脸/声纹/会场识别结果（由外部服务传入）。"""

    face_result: Optional[Any] = None
    voice_result: Optional[Any] = None
    venue_name: Optional[str] = None


class MinutesRequest(BaseModel):
    """智能纪要生成的结构化请求。"""

    meeting_type: Optional[str] = None
    meeting_name: Optional[str] = None
    venue_name: Optional[str] = None
    meeting_id: Optional[str] = None
    topics: List[str] = Field(default_factory=list)  # 议题列表
    person_names: List[str] = Field(default_factory=list)
    oral_names: List[str] = Field(default_factory=list)  # 口头称呼
    draft_text: Optional[str] = None  # 本次会议口水稿全文
    draft_segments_by_topic: Optional[Dict[str, str]] = None  # 已按议题切好的口水稿
    realtime_speaker: Optional[RealtimeSpeakerInput] = None
    open_issues: List[str] = Field(default_factory=list)
    conclusions: List[str] = Field(default_factory=list)
    options: Optional[Dict[str, Any]] = None


class ReferenceItem(BaseModel):
    """单条参考片段（用于生成与溯源）。"""

    pk: Optional[int] = None
    score: float = 0.0
    page_content: str = ""
    source: str = ""  # minutes / attachment / draft
    level1: str = ""
    level2: str = ""
    author: str = ""
    time: str = ""
    version: str = ""
    topic: str = ""


class ErrorItem(BaseModel):
    """单条错误信息。"""

    code: str = ""
    message: str = ""


class MinutesResponse(BaseModel):
    """智能纪要的结构化响应。"""

    minutes_content: str = ""  # 生成的纪要正文
    references: List[ReferenceItem] = Field(default_factory=list)
    resolved_speakers: List[str] = Field(default_factory=list)
    mapped_terms: List[str] = Field(default_factory=list)
    errors: List[ErrorItem] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    partial: bool = False  # 是否部分成功（有未完成项）
