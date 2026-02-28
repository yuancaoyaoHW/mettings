"""意图路由：根据请求上下文给出建议的工具调用序列。

本模块不做工具执行，只负责：
- 决定“调用哪些工具”；
- 计算每个工具的参数（含模板与默认值合并）。
"""
from typing import Any, Dict, List, Optional

from smart_minutes.config_templates import MeetingTypeTemplate, RetrievalWeights
from smart_minutes.schemas import MinutesRequest


def suggest_tools(
    request: MinutesRequest,
    *,
    templates: Optional[Dict[str, MeetingTypeTemplate]] = None,
    default_top_k: int = 5,
    default_dense_weight: Optional[float] = None,
    default_sparse_weight: Optional[float] = None,
) -> List[dict]:
    """按规则产出工具调用列表（名称+参数）。

    参数合并优先级：
    请求 `options` > meeting_type 模板 > 全局默认值。
    """
    steps: List[dict] = []

    # 1. 映射（无依赖）
    if request.oral_names or request.person_names:
        steps.append({"tool": "mapping", "params": {"oral_names": request.oral_names, "person_names": request.person_names}})
    if request.meeting_type or request.meeting_name:
        steps.append({"tool": "professional_terms", "params": {"meeting_type": request.meeting_type or "", "meeting_name": request.meeting_name or ""}})

    # 2. RAG（在 Agent 中可并行）
    opts = request.options or {}
    template = templates.get(request.meeting_type) if (templates and request.meeting_type) else None
    top_k = int(opts.get("top_k", template.top_k if template else default_top_k))
    weights = opts.get("retrieval_weights", {}) if isinstance(opts.get("retrieval_weights", {}), dict) else {}

    def _weights(name: str) -> RetrievalWeights:
        """读取模板中的分类型权重；未命中则返回默认权重对象。"""
        if not template:
            return RetrievalWeights()
        if name == "todo":
            return template.todo_weights
        if name == "open_issue":
            return template.open_issue_weights
        if name == "conclusion":
            return template.conclusion_weights
        return RetrievalWeights()

    def _get_float(d: dict, key: str) -> Optional[float]:
        """从字典读取浮点参数；缺失或空值返回 None。"""
        if key not in d or d.get(key) is None:
            return None
        return float(d.get(key))

    def _resolve_dense_sparse(req_weights: dict, template_weights: RetrievalWeights) -> tuple[Optional[float], Optional[float]]:
        """解析 dense/sparse 最终值，遵循统一优先级规则。"""
        dense = _get_float(req_weights, "dense_weight")
        sparse = _get_float(req_weights, "sparse_weight")
        if dense is None:
            dense = _get_float(opts, "dense_weight")
        if sparse is None:
            sparse = _get_float(opts, "sparse_weight")
        if dense is None:
            dense = template_weights.dense_weight
        if sparse is None:
            sparse = template_weights.sparse_weight
        if dense is None:
            dense = default_dense_weight
        if sparse is None:
            sparse = default_sparse_weight
        return dense, sparse

    if request.meeting_type or request.meeting_name:
        steps.append(
            {
                "tool": "retrieve_latest_minutes_by_series",
                "params": {
                    "meeting_type": request.meeting_type or "",
                    "meeting_name": request.meeting_name or "",
                    "project": request.project or "",
                    "department": request.department or "",
                    "organization": request.organization or "",
                    "top_k": top_k,
                },
            }
        )
    for t in request.topics:
        steps.append({"tool": "retrieve_by_topic", "params": {"topic_name": t, "top_k": top_k}})
    for p in request.person_names:
        steps.append({"tool": "retrieve_by_person", "params": {"person_name": p, "top_k": top_k}})
    for o in request.open_issues:
        oi_weights = weights.get("open_issue", {}) if isinstance(weights.get("open_issue", {}), dict) else {}
        todo_weights = weights.get("todo", {}) if isinstance(weights.get("todo", {}), dict) else {}
        t_oi = _weights("open_issue")
        t_todo = _weights("todo")
        dense_weight, sparse_weight = _resolve_dense_sparse(oi_weights, t_oi)
        issue_weight = _get_float(oi_weights, "type_weight")
        if issue_weight is None:
            issue_weight = t_oi.type_weight
        todo_weight = _get_float(todo_weights, "type_weight")
        if todo_weight is None:
            todo_weight = t_todo.type_weight
        steps.append(
            {
                "tool": "retrieve_similar_todos_or_issues",
                "params": {
                    "text": o,
                    "top_k": top_k,
                    "todo_weight": float(todo_weight),
                    "issue_weight": float(issue_weight),
                    "dense_weight": dense_weight,
                    "sparse_weight": sparse_weight,
                },
            }
        )
    for c in request.conclusions:
        c_weights = weights.get("conclusion", {}) if isinstance(weights.get("conclusion", {}), dict) else {}
        t_conclusion = _weights("conclusion")
        dense_weight, sparse_weight = _resolve_dense_sparse(c_weights, t_conclusion)
        c_type_weight = _get_float(c_weights, "type_weight")
        if c_type_weight is None:
            c_type_weight = t_conclusion.type_weight
        steps.append(
            {
                "tool": "retrieve_similar_conclusions",
                "params": {
                    "text": c,
                    "top_k": top_k,
                    "type_weight": c_type_weight,
                    "dense_weight": dense_weight,
                    "sparse_weight": sparse_weight,
                },
            }
        )
    if request.draft_text:
        steps.append({"tool": "retrieve_similar_topic_by_draft", "params": {"draft_text": request.draft_text[:2000], "top_k": top_k}})
    if request.meeting_type or request.meeting_name:
        steps.append({"tool": "get_attachments_by_meeting", "params": {"meeting_type": request.meeting_type or "", "meeting_name": request.meeting_name or ""}})
    for t in request.topics:
        steps.append({"tool": "search_attachments_by_topic", "params": {"topic_name": t, "query": t, "top_k": top_k}})

    # 3. 口水稿按议题分割（本次会议）
    if request.draft_text and request.topics:
        steps.append({"tool": "get_draft_segments_by_topics", "params": {"draft_text": request.draft_text, "topic_names": request.topics}})

    # 4. 发言人融合（若有实时输入）
    if request.realtime_speaker:
        steps.append({"tool": "resolve_speaker", "params": {"face_result": getattr(request.realtime_speaker, "face_result", None), "voice_result": getattr(request.realtime_speaker, "voice_result", None), "venue_name": getattr(request.realtime_speaker, "venue_name", None)}})

    return steps
