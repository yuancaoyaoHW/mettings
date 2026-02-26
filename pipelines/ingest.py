"""入库流水线：将纪要/附件/口水稿写入 Milvus 与 DB（骨架）。"""
from typing import Any, List, Optional


def ingest_minutes_chunks(
    chunks: List[dict],
    *,
    collection_name: str = "",
    client: Any = None,
) -> None:
    """纪要 chunk 入库（含 vector、text、source、level1、topic、author、time、type）。"""
    pass


def ingest_attachments(chunks: List[dict], *, collection_name: str = "", client: Any = None) -> None:
    """附件 chunk 入库。"""
    pass


def ingest_draft_segments(segments: List[dict], *, collection_name: str = "", client: Any = None) -> None:
    """口水稿按议题切分后的 segment 入库（含 topic）。"""
    pass
