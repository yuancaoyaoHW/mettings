"""入库流水线：从结构化 chunk 生成带向量的待插入行；可选调用传入的 inserter。"""
from typing import Any, Callable, List, Optional

from services.embedding import get_embedding


def _embed_chunks(chunks: List[dict], text_key: str = "text") -> List[dict]:
    """对每条 chunk 的 text 做 embedding，写入 vector 字段。"""
    out = []
    for c in chunks:
        row = dict(c)
        text = row.get(text_key) or row.get("page_content") or ""
        row["vector"] = get_embedding(text)
        out.append(row)
    return out


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
    embedded = _embed_chunks(chunks)
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
