"""RAG 工具：按条件调用检索接口。"""
from typing import Any, List

from smart_minutes.contracts import IRetrieval


def _to_ref(hit: dict) -> dict:
    """单条 hit 转为统一 ref 字典。"""
    return {
        "pk": hit.get("pk"),
        "score": hit.get("score", 0.0),
        "page_content": hit.get("page_content", hit.get("text", "")),
        "source": hit.get("source", ""),
        "level1": hit.get("level1", ""),
        "level2": hit.get("level2", ""),
        "author": hit.get("author", ""),
        "time": hit.get("time", ""),
        "version": hit.get("version", ""),
        "topic": hit.get("topic", ""),
    }


def retrieve_latest_minutes_by_series(
    retrieval: IRetrieval,
    meeting_type: str,
    meeting_name: str,
    top_k: int,
) -> List[dict]:
    """同系列最新纪要：source=minutes、level1=会议类型/名，按 time 降序取 top_k。"""
    level1 = meeting_type or meeting_name or ""
    if not level1:
        return []
    hits = retrieval.search(
        query_text=level1,
        source_filter="minutes",
        level1_filter=level1,
        top_k=top_k * 2,
    )
    # 按 time 降序取 top_k
    with_time = [(h, h.get("time", "")) for h in hits]
    with_time.sort(key=lambda x: x[1], reverse=True)
    return [_to_ref(h) for h, _ in with_time[:top_k]]


def retrieve_by_topic(retrieval: IRetrieval, topic_name: str, top_k: int) -> List[dict]:
    if not topic_name:
        return []
    hits = retrieval.search(query_text=topic_name, topic_filter=topic_name, top_k=top_k)
    return [_to_ref(h) for h in hits]


def retrieve_by_person(retrieval: IRetrieval, person_name: str, top_k: int) -> List[dict]:
    if not person_name:
        return []
    hits = retrieval.search(query_text=person_name, author_filter=person_name, top_k=top_k)
    return [_to_ref(h) for h in hits]


def retrieve_similar_todos_or_issues(retrieval: IRetrieval, text: str, top_k: int) -> List[dict]:
    if not text:
        return []
    hits = retrieval.search(query_text=text, type_filter="open_issue", top_k=top_k)
    return [_to_ref(h) for h in hits]


def retrieve_similar_conclusions(retrieval: IRetrieval, text: str, top_k: int) -> List[dict]:
    if not text:
        return []
    hits = retrieval.search(query_text=text, type_filter="conclusion", top_k=top_k)
    return [_to_ref(h) for h in hits]


def retrieve_similar_topic_by_draft(retrieval: IRetrieval, draft_text: str, top_k: int) -> List[dict]:
    if not draft_text:
        return []
    hits = retrieval.search(
        query_text=draft_text[:2000],
        source_filter="draft",
        top_k=top_k,
    )
    return [_to_ref(h) for h in hits]
