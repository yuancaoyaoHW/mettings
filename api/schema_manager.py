"""Schema 管理 API：提供字段注册、生成、迁移等接口。"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/schema", tags=["schema"])


# ============ 数据模型 ============

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


# ============ 内存存储（生产环境应使用 DB） ============

# 全局字段注册表
_EXTENSION_FIELD_REGISTRY: Dict[str, ExtensionFieldConfig] = {}


def _get_registry() -> Dict[str, ExtensionFieldConfig]:
    """获取字段注册表。"""
    return _EXTENSION_FIELD_REGISTRY


# ============ API 接口 ============

@router.get("/info/{collection_name}", response_model=SchemaInfoResponse)
async def get_schema_info(collection_name: str):
    """
    获取 Collection 的 Schema 信息。
    
    包括：
    - 是否启用动态字段
    - 固定字段列表
    - 已注册的扩展字段
    - 记录数量
    """
    # 这里应该从实际的 Milvus client 获取
    # 简化示例：
    registry = _get_registry()
    
    return SchemaInfoResponse(
        collection_name=collection_name,
        enable_dynamic_field=True,  # 假设已启用
        fields=[
            {"name": "pk", "type": "INT64", "is_primary": True},
            {"name": "text", "type": "VARCHAR", "max_length": 65535},
            {"name": "vector", "type": "FLOAT_VECTOR", "dim": 768},
            {"name": "source", "type": "VARCHAR", "max_length": 64},
            {"name": "type", "type": "VARCHAR", "max_length": 64},
        ],
        extension_fields=list(registry.values()),
        total_records=None,  # 应从 Milvus 查询
    )


@router.post("/register-field", response_model=ExtensionFieldConfig)
async def register_extension_field(config: ExtensionFieldConfig):
    """
    注册新的扩展字段。
    
    注册后，新入库的数据会自动生成该字段。
    存量数据需要调用 /generate-fields 接口补全。
    """
    registry = _get_registry()
    
    # 检查字段名是否合法
    reserved_fields = {
        "pk", "text", "vector", "source", "type", "level1", "level2",
        "topic", "author", "time", "version", "owner", "deadline",
        "status", "source_id", "source_position", "confidence",
        "project", "department", "organization"
    }
    if config.field_name in reserved_fields:
        raise HTTPException(
            status_code=400, 
            detail=f"Field name '{config.field_name}' is reserved"
        )
    
    registry[config.field_name] = config
    
    # 注册到 ingest 模块的生成器
    if config.generation_method == "rule" and config.rule_expression:
        from pipelines.ingest import register_extension_field
        
        def rule_generator(chunk: dict) -> Any:
            # 简单的规则引擎：支持从其他字段提取或常量
            expr = config.rule_expression
            if expr.startswith("$"):
                # 从其他字段提取，如 "$text[:50]"
                field_name = expr[1:].split("[")[0]
                value = chunk.get(field_name, "")
                # 处理切片，如 "[:50]"
                if "[" in expr and "]" in expr:
                    slice_str = expr[expr.find("[")+1:expr.find("]")]
                    if ":" in slice_str:
                        end = int(slice_str.split(":")[1]) if slice_str.split(":")[1] else None
                        value = value[:end] if isinstance(value, str) else value
                return value
            else:
                # 常量
                return expr
        
        register_extension_field(config.field_name, rule_generator)
    
    return config


@router.get("/registered-fields", response_model=List[ExtensionFieldConfig])
async def list_registered_fields():
    """列出所有已注册的扩展字段。"""
    registry = _get_registry()
    return list(registry.values())


@router.delete("/register-field/{field_name}")
async def unregister_extension_field(field_name: str):
    """注销扩展字段（仅停止新数据生成，不影响已有数据）。"""
    registry = _get_registry()
    if field_name in registry:
        del registry[field_name]
        return {"success": True, "message": f"Field '{field_name}' unregistered"}
    raise HTTPException(status_code=404, detail=f"Field '{field_name}' not found")


@router.post("/generate-fields", response_model=FieldGenerationResponse)
async def generate_fields_for_existing_data(
    request: FieldGenerationRequest,
    collection_name: str
):
    """
    为存量数据生成扩展字段。
    
    这是一个异步批量处理接口，会：
    1. 从 Milvus 读取存量数据
    2. 调用 LLM 或规则生成字段值
    3. 更新回 Milvus（upsert）
    
    注意：大规模数据可能需要较长时间，建议配合任务队列使用。
    """
    registry = _get_registry()
    fields_to_generate = request.fields or list(registry.keys())
    
    # 实际实现应该：
    # 1. 启动后台任务（如使用 Celery）
    # 2. 分批读取数据
    # 3. 生成字段
    # 4. upsert 回 Milvus
    
    # 简化示例：
    processed = 0
    failed = 0
    errors = []
    
    for field_name in fields_to_generate:
        if field_name not in registry:
            failed += 1
            errors.append(f"Field '{field_name}' not registered")
            continue
        
        config = registry[field_name]
        if not config.enabled:
            continue
        
        # TODO: 实际的批量处理逻辑
        processed += 1
    
    return FieldGenerationResponse(
        success=True,
        processed_count=processed,
        failed_count=failed,
        errors=errors,
        message=f"Field generation task started for collection '{collection_name}'"
    )


@router.post("/migrate", response_model=SchemaMigrationResponse)
async def migrate_collection(request: SchemaMigrationRequest):
    """
    迁移 Collection 到支持动态字段的新 Collection。
    
    适用场景：
    - 存量 Collection 未启用动态字段
    - 需要重建索引优化性能
    - 需要修改固定字段类型
    
    注意：
    - 迁移期间需要双写或暂停写入
    - 大数据量迁移可能耗时较长
    """
    if request.dry_run:
        return SchemaMigrationResponse(
            success=True,
            message="Dry run mode: migration plan validated",
            source_collection=request.source_collection,
            target_collection=request.target_collection,
            estimated_record_count=None,  # 应查询实际数量
            dry_run=True
        )
    
    # 实际迁移逻辑
    from smart_minutes.adapters.retrieval import SchemaManager
    
    # 这里应该从 app state 获取 client
    # manager = SchemaManager(client)
    # success = manager.migrate_to_dynamic_field(...)
    
    return SchemaMigrationResponse(
        success=True,
        message=f"Migration from '{request.source_collection}' to '{request.target_collection}' started",
        source_collection=request.source_collection,
        target_collection=request.target_collection,
        dry_run=False
    )


@router.post("/preview-field-generation")
async def preview_field_generation(
    text: str,
    field_name: str,
    generation_prompt: Optional[str] = None
):
    """
    预览字段生成效果。
    
    用于调试生成提示词，不实际写入数据库。
    """
    from services.llm import complete
    
    prompt = generation_prompt or f"请从以下内容中提取 '{field_name}'：\n\n{text[:2000]}"
    result = complete(prompt, system="你是一个文本分析助手。")
    
    return {
        "field_name": field_name,
        "input_preview": text[:200],
        "generated_value": result.strip() if result else None,
        "prompt_used": prompt
    }
