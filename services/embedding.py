"""Unified embedding client (placeholder)."""
from typing import List


def get_embedding(text: str, *, model: str = "", base_url: str = "") -> List[float]:
    """Call embedding API; return 4096-dim vector. Placeholder returns zeros."""
    return [0.0] * 4096
