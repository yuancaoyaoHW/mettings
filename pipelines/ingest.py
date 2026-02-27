"""入库流水线：从结构化 chunk 生成带向量的待插入行；可选调用传入的 inserter。"""
from typing import Any, Callable, List, Optional

from services.embedding import get_embedding


_MINUTES_TYPE_ALIASES = {
    "issue": "open_issue",
    "open-issue": "open_issue",
    "openissue": "open_issue",
    "action_item": "todo",
    "action-item": "todo",
    "task": "todo",
    "decision": "conclusion",
}
_MINUTES_ALLOWED_TYPES = {"summary", "open_issue", "conclusion", "todo"}


def _embed_chunks(chunks: List[dict], text_key: str = "text") -> List[dict]:
    """对每条 chunk 的 text 做 embedding，写入 vector 字段。"""
    out = []
    for c in chunks:
        row = dict(c)
        text = row.get(text_key) or row.get("page_content") or ""
        row["vector"] = get_embedding(text)
        out.append(row)
    return out


def _normalize_minutes_type(raw_type: str) -> str:
    """分钟类 chunk type 归一化。"""
    if not raw_type:
        return ""
    key = str(raw_type).strip().lower()
    return _MINUTES_TYPE_ALIASES.get(key, key)


def _validate_minutes_chunk(chunk: dict) -> dict:
    """
    校验并标准化 minutes chunk：
    - type 仅允许 summary/open_issue/conclusion/todo
    - text 必须非空
    - todo 必须有 owner
    - open_issue 建议有 next_step（缺失时给空字符串）
    """
    normalized = dict(chunk)
    text = normalized.get("text", normalized.get("page_content", ""))
    if not str(text).strip():
        raise ValueError("minutes chunk text is required")

    source = str(normalized.get("source", "minutes") or "minutes").strip().lower()
    normalized["source"] = source

    # 仅对 minutes 做分索引规则校验；attachment/draft 走宽松校验。
    if source == "minutes":
        normalized_type = _normalize_minutes_type(normalized.get("type", ""))
        if normalized_type not in _MINUTES_ALLOWED_TYPES:
            raise ValueError(f"minutes chunk type must be one of {_MINUTES_ALLOWED_TYPES}, got: {normalized.get('type')}")
        normalized["type"] = normalized_type

        if normalized_type == "todo" and not str(normalized.get("owner", "")).strip():
            raise ValueError("todo chunk requires owner")
        if normalized_type == "open_issue":
            normalized.setdefault("next_step", "")
            normalized.setdefault("issue_reason", "")
    return normalized


def _row_for_milvus(chunk: dict) -> dict:
    """从 chunk 拼出符合 Milvus Schema 的单条 row（含 vector、text、source、level1、level2、topic、author、time、version、type）。"""
    return {
        "text": chunk.get("text", chunk.get("page_content", "")),
        "vector": chunk["vector"],
        "source": chunk.get("source", ""),
        "type": chunk.get("type", ""),
        "level1": chunk.get("level1", ""),
        "level2": chunk.get("level2", ""),
        "topic": chunk.get("topic", ""),
        "author": chunk.get("author", ""),
        "time": chunk.get("time", ""),
        "version": chunk.get("version", ""),
        "owner": chunk.get("owner", ""),
        "deadline": chunk.get("deadline", ""),
        "status": chunk.get("status", ""),
        "next_step": chunk.get("next_step", ""),
        "issue_reason": chunk.get("issue_reason", ""),
        "source_id": chunk.get("source_id", ""),
        "source_position": chunk.get("source_position", ""),
        "confidence": chunk.get("confidence", None),
        "project": chunk.get("project", ""),
        "department": chunk.get("department", ""),
        "organization": chunk.get("organization", ""),
    }


def ingest_minutes_chunks(
    chunks: List[dict],
    *,
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
) -> List[dict]:
    """
    纪要 chunk 入库：对每条做 embedding，拼成待插入行。
    若传入 client.insert(collection_name, rows) 或 inserter(collection_name, rows)，则调用后返回 []；
    否则返回待插入的 rows，由调用方自行写入 Milvus。
    """
    if not chunks:
        return []
    validated = [_validate_minutes_chunk(c) for c in chunks]
    embedded = _embed_chunks(validated)
    rows = [_row_for_milvus(c) for c in embedded]
    insert_fn = (getattr(client, "insert", None) if client and callable(getattr(client, "insert", None)) else None) or inserter
    if insert_fn and collection_name:
        insert_fn(collection_name, rows)
        return []
    return rows


def ingest_attachments(
    chunks: List[dict],
    *,
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
) -> List[dict]:
    """附件 chunk 入库：同 ingest_minutes_chunks，source 应为 attachment。"""
    if not chunks:
        return []
    copy_chunks = [dict(c) for c in chunks]
    for c in copy_chunks:
        c.setdefault("source", "attachment")
    return ingest_minutes_chunks(copy_chunks, collection_name=collection_name, client=client, inserter=inserter)


def ingest_draft_segments(
    segments: List[dict],
    *,
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
) -> List[dict]:
    """口水稿按议题切分后的 segment 入库：含 topic，source=draft，type=draft_segment。"""
    if not segments:
        return []
    chunks = []
    for s in segments:
        chunks.append({
            "text": s.get("text", s.get("page_content", "")),
            "source": "draft",
            "type": "draft_segment",
            "topic": s.get("topic", ""),
            "level1": s.get("level1", ""),
            "level2": s.get("level2", ""),
            "author": s.get("author", ""),
            "time": s.get("time", ""),
            "version": s.get("version", ""),
        })
    return ingest_minutes_chunks(chunks, collection_name=collection_name, client=client, inserter=inserter)


def ingest_structured_items(
    items: List[dict],
    *,
    item_type: str,
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
) -> List[dict]:
    """
    针对 todo/open_issue/conclusion 的快捷入库：
    - 统一写 source=minutes
    - 强制覆盖 type=item_type
    - 复用 minutes chunk 校验与向量化逻辑
    """
    normalized_type = _normalize_minutes_type(item_type)
    if normalized_type not in {"todo", "open_issue", "conclusion"}:
        raise ValueError("item_type must be one of: todo, open_issue, conclusion")
    chunks = []
    for item in items:
        row = dict(item)
        row["source"] = row.get("source", "minutes")
        row["type"] = normalized_type
        chunks.append(row)
    return ingest_minutes_chunks(chunks, collection_name=collection_name, client=client, inserter=inserter)
