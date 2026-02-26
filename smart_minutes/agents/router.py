"""Intent router: suggest tool sequence from request context."""
from typing import Any, List

from smart_minutes.schemas import MinutesRequest


def suggest_tools(request: MinutesRequest) -> List[dict]:
    """
    Suggest ordered list of tool calls (name + params) from request.
    Rule-based: no LLM. Agent may still append or skip based on results.
    """
    steps: List[dict] = []

    # 1. Mapping (no dependency)
    if request.oral_names or request.person_names:
        steps.append({"tool": "mapping", "params": {"oral_names": request.oral_names, "person_names": request.person_names}})
    if request.meeting_type or request.meeting_name:
        steps.append({"tool": "professional_terms", "params": {"meeting_type": request.meeting_type or "", "meeting_name": request.meeting_name or ""}})

    # 2. RAG (can run in parallel in agent)
    opts = request.options or {}
    top_k = opts.get("top_k", 5)

    if request.meeting_type or request.meeting_name:
        steps.append({"tool": "retrieve_latest_minutes_by_series", "params": {"meeting_type": request.meeting_type or "", "meeting_name": request.meeting_name or "", "top_k": top_k}})
    for t in request.topics:
        steps.append({"tool": "retrieve_by_topic", "params": {"topic_name": t, "top_k": top_k}})
    for p in request.person_names:
        steps.append({"tool": "retrieve_by_person", "params": {"person_name": p, "top_k": top_k}})
    for o in request.open_issues:
        steps.append({"tool": "retrieve_similar_todos_or_issues", "params": {"text": o, "top_k": top_k}})
    for c in request.conclusions:
        steps.append({"tool": "retrieve_similar_conclusions", "params": {"text": c, "top_k": top_k}})
    if request.draft_text:
        steps.append({"tool": "retrieve_similar_topic_by_draft", "params": {"draft_text": request.draft_text[:2000], "top_k": top_k}})
    if request.meeting_type or request.meeting_name:
        steps.append({"tool": "get_attachments_by_meeting", "params": {"meeting_type": request.meeting_type or "", "meeting_name": request.meeting_name or ""}})
    for t in request.topics:
        steps.append({"tool": "search_attachments_by_topic", "params": {"topic_name": t, "query": t, "top_k": top_k}})

    # 3. Draft segmentation (this meeting)
    if request.draft_text and request.topics:
        steps.append({"tool": "get_draft_segments_by_topics", "params": {"draft_text": request.draft_text, "topic_names": request.topics}})

    # 4. Speaker (if realtime input)
    if request.realtime_speaker:
        steps.append({"tool": "resolve_speaker", "params": {"face_result": getattr(request.realtime_speaker, "face_result", None), "voice_result": getattr(request.realtime_speaker, "voice_result", None), "venue_name": getattr(request.realtime_speaker, "venue_name", None)}})

    return steps
