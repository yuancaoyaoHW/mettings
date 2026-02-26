"""IRetrieval 实现：封装 Milvus 混合检索。"""
from typing import Any, List, Optional


def _escape(s: str) -> str:
    """Milvus 字符串转义（防注入）。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_expr(
    *,
    topic_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    level1_filter: Optional[str] = None,
    author_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
) -> Optional[str]:
    """拼装 Milvus 过滤表达式。"""
    clauses = []
    if source_filter:
        clauses.append(f'source == "{_escape(source_filter)}"')
    if topic_filter:
        clauses.append(f'topic == "{_escape(topic_filter)}"')
    if level1_filter:
        clauses.append(f'level1 == "{_escape(level1_filter)}"')
    if author_filter:
        clauses.append(f'author == "{_escape(author_filter)}"')
    if type_filter:
        clauses.append(f'type == "{_escape(type_filter)}"')
    return " and ".join(clauses) if clauses else None


def _hits_to_dicts(results: Any, output_fields: Optional[List[str]] = None) -> List[dict]:
    """将 client 返回的 hits 转为统一 dict 列表（pk、score、page_content 等）。"""
    default_fields = ["text", "source", "level1", "level2", "author", "time", "version", "topic"]
    out = []
    if not results or not hasattr(results, "__getitem__"):
        return out
    hits = results[0] if results and len(results) > 0 else []
    for hit in hits:
        entity = hit.get("entity", hit) if isinstance(hit, dict) else {}
        dist = hit.get("distance", 0.0) if isinstance(hit, dict) else 0.0
        pk = hit.get("id", hit.get("pk"))
        text = entity.get("text", entity.get("page_content", ""))
        out.append({
            "pk": pk,
            "score": dist,
            "page_content": text,
            "source": entity.get("source", ""),
            "level1": entity.get("level1", ""),
            "level2": entity.get("level2", ""),
            "author": entity.get("author", ""),
            "time": entity.get("time", ""),
            "version": entity.get("version", ""),
            "topic": entity.get("topic", ""),
        })
    return out


class RetrievalAdapter:
    """实现 IRetrieval：按过滤条件拼 expr，调用 client.search，返回统一列表。"""

    def __init__(self, client: Any, collection_name: str):
        self._client = client
        self._collection_name = collection_name

    def search(
        self,
        query_text: str,
        *,
        topic_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        level1_filter: Optional[str] = None,
        author_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[dict]:
        """按过滤条件拼 expr，调用 client.search，返回 dict 列表。"""
        if self._client is None:
            return []
        expr = _build_expr(
            topic_filter=topic_filter,
            source_filter=source_filter,
            level1_filter=level1_filter,
            author_filter=author_filter,
            type_filter=type_filter,
        )
        try:
            if not callable(getattr(self._client, "search", None)):
                return []
            file_list = [source_filter] if source_filter else None
            kwargs: dict = {
                "query_text": query_text,
                "knowledge_base_name": self._collection_name,
                "top_k": top_k,
                "topic_filter": topic_filter,
                "file_list": file_list,
            }
            if expr:
                kwargs["filter"] = expr
            raw = self._client.search(**kwargs)
            return _hits_to_dicts(raw)
        except Exception:
            return []
