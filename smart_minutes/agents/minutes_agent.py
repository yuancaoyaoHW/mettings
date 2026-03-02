"""纪要生成 Agent：执行工具序列、组装上下文、在 token 预算内调用 LLM。"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterator, List, Optional

from smart_minutes.schemas import (
    ActionItem,
    ErrorItem,
    MaterialCitation,
    MeetingInfo,
    MinutesRequest,
    MinutesResponse,
    ReferenceItem,
    SpeakerResolution,
    StructuredMinutesOutput,
    TopicSection,
    TraceabilityInfo,
)

if False:
    from smart_minutes.contracts import IMappingStore, IRetrieval, ISpeakerResolver
    from smart_minutes.config import SmartMinutesConfig


class MinutesAgent:
    """按建议顺序执行工具，合并结果，按 context_token_budget 截断后生成纪要。"""

    def __init__(
        self,
        retrieval: "IRetrieval",
        mapping_store: "IMappingStore",
        speaker_resolver: Optional["ISpeakerResolver"] = None,
        config: Optional["SmartMinutesConfig"] = None,
    ):
        from smart_minutes.config import SmartMinutesConfig
        self._retrieval = retrieval
        self._mapping_store = mapping_store
        self._speaker_resolver = speaker_resolver
        self._config = config or SmartMinutesConfig.from_env()

    def run(
        self,
        request: MinutesRequest,
        tool_suggestions: List[dict],
        *,
        retrieve_only: bool = False,
    ) -> MinutesResponse:
        """执行工具列表、收集引用，可选调用 LLM；遵守 context_token_budget。"""
        refs, resolved_speakers, speaker_resolutions, mapped_terms, warnings, errors = self._execute_tools(request, tool_suggestions)
        structured_output = self._build_structured_output(request, refs, speaker_resolutions)
        if retrieve_only:
            return MinutesResponse(
                minutes_content="",
                references=refs,
                resolved_speakers=resolved_speakers,
                speaker_resolutions=speaker_resolutions,
                mapped_terms=mapped_terms,
                errors=errors,
                warnings=warnings,
                partial=len(warnings) > 0 or len(errors) > 0,
                structured_output=structured_output,
            )

        context_parts = self._assemble_context(refs, mapped_terms, resolved_speakers, request)
        budget = getattr(self._config, "context_token_budget", 8000)
        truncated = self._truncate_to_budget(context_parts, budget)
        try:
            minutes_content = self._generate_minutes(request, truncated)
        except Exception as e:
            errors.append(ErrorItem(code="GENERATE_ERROR", message=str(e)))
            minutes_content = ""
        parsed_topics = self._parse_structured_topics_from_content(minutes_content, request.topics)
        if parsed_topics:
            structured_output = self._merge_parsed_topics(structured_output, parsed_topics)
        return MinutesResponse(
            minutes_content=minutes_content,
            references=refs,
            resolved_speakers=resolved_speakers,
            speaker_resolutions=speaker_resolutions,
            mapped_terms=mapped_terms,
            errors=errors,
            warnings=warnings,
            partial=len(warnings) > 0 or len(errors) > 0,
            structured_output=structured_output,
        )

    def prepare_generation(self, request: MinutesRequest, tool_suggestions: List[dict]) -> Dict[str, Any]:
        """执行非流式准备阶段：工具调用、上下文组装、预算裁剪、Prompt 构建。"""
        refs, resolved_speakers, speaker_resolutions, mapped_terms, warnings, errors = self._execute_tools(request, tool_suggestions)
        structured_output = self._build_structured_output(request, refs, speaker_resolutions)
        response = MinutesResponse(
            minutes_content="",
            references=refs,
            resolved_speakers=resolved_speakers,
            speaker_resolutions=speaker_resolutions,
            mapped_terms=mapped_terms,
            errors=errors,
            warnings=warnings,
            partial=len(warnings) > 0 or len(errors) > 0,
            structured_output=structured_output,
        )
        context_parts = self._assemble_context(refs, mapped_terms, resolved_speakers, request)
        budget = getattr(self._config, "context_token_budget", 8000)
        truncated = self._truncate_to_budget(context_parts, budget)
        system_prompt, user_prompt = self._build_prompts(request, truncated)
        return {
            "response": response,
            "context": truncated,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "token_budget": budget,
        }

    def stream_generate_minutes(self, request: MinutesRequest, context: str) -> Iterator[str]:
        """基于已裁剪上下文调用 LLM 流式生成 token。"""
        from services.llm import stream_complete
        system_prompt, user_prompt = self._build_prompts(request, context)
        return stream_complete(user_prompt, system=system_prompt)

    def _execute_tools(
        self,
        request: MinutesRequest,
        tool_suggestions: List[dict],
    ) -> tuple[List[ReferenceItem], List[str], List[SpeakerResolution], List[str], List[str], List[ErrorItem]]:
        """执行工具并汇总结果。"""
        refs: List[ReferenceItem] = []
        resolved_speakers: List[str] = []
        speaker_resolutions: List[SpeakerResolution] = []
        mapped_terms: List[str] = []
        warnings: List[str] = []
        errors: List[ErrorItem] = []

        # 分组：先映射；再并行 RAG/附件；最后口水稿与发言人
        group1 = ["mapping", "professional_terms"]
        group2 = [
            "retrieve_latest_minutes_by_series", "retrieve_by_topic", "retrieve_by_person",
            "retrieve_similar_todos_or_issues", "retrieve_similar_conclusions",
            "retrieve_similar_topic_by_draft", "get_attachments_by_meeting", "search_attachments_by_topic",
        ]
        group3 = ["get_draft_segments_by_topics", "resolve_speaker"]
        ordered_steps: List[dict] = []
        g1_steps = [s for s in tool_suggestions if (s.get("tool") or "") in group1]
        g2_steps = [s for s in tool_suggestions if (s.get("tool") or "") in group2]
        g3_steps = [s for s in tool_suggestions if (s.get("tool") or "") in group3]
        other_steps = [s for s in tool_suggestions if s not in g1_steps and s not in g2_steps and s not in g3_steps]
        ordered_steps = g1_steps + g2_steps + g3_steps + other_steps

        def run_step(step: dict) -> tuple:
            tool_name = step.get("tool") or ""
            params = step.get("params") or {}
            try:
                out = self._run_one_tool(tool_name, params, request)
                return (tool_name, out, None)
            except Exception as e:
                return (tool_name, None, str(e))

        # group2 并行执行
        results: List[tuple] = []
        for step in g1_steps:
            results.append(run_step(step))
        if g2_steps:
            with ThreadPoolExecutor(max_workers=min(8, len(g2_steps))) as ex:
                futs = {ex.submit(run_step, s): s for s in g2_steps}
                for fut in as_completed(futs):
                    results.append(fut.result())
        for step in g3_steps + other_steps:
            results.append(run_step(step))

        for tool_name, out, err in results:
            if err:
                warnings.append(f"{tool_name}: {err}")
                continue
            if isinstance(out, list):
                for it in out:
                    if isinstance(it, dict):
                        if "page_content" in it or it.get("topic"):
                            refs.append(ReferenceItem(
                                pk=it.get("pk"),
                                score=it.get("score", 0.0),
                                page_content=it.get("page_content", ""),
                                source=it.get("source", ""),
                                type=it.get("type", ""),
                                level1=it.get("level1", ""),
                                level2=it.get("level2", ""),
                                author=it.get("author", ""),
                                time=it.get("time", ""),
                                version=it.get("version", ""),
                                topic=it.get("topic", ""),
                                source_id=it.get("source_id", ""),
                                source_position=it.get("source_position", ""),
                                confidence=it.get("confidence"),
                                owner=it.get("owner", ""),
                                deadline=it.get("deadline", ""),
                            ))
                    elif isinstance(it, str) and tool_name in ("mapping", "professional_terms"):
                        mapped_terms.append(it)
            elif isinstance(out, str) and tool_name == "resolve_speaker" and out:
                resolved_speakers.append(out)
            elif isinstance(out, SpeakerResolution) and tool_name == "resolve_speaker":
                speaker_resolutions.append(out)
                if out.resolved_name:
                    resolved_speakers.append(out.resolved_name)
            elif isinstance(out, dict) and tool_name == "resolve_speaker":
                sr = SpeakerResolution.model_validate(out)
                speaker_resolutions.append(sr)
                if sr.resolved_name:
                    resolved_speakers.append(sr.resolved_name)
            elif isinstance(out, list) and tool_name in ("mapping", "professional_terms"):
                mapped_terms.extend(x for x in out if isinstance(x, str))
        return refs, resolved_speakers, speaker_resolutions, mapped_terms, warnings, errors

    def _run_one_tool(self, tool_name: str, params: dict, request: MinutesRequest) -> Any:
        """按工具名分发到 tools/adapters。"""
        from smart_minutes.tools import rag, mapping, speaker, attachment, draft
        top_k = params.get("top_k", getattr(self._config, "default_top_k", 5))
        if tool_name == "mapping":
            names = params.get("oral_names") or []
            return [self._mapping_store.resolve_oral_to_formal(n) for n in names if self._mapping_store.resolve_oral_to_formal(n)]
        if tool_name == "professional_terms":
            return self._mapping_store.get_professional_terms(params.get("meeting_type", ""), params.get("meeting_name", ""))
        if tool_name == "retrieve_latest_minutes_by_series":
            return rag.retrieve_latest_minutes_by_series(
                self._retrieval,
                params.get("meeting_type", ""),
                params.get("meeting_name", ""),
                top_k,
                project=params.get("project", ""),
                department=params.get("department", ""),
                organization=params.get("organization", ""),
                attendees=params.get("attendees") or [],
            )
        if tool_name == "retrieve_by_topic":
            return rag.retrieve_by_topic(self._retrieval, params.get("topic_name", ""), top_k)
        if tool_name == "retrieve_by_person":
            return rag.retrieve_by_person(self._retrieval, params.get("person_name", ""), top_k)
        if tool_name == "retrieve_similar_todos_or_issues":
            return rag.retrieve_similar_todos_or_issues(
                self._retrieval,
                params.get("text", ""),
                top_k,
                todo_weight=float(params.get("todo_weight", 1.0)),
                issue_weight=float(params.get("issue_weight", 1.0)),
                dense_weight=params.get("dense_weight"),
                sparse_weight=params.get("sparse_weight"),
            )
        if tool_name == "retrieve_similar_conclusions":
            return rag.retrieve_similar_conclusions(
                self._retrieval,
                params.get("text", ""),
                top_k,
                dense_weight=params.get("dense_weight"),
                sparse_weight=params.get("sparse_weight"),
                type_weight=params.get("type_weight"),
            )
        if tool_name == "retrieve_similar_topic_by_draft":
            return rag.retrieve_similar_topic_by_draft(self._retrieval, params.get("draft_text", ""), top_k)
        if tool_name == "get_attachments_by_meeting":
            return attachment.get_attachments_by_meeting(self._retrieval, params.get("meeting_type", ""), params.get("meeting_name", ""))
        if tool_name == "search_attachments_by_topic":
            return attachment.search_attachments_by_topic(self._retrieval, params.get("topic_name", ""), params.get("query", ""), top_k)
        if tool_name == "get_draft_segments_by_topics":
            return draft.get_draft_segments_by_topics(params.get("draft_text", ""), params.get("topic_names", []))
        if tool_name == "resolve_speaker" and self._speaker_resolver:
            return self._speaker_resolver.resolve_speaker(params.get("face_result"), params.get("voice_result"), params.get("venue_name"))
        return []

    def _assemble_context(
        self,
        refs: List[ReferenceItem],
        mapped_terms: List[str],
        resolved_speakers: List[str],
        request: MinutesRequest,
    ) -> List[str]:
        """组装上下文片段：历史模板、同类议题、专业词、发言人、口水稿。"""
        parts = []
        # 历史纪要模板：同系列 minutes 的 refs
        template_refs = [r for r in refs if r.source == "minutes"]
        if template_refs:
            parts.append("## 历史纪要模板（同系列）\n" + "\n\n".join(r.page_content for r in template_refs[:5]))
        # 同类议题风格：按议题检索到的 summary/open_issue 等
        other_refs = [r for r in refs if r.source != "minutes" or r not in template_refs]
        if other_refs:
            parts.append("## 同类议题参考（总结/遗留风格）\n" + "\n\n".join(r.page_content for r in other_refs[:15]))
        if mapped_terms:
            parts.append("## 专业术语\n" + ", ".join(mapped_terms))
        if resolved_speakers:
            parts.append("## 发言人\n" + ", ".join(resolved_speakers))
        if request.draft_text:
            parts.append("## 口水稿\n" + (request.draft_text[:3000] if len(request.draft_text) > 3000 else request.draft_text))
        return parts

    def _truncate_to_budget(self, parts: List[str], budget: int) -> str:
        """按 token 预算截断；优先保留靠前片段（历史模板 > 同类议题 > 专业词/发言人 > 口水稿）。"""
        chars_per = getattr(self._config, "chars_per_token", 4)
        approx_chars = budget * chars_per
        out = []
        for p in parts:
            current_len = sum(len(x) for x in out)
            if current_len + len(p) <= approx_chars:
                out.append(p)
            else:
                remain = approx_chars - current_len
                if remain > 100:
                    out.append(p[: int(remain)] + "...")
                break
        return "\n\n".join(out)

    def _generate_minutes(self, request: MinutesRequest, context: str) -> str:
        """根据上下文调用 LLM 生成纪要正文；无配置时返回占位。"""
        from services.llm import complete
        system, user = self._build_prompts(request, context)
        out = complete(user, system=system)
        meeting_label = request.meeting_name or request.meeting_type or "未命名"
        topics_label = "、".join(request.topics) if request.topics else "（未提供）"
        if not out:
            return f"[纪要占位] 会议: {meeting_label}\n议题: {topics_label}\n\n参考上下文已纳入，LLM 未配置或调用失败。"
        return out

    def _build_prompts(self, request: MinutesRequest, context: str) -> tuple[str, str]:
        """统一构建 system/user prompt，便于非流式与流式复用。"""
        meeting_label = request.meeting_name or request.meeting_type or "未命名"
        topics_label = "、".join(request.topics) if request.topics else "（未提供）"
        system = (
            "你是一名会议纪要撰写助手。请根据用户提供的会议信息与参考上下文，生成结构清晰、用语规范的会议纪要。"
            "纪要应包含会议名称、议题、讨论要点、结论与待办（如有）。"
            "参考上下文中的历史模板与同类议题风格仅供参考，不要照抄。"
            "必须严格区分“历史背景/上次遗留”和“本次新结论”，不要把历史结论当作本次结论。"
            "关键事实或结论尽量附上来源标识。"
        )
        user = (
            f"## 本次会议\n会议: {meeting_label}\n议题: {topics_label}\n\n## 参考上下文\n{context}\n\n"
            "请基于以上内容生成会议纪要正文。"
            "请在正文末尾附一个 JSON 块（用 ```json 包裹），键为 topics，值为数组；"
            "每项含 topic_name、summary、key_points（字符串数组）、conclusions、open_issues、"
            "action_items（数组，每项含 content、owner、deadline）。若无法生成可省略该块。"
        )
        return system, user

    def _parse_structured_topics_from_content(
        self, content: str, topic_names: List[str]
    ) -> Optional[List[TopicSection]]:
        """从纪要正文中解析 ```json ... ``` 块中的 topics，转为 TopicSection 列表。"""
        if not content:
            return None
        match = re.search(r"```(?:json|JSON)\s*\n(.*?)\n```", content, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            return None
        raw_topics = data.get("topics")
        if not isinstance(raw_topics, list):
            return None
        out: List[TopicSection] = []
        for t in raw_topics:
            if not isinstance(t, dict):
                continue
            action_items: List[ActionItem] = []
            for ai in t.get("action_items") or []:
                if isinstance(ai, dict):
                    action_items.append(
                        ActionItem(
                            content=ai.get("content", "") or "",
                            owner=ai.get("owner"),
                            deadline=ai.get("deadline"),
                        )
                    )
            out.append(
                TopicSection(
                    topic_name=t.get("topic_name", "") or "",
                    summary=t.get("summary", "") or "",
                    key_points=[x for x in (t.get("key_points") or []) if isinstance(x, str)],
                    conclusions=[x for x in (t.get("conclusions") or []) if isinstance(x, str)],
                    open_issues=[x for x in (t.get("open_issues") or []) if isinstance(x, str)],
                    action_items=action_items,
                )
            )
        return out if out else None

    def _merge_parsed_topics(
        self,
        structured_output: StructuredMinutesOutput,
        parsed: List[TopicSection],
    ) -> StructuredMinutesOutput:
        """按 topic_name 将解析出的议题内容合并进已有 topics，返回新 StructuredMinutesOutput。"""
        existing = structured_output.topics or []
        by_name: Dict[str, TopicSection] = {s.topic_name: s for s in existing if s.topic_name}
        for p in parsed:
            if p.topic_name:
                by_name[p.topic_name] = p
        existing_names = [s.topic_name for s in existing]
        merged = [by_name.get(name) or TopicSection(topic_name=name) for name in existing_names]
        for p in parsed:
            if p.topic_name and p.topic_name not in existing_names:
                merged.append(p)
        return StructuredMinutesOutput(
            meeting_info=structured_output.meeting_info,
            topics=merged,
            materials=structured_output.materials or [],
            traceability=structured_output.traceability,
        )

    def _build_structured_output(
        self,
        request: MinutesRequest,
        refs: List[ReferenceItem],
        speaker_resolutions: List[SpeakerResolution],
    ) -> StructuredMinutesOutput:
        """构造基础结构化输出，便于前端渲染与后续追踪。"""
        meeting_info = MeetingInfo(
            meeting_type=request.meeting_type,
            meeting_name=request.meeting_name,
            meeting_time=request.meeting_time,
            location=request.location or request.venue_name,
            attendees=request.attendees or [],
            host=request.host,
            recorder=request.recorder,
        )
        topics = [TopicSection(topic_name=t) for t in request.topics]
        materials: List[MaterialCitation] = []
        history_ids: List[str] = []
        attachment_positions: List[str] = []
        for idx, ref in enumerate(refs):
            source_id = ref.source_id or (str(ref.pk) if ref.pk is not None else f"ref-{idx}")
            source_position = ref.source_position or (ref.level2 or ref.time or "")
            if ref.source == "minutes":
                history_ids.append(source_id)
            if ref.source == "attachment":
                attachment_positions.append(source_position or source_id)
            materials.append(
                MaterialCitation(
                    source_type=ref.source,
                    source_id=source_id,
                    source_position=source_position,
                    quote=ref.page_content[:200],
                    topic_name=ref.topic or None,
                    confidence=ref.confidence,
                    version=ref.version or None,
                )
            )

        traceability = TraceabilityInfo(
            history_minutes_ids=history_ids,
            attachment_positions=attachment_positions,
            speaker_resolution=speaker_resolutions,
        )
        return StructuredMinutesOutput(
            meeting_info=meeting_info,
            topics=topics,
            materials=materials,
            traceability=traceability,
        )
