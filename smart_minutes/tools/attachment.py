"""附件工具：按会议取政策列表、按议题在附件内检索。"""
from typing import List

from smart_minutes.contracts import IRetrieval


def _to_ref(h: dict) -> dict:
    """hit 转 ref 字典。"""
    return {
        "pk": h.get("pk"),
        "score": h.get("score", 0.0),
        "page_content": h.get("page_content", h.get("text", "")),
        "source": h.get("source", ""),
        "level1": h.get("level1", ""),
        "level2": h.get("level2", ""),
        "author": h.get("author", ""),
        "time": h.get("time", ""),
        "version": h.get("version", ""),
        "topic": h.get("topic", ""),
        "source_id": h.get("source_id", ""),
        "source_position": h.get("source_position", ""),
        "confidence": h.get("confidence"),
    }


def get_attachments_by_meeting(
    retrieval: IRetrieval,
    meeting_type: str,
    meeting_name: str,
) -> List[dict]:
    """会议相关政策/附件列表：source=attachment、level1=会议类型/名。"""
    level1 = meeting_type or meeting_name or ""
    if not level1:
        return []
    hits = retrieval.search(
        query_text=level1,
        source_filter="attachment",
        level1_filter=level1,
        top_k=50,
    )
    return [_to_ref(h) for h in hits]


def search_attachments_by_topic(
    retrieval: IRetrieval,
    topic_name: str,
    query: str,
    top_k: int,
) -> List[dict]:
    if not topic_name:
        return []
    hits = retrieval.search(
        query_text=query or topic_name,
        source_filter="attachment",
        topic_filter=topic_name,
        top_k=top_k,
    )
    return [_to_ref(h) for h in hits]
