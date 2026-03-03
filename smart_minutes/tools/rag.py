"""RAG 工具：按条件调用检索接口。"""
import re
from typing import Any, Dict, List, Optional

from smart_minutes.contracts import IRetrieval


def _to_ref(hit: dict) -> dict:
    """单条 hit 转为统一 ref 字典（与 ingest 行、ReferenceItem 对齐）。"""
    return {
        "pk": hit.get("pk"),
        "score": hit.get("score", 0.0),
        "page_content": hit.get("page_content", hit.get("text", "")),
        "source": hit.get("source", ""),
        "type": hit.get("type", ""),
        "level1": hit.get("level1", ""),
        "level2": hit.get("level2", ""),
        "author": hit.get("author", ""),
        "time": hit.get("time", ""),
        "version": hit.get("version", ""),
        "topic": hit.get("topic", ""),
        "source_id": hit.get("source_id", ""),
        "source_position": hit.get("source_position", ""),
        "confidence": hit.get("confidence"),
        "owner": hit.get("owner", ""),
        "deadline": hit.get("deadline", ""),
    }


def _normalize_meeting_key(raw: str) -> str:
    """会议名称规范化：去日期/编号后缀，保留主干。"""
    if not raw:
        return ""
    text = raw.strip()
    text = re.sub(r"\d{4}[-/年]\d{1,2}([-/月]\d{1,2}[日]?)?", "", text)
    text = re.sub(r"[（(]第?\d+[次期届号]?[)）]", "", text)
    text = re.sub(r"第?\d+[次期届号]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -_")
    return text


def _to_people_set(value: Any) -> set[str]:
    """将不同格式的参会人字段归一为集合。"""
    if not value:
        return set()
    if isinstance(value, str):
        parts = re.split(r"[，,;；/|\s]+", value.strip())
        return {p.strip() for p in parts if p and p.strip()}
    if isinstance(value, list):
        return {str(x).strip() for x in value if str(x).strip()}
    return set()


def _hit_attendees(hit: dict) -> set[str]:
    """从检索命中中提取参会人集合（兼容多种字段名）。"""
    keys = ("attendees", "participant_names", "participants", "attendee_names")
    people: set[str] = set()
    for k in keys:
        people.update(_to_people_set(hit.get(k)))
    return people


def _weighted_kwargs(
    *,
    dense_weight: Optional[float] = None,
    sparse_weight: Optional[float] = None,
    type_weight: Optional[float] = None,
) -> Dict[str, float]:
    """构建可透传给检索层的权重参数。"""
    out: Dict[str, float] = {}
    if dense_weight is not None:
        out["dense_weight"] = dense_weight
    if sparse_weight is not None:
        out["sparse_weight"] = sparse_weight
    if type_weight is not None:
        out["type_weight"] = type_weight
    return out


def _retrieve_by_type_with_weights(
    retrieval: IRetrieval,
    text: str,
    *,
    type_filter: str,
    top_k: int,
    dense_weight: Optional[float] = None,
    sparse_weight: Optional[float] = None,
    type_weight: Optional[float] = None,
    collection_name: Optional[str] = None,
) -> List[dict]:
    """按指定 type + 权重参数检索。"""
    if not text:
        return []
    kw = _weighted_kwargs(
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        type_weight=type_weight,
    )
    kw.update(_search_kw(collection_name))
    hits = retrieval.search(
        query_text=text,
        type_filter=type_filter,
        top_k=top_k,
        **kw,
    )
    return [_to_ref(h) for h in hits]


def _search_kw(collection_name: Optional[str] = None) -> Dict[str, Any]:
    """构建 search 的 collection_name 等额外参数。"""
    kw: Dict[str, Any] = {}
    if collection_name:
        kw["collection_name"] = collection_name
    return kw


def retrieve_latest_minutes_by_series(
    retrieval: IRetrieval,
    meeting_type: str,
    meeting_name: str,
    top_k: int,
    *,
    project: str = "",
    department: str = "",
    organization: str = "",
    attendees: Optional[List[str]] = None,
    collection_name: Optional[str] = None,
) -> List[dict]:
    """同系列最新纪要：source=minutes、level1=会议类型/名，按 time 降序取 top_k。"""
    level1 = _normalize_meeting_key(meeting_type or meeting_name or "")
    if not level1:
        return []
    sk = _search_kw(collection_name)
    hits = retrieval.search(
        query_text=level1,
        source_filter="minutes",
        level1_filter=level1,
        top_k=top_k * 2,
        project_filter=project or None,
        department_filter=department or None,
        organization_filter=organization or None,
        **sk,
    )
    if not hits and meeting_name:
        # 兼容历史数据未规范化时，回退到原始名称检索
        hits = retrieval.search(
            query_text=meeting_name,
            source_filter="minutes",
            level1_filter=meeting_name,
            top_k=top_k * 2,
            project_filter=project or None,
            department_filter=department or None,
            organization_filter=organization or None,
            **sk,
        )
    # 弱约束：参会人重叠（仅作为排序辅助，不改变召回范围）
    query_attendees = _to_people_set(attendees or [])

    def _sort_key(h: dict) -> tuple:
        hit_attendees = _hit_attendees(h)
        overlap = 0.0
        if query_attendees and hit_attendees:
            overlap = len(query_attendees & hit_attendees) / max(len(query_attendees), 1)
        # 时间优先，其次参会人重叠，再次检索分数
        return (
            h.get("time", ""),
            overlap,
            float(h.get("score", 0.0)),
        )

    hits.sort(key=_sort_key, reverse=True)
    return [_to_ref(h) for h in hits[:top_k]]


def retrieve_by_topic(
    retrieval: IRetrieval,
    topic_name: str,
    top_k: int,
    *,
    collection_name: Optional[str] = None,
) -> List[dict]:
    if not topic_name:
        return []
    hits = retrieval.search(
        query_text=topic_name,
        topic_filter=topic_name,
        top_k=top_k,
        **_search_kw(collection_name),
    )
    return [_to_ref(h) for h in hits]


def retrieve_by_person(
    retrieval: IRetrieval,
    person_name: str,
    top_k: int,
    *,
    collection_name: Optional[str] = None,
) -> List[dict]:
    if not person_name:
        return []
    hits = retrieval.search(
        query_text=person_name,
        author_filter=person_name,
        top_k=top_k,
        **_search_kw(collection_name),
    )
    return [_to_ref(h) for h in hits]


def retrieve_similar_todos(
    retrieval: IRetrieval,
    text: str,
    top_k: int,
    *,
    dense_weight: Optional[float] = None,
    sparse_weight: Optional[float] = None,
    type_weight: Optional[float] = None,
    collection_name: Optional[str] = None,
) -> List[dict]:
    """按 todo 类型检索相似待办。"""
    return _retrieve_by_type_with_weights(
        retrieval,
        text,
        type_filter="todo",
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        type_weight=type_weight,
        collection_name=collection_name,
    )


def retrieve_similar_open_issues(
    retrieval: IRetrieval,
    text: str,
    top_k: int,
    *,
    dense_weight: Optional[float] = None,
    sparse_weight: Optional[float] = None,
    type_weight: Optional[float] = None,
    collection_name: Optional[str] = None,
) -> List[dict]:
    """按 open_issue 类型检索相似遗留问题。"""
    return _retrieve_by_type_with_weights(
        retrieval,
        text,
        type_filter="open_issue",
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        type_weight=type_weight,
        collection_name=collection_name,
    )


def retrieve_similar_todos_or_issues(
    retrieval: IRetrieval,
    text: str,
    top_k: int,
    *,
    todo_weight: float = 1.0,
    issue_weight: float = 1.0,
    dense_weight: Optional[float] = None,
    sparse_weight: Optional[float] = None,
    collection_name: Optional[str] = None,
) -> List[dict]:
    """按 todo/open_issue 分别检索并融合排序。"""
    if not text:
        return []
    todo_hits = retrieve_similar_todos(
        retrieval,
        text,
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        type_weight=todo_weight,
        collection_name=collection_name,
    )
    issue_hits = retrieve_similar_open_issues(
        retrieval,
        text,
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        type_weight=issue_weight,
        collection_name=collection_name,
    )
    merged = {}
    for item in todo_hits:
        key = item.get("pk") or f"todo:{item.get('page_content', '')[:64]}"
        item["score"] = float(item.get("score", 0.0)) * todo_weight
        merged[key] = item
    for item in issue_hits:
        key = item.get("pk") or f"issue:{item.get('page_content', '')[:64]}"
        item["score"] = float(item.get("score", 0.0)) * issue_weight
        if key not in merged or item["score"] > float(merged[key].get("score", 0.0)):
            merged[key] = item
    out = list(merged.values())
    out.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return out[:top_k]


def retrieve_similar_conclusions(
    retrieval: IRetrieval,
    text: str,
    top_k: int,
    *,
    dense_weight: Optional[float] = None,
    sparse_weight: Optional[float] = None,
    type_weight: Optional[float] = None,
    collection_name: Optional[str] = None,
) -> List[dict]:
    """按 conclusion 类型检索相似结论。"""
    return _retrieve_by_type_with_weights(
        retrieval,
        text,
        type_filter="conclusion",
        top_k=top_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
        type_weight=type_weight,
        collection_name=collection_name,
    )


def retrieve_similar_topic_by_draft(
    retrieval: IRetrieval,
    draft_text: str,
    top_k: int,
    *,
    collection_name: Optional[str] = None,
) -> List[dict]:
    if not draft_text:
        return []
    hits = retrieval.search(
        query_text=draft_text[:2000],
        source_filter="draft",
        top_k=top_k,
        **_search_kw(collection_name),
    )
    return [_to_ref(h) for h in hits]
