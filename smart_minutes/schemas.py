"""请求/响应 Pydantic 模型（对外契约）。"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RealtimeSpeakerInput(BaseModel):
    """当前片段的人脸/声纹/会场识别结果（由外部服务传入）。"""

    face_result: Optional[Any] = None
    voice_result: Optional[Any] = None
    venue_name: Optional[str] = None


class SpeakerCandidate(BaseModel):
    """发言人候选及其置信度。"""

    name: str = ""
    confidence: float = 0.0
    source: str = ""  # face / voice / venue / mapping


class SpeakerResolution(BaseModel):
    """多模态融合后的发言人归属结果。"""

    resolved_name: Optional[str] = None
    confidence: float = 0.0
    candidates: List[SpeakerCandidate] = Field(default_factory=list)
    status: str = "unknown"  # resolved / unknown / conflict
    conflict_reason: str = ""


class MeetingInfo(BaseModel):
    """结构化会议基本信息。"""

    meeting_type: Optional[str] = None
    meeting_name: Optional[str] = None
    meeting_time: Optional[str] = None
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    attendee_roles: Dict[str, str] = Field(default_factory=dict)
    host: Optional[str] = None
    recorder: Optional[str] = None


class ActionItem(BaseModel):
    """结构化待办项。"""

    content: str = ""
    owner: Optional[str] = None
    deadline: Optional[str] = None
    status: Optional[str] = None
    source_ref_ids: List[str] = Field(default_factory=list)


class TopicSection(BaseModel):
    """结构化议题段。"""

    topic_name: str = ""
    summary: str = ""
    key_points: List[str] = Field(default_factory=list)
    conclusions: List[str] = Field(default_factory=list)
    open_issues: List[str] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    source_ref_ids: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None


class MaterialCitation(BaseModel):
    """材料引用与术语规范化信息。"""

    source_type: str = ""  # minutes / attachment / draft
    source_id: str = ""  # 历史纪要 ID、附件 ID 或片段 ID
    source_position: str = ""  # 页码、段落、chunk 索引等
    quote: str = ""
    topic_name: Optional[str] = None
    term_mappings: Dict[str, str] = Field(default_factory=dict)


class TraceabilityInfo(BaseModel):
    """关键信息的可追溯元数据。"""

    history_minutes_ids: List[str] = Field(default_factory=list)
    attachment_positions: List[str] = Field(default_factory=list)
    speaker_resolution: List[SpeakerResolution] = Field(default_factory=list)


class StructuredMinutesOutput(BaseModel):
    """可渲染、可追踪的结构化纪要结果。"""

    meeting_info: Optional[MeetingInfo] = None
    topics: List[TopicSection] = Field(default_factory=list)
    materials: List[MaterialCitation] = Field(default_factory=list)
    traceability: Optional[TraceabilityInfo] = None


class MinutesRequest(BaseModel):
    """智能纪要生成的结构化请求。"""

    meeting_type: Optional[str] = None
    meeting_name: Optional[str] = None
    project: Optional[str] = None
    department: Optional[str] = None
    organization: Optional[str] = None
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
    source_id: str = ""
    source_position: str = ""
    confidence: Optional[float] = None


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
    speaker_resolutions: List[SpeakerResolution] = Field(default_factory=list)
    structured_output: Optional[StructuredMinutesOutput] = None
