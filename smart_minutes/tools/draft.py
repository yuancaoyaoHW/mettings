"""Draft tools: segment draft by topics (this meeting, in-memory)."""
import re
from typing import List


def get_draft_segments_by_topics(draft_text: str, topic_names: List[str]) -> List[dict]:
    """
    Segment draft_text by topic_names in memory. Uses keyword match and sentence boundaries;
    no Milvus. Returns list of {topic, page_content} for agent to include in context.
    """
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
