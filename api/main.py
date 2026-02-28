"""FastAPI 应用：挂载 /api/smart-minutes。"""
from contextlib import asynccontextmanager
import json
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from smart_minutes import SmartMinutesService
from smart_minutes.adapters.mapping_store import MappingStoreAdapter
from smart_minutes.adapters.retrieval import RetrievalAdapter
from smart_minutes.adapters.speaker_resolver import SpeakerResolverAdapter
from smart_minutes.schemas import MinutesRequest, MinutesResponse

# 导入 schema 管理路由
from api.schema_manager import router as schema_router


def _create_service() -> SmartMinutesService:
    """用 stub 适配器构造服务；生产环境可替换为真实 Milvus/DB。"""
    retrieval = RetrievalAdapter(client=None, collection_name="")
    mapping = MappingStoreAdapter(initial_oral_map={})
    speaker = SpeakerResolverAdapter()
    return SmartMinutesService(retrieval, mapping, speaker)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.service = _create_service()
    yield
    app.state.service = None


app = FastAPI(title="Smart Minutes API", lifespan=lifespan)

# 挂载 schema 管理路由
app.include_router(schema_router)


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


@app.post("/api/smart-minutes/generate", response_model=MinutesResponse)
def generate_minutes(request: MinutesRequest) -> MinutesResponse:
    """生成纪要：返回正文、引用、warnings/errors。"""
    service: SmartMinutesService = app.state.service
    return service.run(request, retrieve_only=False)


@app.post("/api/smart-minutes/retrieve", response_model=MinutesResponse)
def retrieve_only(request: MinutesRequest) -> MinutesResponse:
    """仅检索：不调用 LLM，返回 references、mapped_terms、resolved_speakers。"""
    service: SmartMinutesService = app.state.service
    return service.run(request, retrieve_only=True)


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
