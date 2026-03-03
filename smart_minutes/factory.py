"""应用层工厂：负责统一装配 SmartMinutesService 及其依赖（检索/映射/发言人等）。"""
import os
from typing import Optional

from smart_minutes.api import SmartMinutesService
from smart_minutes.adapters.mapping_store import MappingStoreAdapter
from smart_minutes.adapters.retrieval import RetrievalAdapter
from smart_minutes.adapters.speaker_resolver import SpeakerResolverAdapter
from smart_minutes.schema_management import SchemaManagementBackend


def create_stub_service() -> SmartMinutesService:
    """构造本地开发可用的 stub 服务。"""
    retrieval = RetrievalAdapter(client=None, collection_name="")
    mapping = MappingStoreAdapter(initial_oral_map={})
    speaker = SpeakerResolverAdapter()
    schema_backend = SchemaManagementBackend()
    return SmartMinutesService(
        retrieval, mapping, speaker,
        schema_management=schema_backend,
        proper_noun_store=None,
    )


def _resolve_milvus_uri() -> Optional[str]:
    """解析 Milvus URI：优先 MILVUS_URI，否则由 MILVUS_IP+MILVUS_PORT 或 MILVUS_HOST+MILVUS_PORT 构建。"""
    uri = os.getenv("MILVUS_URI")
    if uri:
        return uri
    ip = os.getenv("MILVUS_IP") or os.getenv("MILVUS_HOST")
    port = os.getenv("MILVUS_PORT", "19530")
    if ip:
        return f"http://{ip}:{port}"
    return None


def create_service_from_env() -> Optional[SmartMinutesService]:
    """按环境变量创建生产适配器；无配置时返回 None。"""
    milvus_uri = os.getenv("MILVUS_URI") or _resolve_milvus_uri()
    has_retrieval_env = bool(
        os.getenv("MILVUS_COLLECTION_NAME") or milvus_uri
    )
    has_mapping_env = bool(
        os.getenv("MAPPING_DB_URI")
        or os.getenv("MYSQL_USER")
        or os.getenv("DB_USER")
    )
    if not (has_retrieval_env or has_mapping_env):
        return None

    collection_name = os.getenv("MILVUS_COLLECTION_NAME", "")
    retrieval = RetrievalAdapter(client=None, collection_name=collection_name)
    if has_retrieval_env:
        from smart_minutes.adapters.retrieval import create_retrieval_adapter

        retrieval = create_retrieval_adapter(
            collection_name=collection_name,
            milvus_uri=milvus_uri,
            token=os.getenv("MILVUS_TOKEN", ""),
            db_name=os.getenv("MILVUS_DB_NAME", "default"),
        )

    mapping = MappingStoreAdapter(initial_oral_map={})
    if has_mapping_env:
        from smart_minutes.adapters.stores.mapping_mysql import create_mapping_store_from_env

        mapping = create_mapping_store_from_env() or mapping

    speaker = SpeakerResolverAdapter()
    schema_backend = SchemaManagementBackend()
    proper_noun_store = None
    if has_mapping_env:
        from smart_minutes.adapters.stores.proper_noun_store import create_proper_noun_store_from_env
        proper_noun_store = create_proper_noun_store_from_env()
    return SmartMinutesService(
        retrieval, mapping, speaker,
        schema_management=schema_backend,
        proper_noun_store=proper_noun_store,
    )


def create_service() -> SmartMinutesService:
    """优先按环境变量创建生产服务，失败时回退到 stub。"""
    return create_service_from_env() or create_stub_service()
