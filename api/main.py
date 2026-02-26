"""FastAPI 应用：挂载 /api/smart-minutes。"""
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from smart_minutes import SmartMinutesService
from smart_minutes.adapters.mapping_store import MappingStoreAdapter
from smart_minutes.adapters.retrieval import RetrievalAdapter
from smart_minutes.adapters.speaker_resolver import SpeakerResolverAdapter
from smart_minutes.schemas import MinutesRequest, MinutesResponse


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
