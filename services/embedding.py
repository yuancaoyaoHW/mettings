"""统一 Embedding 调用：返回 4096 维向量，与 Milvus Schema 一致。"""
from typing import List, Optional

import requests

VECTOR_DIM = 4096


def get_embedding(
    text: str,
    *,
    model: str = "",
    base_url: str = "",
) -> List[float]:
    """
    调用 Embedding API，返回 4096 维向量。
    若 model/base_url 未传，则从 config.settings 读取。
    请求体兼容 input/model，响应取 data[0].embedding。
    """
    try:
        from config.settings import settings
    except Exception:
        settings = None
    model = model or (getattr(settings, "embedding_model_name", None) if settings else "") or ""
    base_url = base_url or (getattr(settings, "embedding_base_url", None) if settings else "") or ""
    if not base_url:
        return [0.0] * VECTOR_DIM
    url = base_url.rstrip("/")
    if "embed" not in url.lower():
        url = url + "/embeddings"
    payload = {"input": text, "model": model} if model else {"input": text}
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        emb = (data.get("data") or [None])[0]
        if not emb:
            return [0.0] * VECTOR_DIM
        vec = emb.get("embedding") if isinstance(emb, dict) else emb
        if not vec or len(vec) != VECTOR_DIM:
            return [0.0] * VECTOR_DIM
        return list(vec)
    except Exception:
        return [0.0] * VECTOR_DIM
