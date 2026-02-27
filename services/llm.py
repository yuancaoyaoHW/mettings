"""统一 LLM 调用：OpenAI 兼容 API（含国产大模型）。"""
from typing import Optional

import requests


def complete(
    prompt: str,
    *,
    model: str = "",
    api_key: str = "",
    base_url: Optional[str] = None,
    system: Optional[str] = None,
) -> str:
    """
    调用 LLM 补全。兼容 OpenAI / 国产大模型 chat 接口。
    若 model/api_key/base_url 未传，则从 config.settings 读取。
    """
    try:
        from config.settings import settings
    except Exception:
        settings = None
    model = model or (settings.llm_model_name if settings else "") or "gpt-3.5-turbo"
    api_key = api_key or (settings.llm_api_key if settings else "")
    base_url = base_url if base_url is not None else (settings.llm_base_url if settings else "")
    if not base_url or not api_key:
        return ""
    base = base_url.rstrip("/")
    url = base if "chat" in base or "completions" in base else base + "/v1/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 4096}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        choice = (data.get("choices") or [None])[0]
        if not choice:
            return ""
        msg = choice.get("message") or {}
        return (msg.get("content") or "").strip()
    except Exception:
        return ""
