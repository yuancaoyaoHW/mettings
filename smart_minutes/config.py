"""Smart minutes feature config (collection name, top_k, context budget)."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SmartMinutesConfig:
    """Config for smart_minutes module."""

    collection_name: str = ""
    default_top_k: int = 5
    context_token_budget: int = 8000
    sparse_weight: float = 0.5
    dense_weight: float = 0.5

    @classmethod
    def from_env(cls, collection_name: Optional[str] = None) -> "SmartMinutesConfig":
        import os
        return cls(
            collection_name=collection_name or os.environ.get("MILVUS_COLLECTION_NAME", ""),
            default_top_k=int(os.environ.get("DEFAULT_TOP_K", "5")),
            context_token_budget=int(os.environ.get("CONTEXT_TOKEN_BUDGET", "8000")),
        )
