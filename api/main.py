"""FastAPI 应用：挂载 /api/smart-minutes。"""
from contextlib import asynccontextmanager
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from smart_minutes import SmartMinutesService
from smart_minutes.schemas import MinutesRequest, MinutesResponse
from smart_minutes.factory import create_service

# 导入 schema 管理路由与查询路由
from api.schema_manager import router as schema_router
from api.query_routes import router as query_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.service = create_service()
    yield
    app.state.service = None


app = FastAPI(title="Smart Minutes API", lifespan=lifespan)

# 挂载 schema 管理路由与查询路由
app.include_router(schema_router, prefix="/api/schema")
app.include_router(schema_router, prefix="/api/v1/schema")
app.include_router(query_router)


def _event_chunk(event: Dict[str, Any]) -> str:
    """输出阶段事件（非流式 token）。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _openai_stream_chunk(
    *,
    content: Optional[str] = None,
    model: str = "smart-minutes",
    chunk_id: Optional[str] = None,
    event: Optional[Dict[str, Any]] = None,
    finish_reason: Optional[str] = None,
) -> str:
    """输出 OpenAI ChatCompletions 风格的 SSE chunk。"""
    payload = {
        "id": chunk_id or f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": finish_reason,
        }],
    }
    if content is not None:
        payload["choices"][0]["delta"]["content"] = content
    if event is not None:
        payload["event"] = event
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/health")
def health() -> dict:
    """健康检查。"""
    return {"status": "ok"}


@app.post("/api/v1/smart-minutes/generate", response_model=MinutesResponse)
@app.post("/api/smart-minutes/generate", response_model=MinutesResponse)
def generate_minutes(request: MinutesRequest) -> MinutesResponse:
    """生成纪要：返回正文、引用、warnings/errors。"""
    service: SmartMinutesService = app.state.service
    return service.run(request, retrieve_only=False)


@app.post("/api/v1/smart-minutes/retrieve", response_model=MinutesResponse)
@app.post("/api/smart-minutes/retrieve", response_model=MinutesResponse)
def retrieve_only(request: MinutesRequest) -> MinutesResponse:
    """仅检索：不调用 LLM，返回 references、mapped_terms、resolved_speakers。"""
    service: SmartMinutesService = app.state.service
    return service.run(request, retrieve_only=True)


@app.post("/api/v1/smart-minutes/generate-stream")
@app.post("/api/smart-minutes/generate-stream")
def generate_minutes_stream(request: MinutesRequest) -> StreamingResponse:
    """先输出非流式阶段事件，再以 SSE 流式返回最终纪要正文。"""
    service: SmartMinutesService = app.state.service

    def gen():
        yield _event_chunk({
            "stage": "smart_minutes_start",
            "think": "已收到智能纪要请求，开始准备执行。",
            "meeting_name": request.meeting_name,
            "topics": request.topics,
        })

        prepared = service.prepare_generation(request)
        response: MinutesResponse = prepared["response"]
        context = prepared["context"]
        system_prompt = prepared["system_prompt"]
        user_prompt = prepared["user_prompt"]
        tool_suggestions = prepared.get("tool_suggestions") or []
        token_budget = prepared.get("token_budget", 8000)

        yield _event_chunk({
            "stage": "prepare_done",
            "think": "工具执行完成，开始流式生成纪要。",
            "tool_count": len(tool_suggestions),
            "reference_count": len(response.references),
            "warning_count": len(response.warnings),
            "token_budget": token_budget,
            "context_chars": len(context),
        })

        from services.llm import stream_complete
        streamed = False
        for token in stream_complete(user_prompt, system=system_prompt):
            streamed = True
            yield _openai_stream_chunk(content=token, model="smart-minutes")

        if not streamed:
            # 未配置 LLM 或流式失败时，给出占位结果，保证前端始终能收到正文。
            meeting_label = request.meeting_name or request.meeting_type or "未命名"
            topics_label = "、".join(request.topics) if request.topics else "（未提供）"
            fallback = (
                f"[纪要占位] 会议: {meeting_label}\n议题: {topics_label}\n\n"
                "参考上下文已纳入，LLM 未配置或流式调用失败。"
            )
            yield _openai_stream_chunk(content=fallback, model="smart-minutes")

        if response.warnings:
            yield _event_chunk({
                "stage": "warnings",
                "warnings": response.warnings,
                "partial": response.partial,
            })
        yield _openai_stream_chunk(model="smart-minutes", finish_reason="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- MD 文件入库 ----------


class IngestFromMdRequest(BaseModel):
    """MD 文件入库请求。"""
    kb_name: str = Field(..., description="知识库名")
    file_name: str = Field(..., description="文档名")
    collection_name: Optional[str] = Field(default=None, description="可选，默认用环境变量 MILVUS_COLLECTION_NAME")


class IngestFromMdResponse(BaseModel):
    """MD 文件入库响应。"""
    success: bool
    ingested_count: int = 0
    errors: List[str] = Field(default_factory=list)
    deleted_count: int = 0


@app.post("/api/v1/smart-minutes/ingest-from-md", response_model=IngestFromMdResponse)
@app.post("/api/smart-minutes/ingest-from-md", response_model=IngestFromMdResponse)
def ingest_from_md(request: IngestFromMdRequest) -> IngestFromMdResponse:
    """
    从 FILE_PATH 下读取 MD 文件，解析为 chunk，全量替换后入库 Milvus。
    路径结构：{FILE_PATH}/{kb_name}/{file_name}/vlm/*.md
    """
    service: SmartMinutesService = app.state.service
    result = service.ingest_from_md(
        kb_name=request.kb_name,
        file_name=request.file_name,
        collection_name=request.collection_name,
    )
    if not result["success"] and not result.get("ingested_count", 0):
        first_error = result.get("errors", [""])[0] or "入库失败"
        if "FILE_PATH" in first_error or "未配置" in first_error:
            raise HTTPException(status_code=400, detail=first_error)
        if "路径不存在" in first_error or "无 .md 文件" in first_error:
            raise HTTPException(status_code=404, detail=first_error)
    return IngestFromMdResponse(
        success=result["success"],
        ingested_count=result.get("ingested_count", 0),
        errors=result.get("errors", []),
        deleted_count=result.get("deleted_count", 0),
    )
