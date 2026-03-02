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
    ):
        from smart_minutes.config import SmartMinutesConfig
        self._retrieval = retrieval
        self._mapping_store = mapping_store
        self._speaker_resolver = speaker_resolver
        self._config = config or SmartMinutesConfig.from_env()
        self._schema_management = schema_management

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
