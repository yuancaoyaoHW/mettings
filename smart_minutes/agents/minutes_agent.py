"""Minutes generation agent: run suggested tools, assemble context, call LLM under token budget."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from smart_minutes.schemas import ErrorItem, MinutesRequest, MinutesResponse, ReferenceItem

if False:
    from smart_minutes.contracts import IMappingStore, IRetrieval, ISpeakerResolver
    from smart_minutes.config import SmartMinutesConfig


class MinutesAgent:
    """Runs tool sequence, merges results, truncates to context_token_budget, generates minutes."""

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
        """Execute tool list, collect references, optionally call LLM. Respects context_token_budget."""
        refs: List[ReferenceItem] = []
        resolved_speakers: List[str] = []
        mapped_terms: List[str] = []
        warnings: List[str] = []
        errors: List[ErrorItem] = []

        for step in tool_suggestions:
            tool_name = step.get("tool") or ""
            params = step.get("params") or {}
            try:
                out = self._run_one_tool(tool_name, params, request)
                if isinstance(out, list):
                    for it in out:
                        if isinstance(it, dict):
                            if "page_content" in it or it.get("topic"):
                                refs.append(ReferenceItem(
                                    pk=it.get("pk"),
                                    score=it.get("score", 0.0),
                                    page_content=it.get("page_content", ""),
                                    source=it.get("source", ""),
                                    level1=it.get("level1", ""),
                                    level2=it.get("level2", ""),
                                    author=it.get("author", ""),
                                    time=it.get("time", ""),
                                    version=it.get("version", ""),
                                    topic=it.get("topic", ""),
                                ))
                        elif isinstance(it, str) and tool_name in ("mapping", "professional_terms"):
                            mapped_terms.append(it)
                elif isinstance(out, str) and tool_name == "resolve_speaker" and out:
                    resolved_speakers.append(out)
                elif isinstance(out, list) and tool_name in ("mapping", "professional_terms"):
                    mapped_terms.extend(x for x in out if isinstance(x, str))
            except Exception as e:
                warnings.append(f"{tool_name}: {e}")

        if retrieve_only:
            return MinutesResponse(
                minutes_content="",
                references=refs,
                resolved_speakers=resolved_speakers,
                mapped_terms=mapped_terms,
                warnings=warnings,
                partial=len(warnings) > 0,
            )

        # Assemble prompt under token budget and generate
        context_parts = self._assemble_context(refs, mapped_terms, resolved_speakers, request)
        budget = getattr(self._config, "context_token_budget", 8000)
        truncated = self._truncate_to_budget(context_parts, budget)
        try:
            minutes_content = self._generate_minutes(request, truncated)
        except Exception as e:
            errors.append(ErrorItem(code="GENERATE_ERROR", message=str(e)))
            minutes_content = ""
        return MinutesResponse(
            minutes_content=minutes_content,
            references=refs,
            resolved_speakers=resolved_speakers,
            mapped_terms=mapped_terms,
            errors=errors,
            warnings=warnings,
            partial=len(warnings) > 0 or len(errors) > 0,
        )

    def _run_one_tool(self, tool_name: str, params: dict, request: MinutesRequest) -> Any:
        """Dispatch to tools/adapters."""
        from smart_minutes.tools import rag, mapping, speaker, attachment, draft
        top_k = params.get("top_k", getattr(self._config, "default_top_k", 5))
        coll = getattr(self._config, "collection_name", "") or ""

        if tool_name == "mapping":
            names = params.get("oral_names") or []
            return [self._mapping_store.resolve_oral_to_formal(n) for n in names if self._mapping_store.resolve_oral_to_formal(n)]
        if tool_name == "professional_terms":
            return self._mapping_store.get_professional_terms(params.get("meeting_type", ""), params.get("meeting_name", ""))
        if tool_name == "retrieve_latest_minutes_by_series":
            return rag.retrieve_latest_minutes_by_series(self._retrieval, params.get("meeting_type", ""), params.get("meeting_name", ""), top_k)
        if tool_name == "retrieve_by_topic":
            return rag.retrieve_by_topic(self._retrieval, params.get("topic_name", ""), top_k)
        if tool_name == "retrieve_by_person":
            return rag.retrieve_by_person(self._retrieval, params.get("person_name", ""), top_k)
        if tool_name == "retrieve_similar_todos_or_issues":
            return rag.retrieve_similar_todos_or_issues(self._retrieval, params.get("text", ""), top_k)
        if tool_name == "retrieve_similar_conclusions":
            return rag.retrieve_similar_conclusions(self._retrieval, params.get("text", ""), top_k)
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
        """Simple char-based truncation (≈4 chars/token for Chinese)."""
        approx_tokens = budget * 4
        out = []
        for p in parts:
            if len("".join(out)) + len(p) <= approx_tokens:
                out.append(p)
            else:
                remain = approx_tokens - len("".join(out))
                if remain > 100:
                    out.append(p[:remain] + "...")
                break
        return "\n\n".join(out)

    def _generate_minutes(self, request: MinutesRequest, context: str) -> str:
        """Placeholder: no LLM call in Phase 1; return stub."""
        return f"[纪要占位] 会议: {request.meeting_name or request.meeting_type or '未命名'}\n议题: {', '.join(request.topics)}\n\n参考上下文已纳入，待接入 LLM 生成正文。"
