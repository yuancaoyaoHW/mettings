"""口水稿工具：按议题在内存中分割（本次会议）。"""
import re
from typing import List


def get_draft_segments_by_topics(draft_text: str, topic_names: List[str]) -> List[dict]:
    """按议题名对口水稿做内存分割（关键词+句界），返回 {topic, page_content} 列表。"""
    if not draft_text or not topic_names:
        return []
    segments = []
    # Split into sentences (simple: 。！？\n)
    sentences = re.split(r"(?<=[。！？\n])", draft_text)
    for topic in topic_names:
        if not topic:
            continue
        matching = []
        for s in sentences:
            if topic in s or s.strip().startswith(topic[:2] if len(topic) >= 2 else ""):
                matching.append(s.strip())
        if matching:
            segments.append({"topic": topic, "page_content": " ".join(matching)})
        else:
            idx = draft_text.find(topic)
            if idx >= 0:
                start = max(0, idx - 80)
                end = min(len(draft_text), idx + len(topic) + 400)
                segments.append({"topic": topic, "page_content": draft_text[start:end]})
            else:
                segments.append({"topic": topic, "page_content": ""})
    return segments
