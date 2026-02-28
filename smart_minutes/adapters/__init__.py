"""
Adapters: implementations of contracts

提供外部服务的适配器实现：
- Milvus 向量数据库
- 映射存储
- 发言人识别
"""

from smart_minutes.adapters.mapping_store import MappingStoreAdapter
from smart_minutes.adapters.speaker_resolver import SpeakerResolverAdapter

# Milvus 相关导入（可选依赖）
try:
    from smart_minutes.adapters.milvus_client import (
        MilvusClient,
        MilvusConfig,
        CollectionSchemaConfig,
        IndexConfig,
        SearchParams,
        create_milvus_client_from_env,
        get_milvus_client,
    )
    from smart_minutes.adapters.retrieval import (
        RetrievalAdapter,
        SchemaManager,
        create_retrieval_adapter,
    )
    HAS_MILVUS = True
except ImportError:
    HAS_MILVUS = False
    MilvusClient = None
    MilvusConfig = None
    CollectionSchemaConfig = None
    IndexConfig = None
    SearchParams = None

__all__ = [
    # 基础适配器
    "MappingStoreAdapter",
    "SpeakerResolverAdapter",
]

if HAS_MILVUS:
    __all__.extend([
        # Milvus 客户端
        "MilvusClient",
        "MilvusConfig",
        "CollectionSchemaConfig",
        "IndexConfig",
        "SearchParams",
        # 便捷函数
        "create_milvus_client_from_env",
        "get_milvus_client",
        # 检索适配器
        "RetrievalAdapter",
        "SchemaManager",
        "create_retrieval_adapter",
    ])
