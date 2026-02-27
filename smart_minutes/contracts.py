"""智能纪要抽象接口（依赖倒置，便于注入与替换实现）。"""
from typing import Any, List, Optional, Protocol

from smart_minutes.schemas import SpeakerResolution


class IRetrieval(Protocol):
    """检索接口：按条件/查询返回 chunk 列表。"""

    def search(
        self,
        query_text: str,
        *,
        topic_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        level1_filter: Optional[str] = None,
        author_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[dict]:
        """混合检索（可带过滤），返回含 pk、score、page_content、source 等字段的 dict 列表。"""
        ...


class IMappingStore(Protocol):
    """映射查询接口：口头称呼→正式人名，会议类型→专业名词。"""

    def resolve_oral_to_formal(self, oral_name: str) -> Optional[str]:
        """口头/昵称 → 正式人名，未命中返回 None。"""
        ...

    def get_professional_terms(self, meeting_type: str, meeting_name: str) -> List[str]:
        """按会议类型/名称取专业名词，无则返回空列表。"""
        ...


class ISpeakerResolver(Protocol):
    """发言人融合接口：人脸/声纹/会场结果 → 正式人名。"""

    def resolve_speaker(
        self,
        face_result: Any = None,
        voice_result: Any = None,
        venue_name: Optional[str] = None,
    ) -> Optional[SpeakerResolution]:
        """多维度融合发言人，返回归属结果（含置信度/候选集）。"""
        ...
