"""从环境变量读取的应用配置。"""
import os
from typing import Optional


def _str(key: str, default: str = "") -> str:
    """读环境变量字符串。"""
    return os.environ.get(key, default)


def _int(key: str, default: int = 0) -> int:
    """读环境变量整数。"""
    v = os.environ.get(key)
    return int(v) if v is not None else default


class Settings:
    """全局配置（Milvus、Embedding、LLM、智能纪要等）。"""

    # Milvus
    milvus_uri: str = _str("MILVUS_URI")
    milvus_token: str = _str("MILVUS_TOKEN")
    milvus_db_name: str = _str("MILVUS_DB_NAME")
    milvus_collection_name: str = _str("MILVUS_COLLECTION_NAME")

    # Embedding
    embedding_base_url: str = _str("EMBEDDING_BASE_URL")
    embedding_model_name: str = _str("EMBEDDING_MODEL_NAME")

    # LLM
    llm_api_key: str = _str("LLM_API_KEY")
    llm_base_url: str = _str("LLM_BASE_URL")
    llm_model_name: str = _str("LLM_MODEL_NAME")

    # Rerank
    rerank_base_url: str = _str("RERANK_BASE_URL")
    rerank_model_name: str = _str("RERANK_MODEL_NAME")

    # Smart minutes
    context_token_budget: int = _int("CONTEXT_TOKEN_BUDGET", 8000)
    default_top_k: int = _int("DEFAULT_TOP_K", 5)

    # Mapping
    mapping_db_uri: Optional[str] = os.environ.get("MAPPING_DB_URI")

    # MD 文件入库：处理后的会议纪要 MD 根路径
    file_path: str = _str("FILE_PATH")


settings = Settings()
