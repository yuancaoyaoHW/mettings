"""智能纪要模块配置（集合名、top_k、上下文预算等）。"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SmartMinutesConfig:
    """本功能配置项。"""

    collection_name: str = ""  # Milvus 集合名
    default_top_k: int = 5
    context_token_budget: int = 8000  # 单次送入模型的 token 上限
    sparse_weight: float = 0.5
    dense_weight: float = 0.5

    @classmethod
    def from_env(cls, collection_name: Optional[str] = None) -> "SmartMinutesConfig":
        """从环境变量读取配置。"""
        import os
        return cls(
            collection_name=collection_name or os.environ.get("MILVUS_COLLECTION_NAME", ""),
            default_top_k=int(os.environ.get("DEFAULT_TOP_K", "5")),
            context_token_budget=int(os.environ.get("CONTEXT_TOKEN_BUDGET", "8000")),
        )
