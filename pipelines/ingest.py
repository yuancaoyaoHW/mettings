"""Ingest pipeline: load minutes/attachments/mappings into Milvus and DB (skeleton)."""
from typing import Any, List, Optional


def ingest_minutes_chunks(
    chunks: List[dict],
    *,
    collection_name: str = "",
    client: Any = None,
) -> None:
    """Insert minute chunks (with vector, text, source, level1, topic, author, time, type) into Milvus."""
    pass


def ingest_attachments(chunks: List[dict], *, collection_name: str = "", client: Any = None) -> None:
    """Insert attachment chunks into Milvus."""
    pass


def ingest_draft_segments(segments: List[dict], *, collection_name: str = "", client: Any = None) -> None:
    """Insert draft segments (with topic) into Milvus."""
    pass
