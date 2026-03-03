"""Schema 管理：扩展字段注册、生成、迁移与预览。由 Facade 统一暴露。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============ 数据模型（与 HTTP 契约一致） ============

class ExtensionFieldConfig(BaseModel):
    """扩展字段配置。"""
    field_name: str = Field(..., description="字段名")
    field_type: str = Field(default="string", description="字段类型: string/int/float/bool/array")
    description: str = Field(default="", description="字段描述")
    generation_method: str = Field(
        default="llm",
        description="生成方式: llm/rule/none（外部传入）"
    )
    generation_prompt: Optional[str] = Field(
        default=None,
        description="LLM 生成提示词模板"
    )
    rule_expression: Optional[str] = Field(
        default=None,
        description="规则表达式（当 generation_method=rule 时）"
    )
    enabled: bool = Field(default=True, description="是否启用")


class FieldGenerationRequest(BaseModel):
    """字段生成请求。"""
    chunk_ids: Optional[List[str]] = Field(
        default=None,
        description="指定要处理的 chunk ID，None 表示全部"
    )
    fields: Optional[List[str]] = Field(
        default=None,
        description="指定要生成的字段，None 表示全部已注册字段"
    )
    batch_size: int = Field(default=100, ge=1, le=1000, description="批处理大小")


class FieldGenerationResponse(BaseModel):
    """字段生成响应。"""
    success: bool
    processed_count: int = 0
    failed_count: int = 0
    errors: List[str] = Field(default_factory=list)
    message: str = ""


class SchemaMigrationRequest(BaseModel):
    """Schema 迁移请求。"""
    source_collection: str
    target_collection: str
    embedding_dim: int = 768
    dry_run: bool = Field(default=False, description="仅预览，不实际执行")


class SchemaMigrationResponse(BaseModel):
    """Schema 迁移响应。"""
    success: bool
    message: str
    source_collection: str
    target_collection: str
    estimated_record_count: Optional[int] = None
    dry_run: bool


class SchemaInfoResponse(BaseModel):
    """Schema 信息响应。"""
    collection_name: str
    enable_dynamic_field: bool
    fields: List[Dict[str, Any]]
    extension_fields: List[ExtensionFieldConfig]
    total_records: Optional[int] = None


# 保留字段名（与 api/schema_manager 一致）
# 9 大功能核心字段：source, type, topic, author/owner, source_id, source_position
# level1/level2/version/deadline/status 若未使用，新集合或迁移时可不再创建
RESERVED_FIELDS = {
    "pk", "text", "vector", "source", "type", "level1", "level2",
    "topic", "author", "time", "version", "owner", "deadline",
    "status", "source_id", "source_position", "confidence",
    "project", "department", "organization",
}


class SchemaManagementBackend:
    """
    扩展字段注册表与 schema 操作实现。
    可由 Facade 注入；若需 Milvus schema/迁移，需传入 schema_manager（SchemaManager）。
    """

    def __init__(
        self,
        schema_manager: Optional[Any] = None,
        *,
        extension_registry: Optional[Dict[str, ExtensionFieldConfig]] = None,
    ):
        self._schema_manager = schema_manager
        self._registry: Dict[str, ExtensionFieldConfig] = extension_registry or {}

    def get_schema_info(self, collection_name: str) -> SchemaInfoResponse:
        """获取 Collection 的 Schema 信息。"""
        enable_dynamic = True
        total_records: Optional[int] = None
        fields: List[Dict[str, Any]] = [
            {"name": "pk", "type": "INT64", "is_primary": True},
            {"name": "text", "type": "VARCHAR", "max_length": 65535},
            {"name": "vector", "type": "FLOAT_VECTOR", "dim": 768},
            {"name": "source", "type": "VARCHAR", "max_length": 64},
            {"name": "type", "type": "VARCHAR", "max_length": 64},
        ]
        if self._schema_manager is not None:
            try:
                schema = self._schema_manager.get_collection_schema(collection_name)
                if schema:
                    enable_dynamic = schema.get("enable_dynamic_field", True)
                    if "fields" in schema:
                        fields = schema["fields"]
                stats = getattr(
                    self._schema_manager, "get_collection_stats", None
                )
                if stats:
                    total_records = stats(collection_name).get("row_count")
            except Exception:
                pass
        return SchemaInfoResponse(
            collection_name=collection_name,
            enable_dynamic_field=enable_dynamic,
            fields=fields,
            extension_fields=list(self._registry.values()),
            total_records=total_records,
        )

    def register_extension_field(self, config: ExtensionFieldConfig) -> ExtensionFieldConfig:
        """注册扩展字段。"""
        if config.field_name in RESERVED_FIELDS:
            raise ValueError(f"Field name '{config.field_name}' is reserved")
        self._registry[config.field_name] = config
        if config.generation_method == "rule" and config.rule_expression:
            try:
                from pipelines.ingest import register_extension_field as register_ingest

                def rule_generator(chunk: dict) -> Any:
                    expr = config.rule_expression
                    if expr.startswith("$"):
                        field_name = expr[1:].split("[")[0]
                        value = chunk.get(field_name, "")
                        if "[" in expr and "]" in expr:
                            slice_str = expr[expr.find("[") + 1 : expr.find("]")]
                            if ":" in slice_str:
                                end = int(slice_str.split(":")[1]) if slice_str.split(":")[1] else None
                                value = value[:end] if isinstance(value, str) else value
                        return value
                    return expr

                register_ingest(config.field_name, rule_generator)
            except ImportError:
                pass
        return config

    def list_registered_fields(self) -> List[ExtensionFieldConfig]:
        """列出已注册的扩展字段。"""
        return list(self._registry.values())

    def unregister_extension_field(self, field_name: str) -> None:
        """注销扩展字段。"""
        if field_name not in self._registry:
            raise KeyError(f"Field '{field_name}' not found")
        del self._registry[field_name]

    def generate_fields_for_existing_data(
        self,
        request: FieldGenerationRequest,
        collection_name: str,
    ) -> FieldGenerationResponse:
        """为存量数据生成扩展字段（当前仅校验，不执行真实批处理）。"""
        fields_to_generate = request.fields or list(self._registry.keys())
        processed = 0
        failed = 0
        errors: List[str] = []
        for field_name in fields_to_generate:
            if field_name not in self._registry:
                failed += 1
                errors.append(f"Field '{field_name}' not registered")
                continue
            if self._registry[field_name].enabled:
                processed += 1
        return FieldGenerationResponse(
            success=False,
            processed_count=processed,
            failed_count=failed,
            errors=errors,
            message=(
                f"Field generation is not implemented yet for collection '{collection_name}'. "
                "Only field validation has been performed."
            ),
        )

    def migrate_collection(self, request: SchemaMigrationRequest) -> SchemaMigrationResponse:
        """迁移 Collection 到支持动态字段的新 Collection。"""
        if request.dry_run:
            return SchemaMigrationResponse(
                success=True,
                message="Dry run mode: migration plan validated",
                source_collection=request.source_collection,
                target_collection=request.target_collection,
                estimated_record_count=None,
                dry_run=True,
            )
        if self._schema_manager is None:
            return SchemaMigrationResponse(
                success=False,
                message="Schema manager not configured",
                source_collection=request.source_collection,
                target_collection=request.target_collection,
                dry_run=False,
            )
        ok = self._schema_manager.migrate_to_dynamic_field(
            source_collection=request.source_collection,
            target_collection=request.target_collection,
            embedding_dim=request.embedding_dim,
        )
        return SchemaMigrationResponse(
            success=ok,
            message=(
                f"Migration from '{request.source_collection}' to '{request.target_collection}' started"
                if ok else "Migration failed"
            ),
            source_collection=request.source_collection,
            target_collection=request.target_collection,
            dry_run=False,
        )

    def preview_field_generation(
        self,
        text: str,
        field_name: str,
        generation_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """预览字段生成效果，不写入数据库。"""
        from services.llm import complete

        prompt = generation_prompt or f"请从以下内容中提取 '{field_name}'：\n\n{text[:2000]}"
        result = complete(prompt, system="你是一个文本分析助手。")
        return {
            "field_name": field_name,
            "input_preview": text[:200],
            "generated_value": result.strip() if result else None,
            "prompt_used": prompt,
        }
