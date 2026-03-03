"""
IRetrieval 实现：封装 Milvus 混合检索，支持动态字段。

使用新的 MilvusClient 提供完整功能。
"""
import logging
from typing import Any, Dict, List, Optional, Union

from smart_minutes.contracts import IRetrieval

# 导入新的 Milvus 客户端
try:
    from smart_minutes.adapters.milvus_client import (
        MilvusClient,
        MilvusConfig,
        SearchParams,
    )
    HAS_MILVUS_CLIENT = True
except ImportError:
    HAS_MILVUS_CLIENT = False

logger = logging.getLogger(__name__)


def _escape(s: str) -> str:
    """Milvus 字符串转义（防注入）。"""
    if not isinstance(s, str):
        return str(s)
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_expr(
    *,
    topic_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    level1_filter: Optional[str] = None,
    author_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    project_filter: Optional[str] = None,
    department_filter: Optional[str] = None,
    organization_filter: Optional[str] = None,
    # 新增：动态字段过滤
    dynamic_filters: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """拼装 Milvus 过滤表达式，支持动态字段。"""
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
    if project_filter:
        clauses.append(f'project == "{_escape(project_filter)}"')
    if department_filter:
        clauses.append(f'department == "{_escape(department_filter)}"')
    if organization_filter:
        clauses.append(f'organization == "{_escape(organization_filter)}"')
    
    # 动态字段过滤
    if dynamic_filters:
        for key, value in dynamic_filters.items():
            if isinstance(value, str):
                clauses.append(f'{key} == "{_escape(value)}"')
            elif isinstance(value, bool):
                clauses.append(f'{key} == {str(value).lower()}')
            elif isinstance(value, (int, float)):
                clauses.append(f'{key} == {value}')
            elif isinstance(value, list) and value:
                if len(value) == 1:
                    clauses.append(f'{key} == "{_escape(str(value[0]))}"')
                else:
                    # 使用 in 操作符
                    values_str = ", ".join([f'"{_escape(str(v))}"' for v in value])
                    clauses.append(f'{key} in [{values_str}]')
    
    return " and ".join(clauses) if clauses else None


def _hits_to_dicts(results: Any, output_fields: Optional[List[str]] = None) -> List[dict]:
    """将 client 返回的 hits 转为统一 dict 列表（支持动态字段）。"""
    default_fields = [
        "text", "source", "level1", "level2", "author", "time", 
        "version", "topic", "type", "owner", "deadline", "status",
        # 动态字段
        "sentiment", "keywords", "summary_short", "importance", "category",
        "summary_detailed", "decision_summary"
    ]
    fields_to_extract = output_fields or default_fields
    
    out = []
    if not results or not hasattr(results, "__getitem__"):
        return out
    
    # 处理 MilvusClient 返回的新格式
    if isinstance(results, list) and results and isinstance(results[0], list):
        # 搜索结果格式：[[hit1, hit2, ...], [...]]
        for group in results:
            for hit in group:
                item = _convert_hit_to_dict(hit, fields_to_extract)
                out.append(item)
    elif isinstance(results, list):
        # 查询结果格式：[{...}, {...}]
        for item in results:
            if isinstance(item, dict):
                out.append(item)
    
    return out


def _convert_hit_to_dict(hit: Any, fields: List[str]) -> dict:
    """将单个 hit 转换为字典"""
    if isinstance(hit, dict):
        # 新格式
        item = {
            "pk": hit.get("id"),
            "score": hit.get("distance", 0.0) if hit.get("distance") else hit.get("score", 0.0),
            "page_content": hit.get("text", ""),
        }
        # 添加其他字段
        for field in fields:
            if field in hit and field not in item:
                item[field] = hit[field]
        return item
    else:
        # 旧格式兼容
        return {
            "pk": getattr(hit, 'id', None),
            "score": getattr(hit, 'distance', 0.0),
            "page_content": "",
        }


class RetrievalAdapter(IRetrieval):
    """
    实现 IRetrieval：使用 MilvusClient 进行混合检索。
    
    支持功能：
    - 向量相似度搜索
    - 标量过滤
    - 动态字段过滤
    - 批量检索
    """

    def __init__(
        self,
        client: Any = None,
        collection_name: str = "",
        config: Optional[MilvusConfig] = None
    ):
        """
        初始化检索适配器
        
        Args:
            client: MilvusClient 实例或兼容对象
            collection_name: 默认集合名称
            config: Milvus 配置（用于创建新客户端）
        """
        self._collection_name = collection_name
        
        if client is not None:
            self._client = client
            self._owns_client = False
        elif HAS_MILVUS_CLIENT and config:
            self._client = MilvusClient(config)
            self._owns_client = True
        else:
            self._client = None
            self._owns_client = False
            logger.warning("MilvusClient not available, operations will fail")

    def __del__(self):
        """清理资源"""
        if self._owns_client and self._client:
            try:
                self._client.close()
            except:
                pass

    def get_client(self) -> Any:
        """获取底层 MilvusClient，用于 insert/delete 等操作。"""
        return self._client

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
        """
        执行混合检索
        
        Args:
            query_text: 查询文本（需要外部转换为向量）
            topic_filter: 议题过滤
            source_filter: 来源过滤
            level1_filter: 一级分类过滤
            author_filter: 作者过滤
            type_filter: 类型过滤
            top_k: 返回条数
            **kwargs: 额外参数
        
        Returns:
            检索结果列表
        """
        if self._client is None:
            logger.error("Milvus client not initialized")
            return []
        
        # 构建过滤表达式
        dynamic_filters = kwargs.pop("dynamic_filters", None)
        expr = _build_expr(
            topic_filter=topic_filter,
            source_filter=source_filter,
            level1_filter=level1_filter,
            author_filter=author_filter,
            type_filter=type_filter,
            project_filter=kwargs.get("project_filter"),
            department_filter=kwargs.get("department_filter"),
            organization_filter=kwargs.get("organization_filter"),
            dynamic_filters=dynamic_filters,
        )
        
        # 获取查询向量（从 kwargs 或通过 embedding 函数）
        query_vector = kwargs.get("query_vector")
        if query_vector is None and hasattr(self._client, 'embedding_func'):
            query_vector = self._client.embedding_func(query_text)
        
        if query_vector is None:
            logger.error("No query vector provided")
            return []
        
        # 构建搜索参数
        collection_name = kwargs.get("collection_name") or self._collection_name
        if not collection_name:
            logger.error("No collection name specified")
            return []
        
        # 构建输出字段
        output_fields = kwargs.get("output_fields") or [
            "id", "text", "source", "level1", "level2", "author", 
            "time", "version", "topic", "type", "owner", "deadline",
            "source_id", "source_position", "confidence",
            "sentiment", "keywords", "summary_short", "importance", "category"
        ]
        
        try:
            # 使用新的 MilvusClient 搜索
            if HAS_MILVUS_CLIENT and isinstance(self._client, MilvusClient):
                search_params = SearchParams(
                    top_k=top_k,
                    filter_expr=expr,
                    output_fields=output_fields,
                    nprobe=kwargs.get("nprobe", 128),
                    ef=kwargs.get("ef", 200),
                )
                
                results = self._client.search(
                    collection_name=collection_name,
                    vectors=[query_vector],
                    search_params=search_params,
                    metric_type=kwargs.get("metric_type", "COSINE"),
                )
            else:
                # 兼容旧接口
                results = self._client.search(
                    query_text=query_text,
                    knowledge_base_name=collection_name,
                    top_k=top_k,
                    filter=expr,
                    output_fields=output_fields,
                )
            
            return _hits_to_dicts(results, output_fields)
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def search_by_dynamic_filter(
        self,
        query_text: str,
        dynamic_filters: Dict[str, Any],
        *,
        top_k: int = 5,
        **kwargs
    ) -> List[dict]:
        """
        基于动态字段的高级检索
        
        Args:
            query_text: 查询文本
            dynamic_filters: 动态字段过滤条件
            top_k: 返回条数
        """
        return self.search(
            query_text=query_text,
            dynamic_filters=dynamic_filters,
            top_k=top_k,
            **kwargs
        )

    def batch_search(
        self,
        queries: List[str],
        *,
        top_k: int = 5,
        **kwargs
    ) -> List[List[dict]]:
        """
        批量检索
        
        Args:
            queries: 查询文本列表
            top_k: 每查询返回条数
        
        Returns:
            每组查询的结果列表
        """
        results = []
        for query in queries:
            result = self.search(query, top_k=top_k, **kwargs)
            results.append(result)
        return results


class SchemaManager:
    """管理 Milvus Collection Schema 的扩展和迁移。"""
    
    def __init__(self, client: MilvusClient):
        self._client = client
    
    def get_collection_schema(self, collection_name: str) -> Optional[Dict]:
        """获取当前 Collection 的 Schema 信息。"""
        return self._client.get_schema(collection_name)
    
    def check_dynamic_field_enabled(self, collection_name: str) -> bool:
        """检查 Collection 是否启用了动态字段。"""
        schema = self.get_collection_schema(collection_name)
        if schema:
            return schema.get("enable_dynamic_field", False)
        return False
    
    def list_collections(self) -> List[str]:
        """列出所有集合"""
        return self._client.list_collections()
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """获取集合统计信息"""
        return self._client.get_collection_stats(collection_name)
    
    def migrate_to_dynamic_field(
        self,
        source_collection: str,
        target_collection: str,
        embedding_dim: int = 768,
        batch_size: int = 1000
    ) -> bool:
        """
        迁移 Collection 到支持动态字段的新 Collection
        
        Args:
            source_collection: 源 Collection
            target_collection: 目标 Collection
            embedding_dim: 向量维度
            batch_size: 批处理大小
        """
        try:
            from smart_minutes.adapters.milvus_client import (
                CollectionSchemaConfig,
                IndexConfig,
            )
            
            # 1. 获取源集合的 schema
            old_schema = self.get_collection_schema(source_collection)
            if not old_schema:
                logger.error(f"Source collection '{source_collection}' not found")
                return False
            
            # 2. 创建新集合（启用动态字段）
            scalar_fields = [
                {"name": "source", "dtype": "VARCHAR", "max_length": 64},
                {"name": "type", "dtype": "VARCHAR", "max_length": 64},
                {"name": "level1", "dtype": "VARCHAR", "max_length": 256},
                {"name": "level2", "dtype": "VARCHAR", "max_length": 256},
                {"name": "topic", "dtype": "VARCHAR", "max_length": 256},
                {"name": "author", "dtype": "VARCHAR", "max_length": 128},
                {"name": "time", "dtype": "VARCHAR", "max_length": 32},
                {"name": "version", "dtype": "VARCHAR", "max_length": 32},
                {"name": "owner", "dtype": "VARCHAR", "max_length": 128},
                {"name": "deadline", "dtype": "VARCHAR", "max_length": 32},
                {"name": "status", "dtype": "VARCHAR", "max_length": 32},
                {"name": "source_id", "dtype": "VARCHAR", "max_length": 256},
                {"name": "source_position", "dtype": "VARCHAR", "max_length": 256},
            ]
            
            schema_config = CollectionSchemaConfig(
                collection_name=target_collection,
                description=f"Migrated from {source_collection} with dynamic fields",
                vector_dim=embedding_dim,
                enable_dynamic_field=True,
                scalar_fields=scalar_fields
            )
            
            index_config = IndexConfig(index_type="IVF_FLAT", params={"nlist": 128})
            
            self._client.create_collection(
                schema_config=schema_config,
                index_config=index_config,
                load_immediately=True
            )
            
            # 3. 数据迁移（分批读取、写入）
            # 这里简化处理，实际需要分页查询
            logger.info(f"Migration started: {source_collection} -> {target_collection}")
            logger.info("Note: Actual data migration should be implemented with pagination")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False


# ==================== 便捷函数 ====================

def create_retrieval_adapter(
    collection_name: str,
    milvus_uri: Optional[str] = None,
    **kwargs
) -> RetrievalAdapter:
    """
    创建检索适配器
    
    Args:
        collection_name: 集合名称
        milvus_uri: Milvus 连接 URI
        **kwargs: 额外配置
    
    Returns:
        RetrievalAdapter 实例
    """
    if not HAS_MILVUS_CLIENT:
        logger.error("MilvusClient not available")
        return RetrievalAdapter(client=None, collection_name=collection_name)
    
    config = MilvusConfig(
        uri=milvus_uri or kwargs.get("uri", ""),
        host=kwargs.get("host", "localhost"),
        port=kwargs.get("port", 19530),
        token=kwargs.get("token", ""),
        db_name=kwargs.get("db_name", "default"),
    )
    
    client = MilvusClient(config)
    return RetrievalAdapter(client=client, collection_name=collection_name)
