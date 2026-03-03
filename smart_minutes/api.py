"""统一门面：请求 → 路由/Agent → 响应；并统一暴露 schema 管理入口。

`SmartMinutesService` 是调用方唯一入口，负责将全局配置（含模板）
透传给路由，再由 Agent 执行工具并组装结果；可选注入 schema 管理后端，
对外提供 schema 信息、扩展字段注册/生成/迁移与预览。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from smart_minutes.schemas import MinutesRequest, MinutesResponse

if TYPE_CHECKING:
    from smart_minutes.contracts import IMappingStore, IRetrieval, ISpeakerResolver
    from smart_minutes.config import SmartMinutesConfig
    from smart_minutes.schema_management import (
        ExtensionFieldConfig,
        FieldGenerationRequest,
        FieldGenerationResponse,
        SchemaInfoResponse,
        SchemaMigrationRequest,
        SchemaMigrationResponse,
    )


class SmartMinutesService:
    """智能纪要唯一入口，依赖注入检索/映射/发言人实现；可选 schema 管理。"""

    def __init__(
        self,
        retrieval: IRetrieval,
        mapping_store: IMappingStore,
        speaker_resolver: Optional[ISpeakerResolver] = None,
        *,
        config: Optional[SmartMinutesConfig] = None,
        schema_management: Optional[Any] = None,
        proper_noun_store: Optional[Any] = None,
    ):
        from smart_minutes.config import SmartMinutesConfig
        self._retrieval = retrieval
        self._mapping_store = mapping_store
        self._speaker_resolver = speaker_resolver
        self._config = config or SmartMinutesConfig.from_env()
        self._schema_management = schema_management
        self._proper_noun_store = proper_noun_store

    def run(self, request: MinutesRequest, *, retrieve_only: bool = False) -> MinutesResponse:
        """执行纪要生成或仅检索；内部流程为 路由建议 + Agent 执行。"""
        from smart_minutes.agents.minutes_agent import MinutesAgent
        from smart_minutes.agents.router import suggest_tools
        tool_suggestions = suggest_tools(
            request,
            templates=getattr(self._config, "templates", None),
            default_top_k=getattr(self._config, "default_top_k", 5),
            default_dense_weight=getattr(self._config, "dense_weight", None),
            default_sparse_weight=getattr(self._config, "sparse_weight", None),
        )
        agent = MinutesAgent(
            retrieval=self._retrieval,
            mapping_store=self._mapping_store,
            speaker_resolver=self._speaker_resolver,
            config=self._config,
        )
        return agent.run(request, tool_suggestions=tool_suggestions, retrieve_only=retrieve_only)

    def prepare_generation(self, request: MinutesRequest) -> Dict[str, Any]:
        """执行非流式准备阶段，返回流式生成所需上下文与 Prompt。"""
        from smart_minutes.agents.minutes_agent import MinutesAgent
        from smart_minutes.agents.router import suggest_tools
        tool_suggestions = suggest_tools(
            request,
            templates=getattr(self._config, "templates", None),
            default_top_k=getattr(self._config, "default_top_k", 5),
            default_dense_weight=getattr(self._config, "dense_weight", None),
            default_sparse_weight=getattr(self._config, "sparse_weight", None),
        )
        agent = MinutesAgent(
            retrieval=self._retrieval,
            mapping_store=self._mapping_store,
            speaker_resolver=self._speaker_resolver,
            config=self._config,
        )
        prepared = agent.prepare_generation(request, tool_suggestions=tool_suggestions)
        prepared["tool_suggestions"] = tool_suggestions
        return prepared

    # ---------- Schema 管理（统一入口，委托给可选 backend） ----------

    def _require_schema_management(self) -> Any:
        if self._schema_management is None:
            raise ValueError("Schema management not configured")
        return self._schema_management

    def get_schema_info(self, collection_name: str) -> "SchemaInfoResponse":
        """获取 Collection 的 Schema 信息。"""
        from smart_minutes.schema_management import SchemaInfoResponse
        backend = self._require_schema_management()
        return backend.get_schema_info(collection_name)

    def register_extension_field(self, config: "ExtensionFieldConfig") -> "ExtensionFieldConfig":
        """注册扩展字段。"""
        from smart_minutes.schema_management import ExtensionFieldConfig
        backend = self._require_schema_management()
        return backend.register_extension_field(
            config if isinstance(config, ExtensionFieldConfig) else ExtensionFieldConfig(**config)
        )

    def list_registered_fields(self) -> List["ExtensionFieldConfig"]:
        """列出已注册的扩展字段。"""
        backend = self._require_schema_management()
        return backend.list_registered_fields()

    def unregister_extension_field(self, field_name: str) -> None:
        """注销扩展字段。"""
        backend = self._require_schema_management()
        backend.unregister_extension_field(field_name)

    def generate_fields_for_existing_data(
        self,
        request: "FieldGenerationRequest",
        collection_name: str,
    ) -> "FieldGenerationResponse":
        """为存量数据生成扩展字段。"""
        from smart_minutes.schema_management import (
            FieldGenerationRequest,
            FieldGenerationResponse,
        )
        backend = self._require_schema_management()
        req = request if isinstance(request, FieldGenerationRequest) else FieldGenerationRequest(**request)
        return backend.generate_fields_for_existing_data(req, collection_name)

    def migrate_collection(self, request: "SchemaMigrationRequest") -> "SchemaMigrationResponse":
        """迁移 Collection 到支持动态字段的新 Collection。"""
        from smart_minutes.schema_management import (
            SchemaMigrationRequest,
            SchemaMigrationResponse,
        )
        backend = self._require_schema_management()
        req = request if isinstance(request, SchemaMigrationRequest) else SchemaMigrationRequest(**request)
        return backend.migrate_collection(req)

    def preview_field_generation(
        self,
        text: str,
        field_name: str,
        generation_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """预览字段生成效果。"""
        backend = self._require_schema_management()
        return backend.preview_field_generation(text, field_name, generation_prompt)

    # ---------- 独立查询 API（仅检索，不调 LLM） ----------

    def _resolve_collection(self, kb_name: Optional[str], collection_name: Optional[str]) -> str:
        """解析 collection：优先 kb_name/collection_name，否则用 config。"""
        return (
            (collection_name or kb_name or "")
            or getattr(self._config, "collection_name", "")
            or ""
        )

    def query_series(
        self,
        meeting_type: str,
        meeting_name: str,
        *,
        top_k: int = 5,
        kb_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """同系列历史纪要。"""
        from smart_minutes.tools import rag
        coll = self._resolve_collection(kb_name, collection_name)
        items = rag.retrieve_latest_minutes_by_series(
            self._retrieval,
            meeting_type,
            meeting_name,
            top_k,
            collection_name=coll or None,
        )
        return {"items": items, "collection": coll}

    def query_by_topic(
        self,
        topic_name: str,
        *,
        top_k: int = 5,
        kb_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """议题/相似议题历史。"""
        from smart_minutes.tools import rag
        coll = self._resolve_collection(kb_name, collection_name)
        items = rag.retrieve_by_topic(
            self._retrieval,
            topic_name,
            top_k,
            collection_name=coll or None,
        )
        return {"items": items, "collection": coll}

    def query_attachments(
        self,
        meeting_type: str,
        meeting_name: str,
        *,
        kb_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """附件信息。"""
        from smart_minutes.tools import attachment
        coll = self._resolve_collection(kb_name, collection_name)
        items = attachment.get_attachments_by_meeting(
            self._retrieval,
            meeting_type,
            meeting_name,
            collection_name=coll or None,
        )
        return {"items": items, "collection": coll}

    def query_topic_from_draft(
        self,
        draft_text: str,
        *,
        top_k: int = 5,
        kb_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """口水稿→议题名。"""
        from smart_minutes.tools import rag
        coll = self._resolve_collection(kb_name, collection_name)
        items = rag.retrieve_similar_topic_by_draft(
            self._retrieval,
            draft_text,
            top_k,
            collection_name=coll or None,
        )
        return {"items": items, "collection": coll}

    def query_similar_todos_issues(
        self,
        todos_or_issues: List[str],
        *,
        top_k: int = 5,
        kb_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """类似待办/遗留。"""
        from smart_minutes.tools import rag
        coll = self._resolve_collection(kb_name, collection_name)
        text = "\n".join(todos_or_issues) if todos_or_issues else ""
        items = rag.retrieve_similar_todos_or_issues(
            self._retrieval,
            text,
            top_k,
            collection_name=coll or None,
        )
        return {"items": items, "collection": coll}

    def query_similar_conclusions(
        self,
        conclusions: List[str],
        *,
        top_k: int = 5,
        kb_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """类似议题结论。"""
        from smart_minutes.tools import rag
        coll = self._resolve_collection(kb_name, collection_name)
        text = "\n".join(conclusions) if conclusions else ""
        items = rag.retrieve_similar_conclusions(
            self._retrieval,
            text,
            top_k,
            collection_name=coll or None,
        )
        return {"items": items, "collection": coll}

    def query_by_person(
        self,
        person_name: str,
        *,
        top_k: int = 5,
        kb_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按人查询。若口头称呼对应多人，返回候选不查 Milvus。"""
        from smart_minutes.tools import rag
        coll = self._resolve_collection(kb_name, collection_name)
        candidates = getattr(
            self._mapping_store,
            "resolve_oral_to_formal_candidates",
            lambda _: [],
        )(person_name)
        if len(candidates) > 1:
            return {
                "items": [],
                "collection": coll,
                "oral_name": person_name,
                "formal_names": candidates,
                "ambiguous": True,
            }
        formal = candidates[0] if candidates else person_name
        items = rag.retrieve_by_person(
            self._retrieval,
            formal,
            top_k,
            collection_name=coll or None,
        )
        return {"items": items, "collection": coll}

    def add_oral_name_mappings(
        self,
        mappings: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """批量添加或更新口头称呼映射。"""
        store = self._mapping_store
        if hasattr(store, "batch_add_or_update_oral_name_mappings"):
            return store.batch_add_or_update_oral_name_mappings(mappings)
        return {"success_count": 0, "failed_count": len(mappings)}

    def match_chunks_to_topics(
        self,
        chunks: List[Dict[str, Any]],
        topics: List[str],
        *,
        unclassified_label: str = "未分类",
    ) -> List[Dict[str, Any]]:
        """Chunk-主题匹配：为每个 chunk 分配主题。"""
        from smart_minutes.tools.chunk_topic_matcher import match_chunks_to_topics as _match
        return _match(chunks, topics, unclassified_label=unclassified_label)

    def extract_proper_nouns(
        self,
        kb_name: str,
        *,
        text: Optional[str] = None,
        chunks: Optional[List[Dict[str, Any]]] = None,
        file_name: Optional[str] = None,
        source_id: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从文本或 chunks 提取专有名词并写入存储。"""
        from smart_minutes.tools.proper_noun_extractor import extract_proper_nouns_from_text
        store = self._proper_noun_store
        if not store:
            return {"success": False, "added": 0, "error": "专有名词存储未配置"}
        content = text or ""
        if not content and chunks:
            content = "\n".join(c.get("text", "") for c in chunks)
        if not content:
            return {"success": False, "added": 0, "error": "未提供 text 或 chunks"}
        terms = extract_proper_nouns_from_text(content)
        if not terms:
            return {"success": True, "added": 0}
        source_doc = file_name
        added = store.add_proper_nouns(
            kb_name,
            terms,
            collection_name=collection_name,
            source_doc=source_doc,
            source_id=source_id,
        )
        return {"success": True, "added": added}

    def list_proper_nouns(
        self,
        kb_name: str,
        *,
        collection_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """按知识库查询专有名词列表。"""
        store = self._proper_noun_store
        if not store:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        return store.list_by_kb(
            kb_name,
            collection_name=collection_name,
            page=page,
            page_size=page_size,
        )

    # ---------- MD 文件入库 ----------

    def ingest_from_md(
        self,
        kb_name: str,
        file_name: str,
        *,
        collection_name: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从 FILE_PATH 下读取 MD 文件，解析为 chunk，删除旧数据后入库 Milvus。

        Args:
            kb_name: 知识库名
            file_name: 文档名
            collection_name: 可选，默认用 config 的 collection_name
            file_path: 可选，默认用环境变量 FILE_PATH

        Returns:
            {"success": bool, "ingested_count": int, "errors": List[str], "deleted_count": int}
        """
        from pipelines.md_ingest import ingest_from_md as _ingest_from_md

        coll = collection_name or getattr(self._config, "collection_name", "") or ""
        client = getattr(self._retrieval, "get_client", lambda: None)()
        if client is None:
            return {
                "success": False,
                "ingested_count": 0,
                "errors": ["Milvus 未配置，无法入库"],
                "deleted_count": 0,
            }
        if not coll:
            return {
                "success": False,
                "ingested_count": 0,
                "errors": ["collection_name 未配置，请设置 MILVUS_COLLECTION_NAME 或传入 collection_name"],
                "deleted_count": 0,
            }
        return _ingest_from_md(
            kb_name,
            file_name,
            file_path=file_path or "",
            collection_name=coll,
            client=client,
            enable_dynamic_fields=True,
            use_llm_for_fields=True,
            use_llm_classify=True,
        )
