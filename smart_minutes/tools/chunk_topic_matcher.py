"""
Chunk-主题匹配：给定纪要若干 chunk + 若干主题，为每个 chunk 分配主题
"""
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def match_chunks_to_topics(
    chunks: List[Dict],
    topics: List[str],
    *,
    unclassified_label: str = "未分类",
) -> List[Dict]:
    """
    为每个 chunk 分配一个主题。

    Args:
        chunks: List[{ "chunk_id", "text" }]
        topics: 主题列表
        unclassified_label: 无法匹配时的标签

    Returns:
        assignments: List[{ "chunk_id", "topic" }]
    """
    if not chunks or not topics:
        return [{"chunk_id": c.get("chunk_id", ""), "topic": unclassified_label} for c in chunks]

    try:
        from services.llm import complete
    except ImportError:
        logger.warning("LLM not available, fallback to first topic")
        return [
            {"chunk_id": c.get("chunk_id", ""), "topic": topics[0] if topics else unclassified_label}
            for c in chunks
        ]

    system = (
        "你是一个文本分类助手。根据给定文本内容，选择一个最匹配的主题。"
        "只输出主题名称，不要其他解释。"
        f"可选主题：{json.dumps(topics, ensure_ascii=False)}。"
        f"若都不匹配，输出：{unclassified_label}"
    )

    assignments = []
    for c in chunks:
        chunk_id = c.get("chunk_id", "")
        text = (c.get("text") or "")[:1500]
        if not text:
            assignments.append({"chunk_id": chunk_id, "topic": unclassified_label})
            continue
        prompt = f"文本：\n{text}\n\n请选择最匹配的主题："
        result = complete(prompt, system=system)
        topic = (result or "").strip()
        if topic not in topics and topic != unclassified_label:
            topic = unclassified_label
        assignments.append({"chunk_id": chunk_id, "topic": topic or unclassified_label})

    return assignments
