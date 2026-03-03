"""独立查询 API：仅检索，不调 LLM。"""
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from smart_minutes import SmartMinutesService

router = APIRouter(tags=["query"])


def _get_service(request: Request) -> SmartMinutesService:
    return request.app.state.service


# ---------- 请求模型 ----------


class KbCollectionMixin(BaseModel):
    """kb_name / collection_name 可选参数。"""
    kb_name: Optional[str] = Field(default=None, description="知识库名")
    collection_name: Optional[str] = Field(default=None, description="Milvus 集合名")


class QuerySeriesRequest(KbCollectionMixin):
    meeting_type: str = Field(..., description="会议类型")
    meeting_name: str = Field(..., description="会议名称")
    top_k: Optional[int] = Field(default=5, description="返回条数")


class QueryByTopicRequest(KbCollectionMixin):
    topic_name: str = Field(..., description="议题名")
    top_k: Optional[int] = Field(default=5, description="返回条数")


class QueryAttachmentsRequest(KbCollectionMixin):
    meeting_type: str = Field(..., description="会议类型")
    meeting_name: str = Field(..., description="会议名称")


class QueryTopicFromDraftRequest(KbCollectionMixin):
    draft_text: str = Field(..., description="口水稿文本")
    top_k: Optional[int] = Field(default=5, description="返回条数")


class QuerySimilarTodosIssuesRequest(KbCollectionMixin):
    todos_or_issues: List[str] = Field(..., description="待办或遗留文本列表")
    top_k: Optional[int] = Field(default=5, description="返回条数")


class QuerySimilarConclusionsRequest(KbCollectionMixin):
    conclusions: List[str] = Field(..., description="结论文本列表")
    top_k: Optional[int] = Field(default=5, description="返回条数")


class QueryByPersonRequest(KbCollectionMixin):
    person_name: str = Field(..., description="人名（口头称呼或正式名）")
    top_k: Optional[int] = Field(default=5, description="返回条数")


class OralNameMappingItem(BaseModel):
    oral_name: str = Field(..., description="口头称呼")
    formal_name: str = Field(..., description="正式人名")
    employee_id: Optional[str] = Field(default=None, description="员工ID")


class AddOralNameMappingsRequest(BaseModel):
    mappings: List[OralNameMappingItem] = Field(..., description="映射列表")


class ChunkItem(BaseModel):
    chunk_id: str = Field(..., description="Chunk ID")
    text: str = Field(..., description="Chunk 文本")


class MatchChunksToTopicsRequest(BaseModel):
    chunks: List[ChunkItem] = Field(..., description="Chunk 列表")
    topics: List[str] = Field(..., description="主题列表")
    unclassified_label: Optional[str] = Field(default="未分类", description="未匹配时的标签")


class ExtractProperNounsRequest(BaseModel):
    kb_name: str = Field(..., description="知识库名")
    text: Optional[str] = Field(default=None, description="待提取文本")
    chunks: Optional[List[ChunkItem]] = Field(default=None, description="或提供 chunks")
    file_name: Optional[str] = Field(default=None, description="来源文档名")
    source_id: Optional[str] = Field(default=None, description="来源 ID")
    collection_name: Optional[str] = Field(default=None, description="集合名")


# ---------- 路由 ----------


@router.post("/api/v1/smart-minutes/query/series")
@router.post("/api/smart-minutes/query/series")
def query_series(request: Request, body: QuerySeriesRequest):
    """同系列历史纪要。"""
    svc = _get_service(request)
    result = svc.query_series(
        body.meeting_type,
        body.meeting_name,
        top_k=body.top_k or 5,
        kb_name=body.kb_name,
        collection_name=body.collection_name,
    )
    return result


@router.post("/api/v1/smart-minutes/query/by-topic")
@router.post("/api/smart-minutes/query/by-topic")
def query_by_topic(request: Request, body: QueryByTopicRequest):
    """议题/相似议题历史。"""
    svc = _get_service(request)
    result = svc.query_by_topic(
        body.topic_name,
        top_k=body.top_k or 5,
        kb_name=body.kb_name,
        collection_name=body.collection_name,
    )
    return result


@router.post("/api/v1/smart-minutes/query/attachments")
@router.post("/api/smart-minutes/query/attachments")
def query_attachments(request: Request, body: QueryAttachmentsRequest):
    """附件信息。"""
    svc = _get_service(request)
    result = svc.query_attachments(
        body.meeting_type,
        body.meeting_name,
        kb_name=body.kb_name,
        collection_name=body.collection_name,
    )
    return result


@router.post("/api/v1/smart-minutes/query/topic-from-draft")
@router.post("/api/smart-minutes/query/topic-from-draft")
def query_topic_from_draft(request: Request, body: QueryTopicFromDraftRequest):
    """口水稿→议题名。"""
    svc = _get_service(request)
    result = svc.query_topic_from_draft(
        body.draft_text,
        top_k=body.top_k or 5,
        kb_name=body.kb_name,
        collection_name=body.collection_name,
    )
    return result


@router.post("/api/v1/smart-minutes/query/similar-todos-issues")
@router.post("/api/smart-minutes/query/similar-todos-issues")
def query_similar_todos_issues(request: Request, body: QuerySimilarTodosIssuesRequest):
    """类似待办/遗留。"""
    svc = _get_service(request)
    result = svc.query_similar_todos_issues(
        body.todos_or_issues,
        top_k=body.top_k or 5,
        kb_name=body.kb_name,
        collection_name=body.collection_name,
    )
    return result


@router.post("/api/v1/smart-minutes/query/similar-conclusions")
@router.post("/api/smart-minutes/query/similar-conclusions")
def query_similar_conclusions(request: Request, body: QuerySimilarConclusionsRequest):
    """类似议题结论。"""
    svc = _get_service(request)
    result = svc.query_similar_conclusions(
        body.conclusions,
        top_k=body.top_k or 5,
        kb_name=body.kb_name,
        collection_name=body.collection_name,
    )
    return result


@router.post("/api/v1/smart-minutes/query/by-person")
@router.post("/api/smart-minutes/query/by-person")
def query_by_person(request: Request, body: QueryByPersonRequest):
    """按人查询。"""
    svc = _get_service(request)
    result = svc.query_by_person(
        body.person_name,
        top_k=body.top_k or 5,
        kb_name=body.kb_name,
        collection_name=body.collection_name,
    )
    return result


@router.post("/api/v1/smart-minutes/mappings/oral-names")
@router.post("/api/smart-minutes/mappings/oral-names")
def add_oral_name_mappings(request: Request, body: AddOralNameMappingsRequest):
    """批量添加或更新口头称呼映射。"""
    svc = _get_service(request)
    mappings = [
        {
            "oral_name": m.oral_name,
            "formal_name": m.formal_name,
            "employee_id": m.employee_id or "",
        }
        for m in body.mappings
    ]
    result = svc.add_oral_name_mappings(mappings)
    return result


@router.post("/api/v1/smart-minutes/match-chunks-to-topics")
@router.post("/api/smart-minutes/match-chunks-to-topics")
def match_chunks_to_topics(request: Request, body: MatchChunksToTopicsRequest):
    """Chunk-主题匹配：为每个 chunk 分配主题。"""
    svc = _get_service(request)
    chunks = [{"chunk_id": c.chunk_id, "text": c.text} for c in body.chunks]
    assignments = svc.match_chunks_to_topics(
        chunks,
        body.topics,
        unclassified_label=body.unclassified_label or "未分类",
    )
    return {"assignments": assignments}


@router.post("/api/v1/smart-minutes/extract-proper-nouns")
@router.post("/api/smart-minutes/extract-proper-nouns")
def extract_proper_nouns(request: Request, body: ExtractProperNounsRequest):
    """从文本或 chunks 提取专有名词并写入存储。"""
    svc = _get_service(request)
    chunks_data = None
    if body.chunks:
        chunks_data = [{"chunk_id": c.chunk_id, "text": c.text} for c in body.chunks]
    result = svc.extract_proper_nouns(
        body.kb_name,
        text=body.text,
        chunks=chunks_data,
        file_name=body.file_name,
        source_id=body.source_id,
        collection_name=body.collection_name,
    )
    return result


@router.get("/api/v1/smart-minutes/proper-nouns")
@router.get("/api/smart-minutes/proper-nouns")
def list_proper_nouns(
    request: Request,
    kb_name: str,
    collection_name: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
):
    """按知识库查询专有名词列表。"""
    svc = _get_service(request)
    result = svc.list_proper_nouns(
        kb_name,
        collection_name=collection_name,
        page=page,
        page_size=page_size,
    )
    return result
