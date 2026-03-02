"""Schema 管理 API：仅做请求/响应适配，统一调用 SmartMinutesService Facade。"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request

from smart_minutes import SmartMinutesService
from smart_minutes.schema_management import (
    ExtensionFieldConfig,
    FieldGenerationRequest,
    FieldGenerationResponse,
    SchemaInfoResponse,
    SchemaMigrationRequest,
    SchemaMigrationResponse,
)

router = APIRouter(tags=["schema"])


def _get_service(request: Request) -> SmartMinutesService:
    return request.app.state.service


@router.get("/info/{collection_name}", response_model=SchemaInfoResponse)
async def get_schema_info(request: Request, collection_name: str):
    """获取 Collection 的 Schema 信息。"""
    try:
        return _get_service(request).get_schema_info(collection_name)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/register-field", response_model=ExtensionFieldConfig)
async def register_extension_field(request: Request, config: ExtensionFieldConfig):
    """注册新的扩展字段。"""
    try:
        return _get_service(request).register_extension_field(config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/registered-fields", response_model=List[ExtensionFieldConfig])
async def list_registered_fields(request: Request):
    """列出所有已注册的扩展字段。"""
    try:
        return _get_service(request).list_registered_fields()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/register-field/{field_name}")
async def unregister_extension_field(request: Request, field_name: str):
    """注销扩展字段。"""
    try:
        _get_service(request).unregister_extension_field(field_name)
        return {"success": True, "message": f"Field '{field_name}' unregistered"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/generate-fields", response_model=FieldGenerationResponse)
async def generate_fields_for_existing_data(
    request: Request,
    body: FieldGenerationRequest,
    collection_name: str,
):
    """为存量数据生成扩展字段。"""
    try:
        return _get_service(request).generate_fields_for_existing_data(body, collection_name)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/migrate", response_model=SchemaMigrationResponse)
async def migrate_collection(request: Request, body: SchemaMigrationRequest):
    """迁移 Collection 到支持动态字段的新 Collection。"""
    try:
        return _get_service(request).migrate_collection(body)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/preview-field-generation")
async def preview_field_generation(
    request: Request,
    text: str,
    field_name: str,
    generation_prompt: Optional[str] = None,
):
    """预览字段生成效果。"""
    try:
        return _get_service(request).preview_field_generation(
            text, field_name, generation_prompt
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
