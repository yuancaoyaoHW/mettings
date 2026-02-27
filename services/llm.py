"""统一 LLM 调用：OpenAI 兼容 API（含国产大模型）。"""
from typing import Iterator, Optional

import requests


def _load_defaults() -> tuple[str, str, str]:
    """读取默认 model/api_key/base_url。"""
    try:
        from config.settings import settings
    except Exception:
        settings = None
    model = (settings.llm_model_name if settings else "") or "gpt-3.5-turbo"
    api_key = (settings.llm_api_key if settings else "")
    base_url = (settings.llm_base_url if settings else "")
    return model, api_key, base_url


def _build_chat_url(base_url: str) -> str:
    """兼容 base_url 传根路径或完整 chat 路径。"""
    base = base_url.rstrip("/")
    return base if "chat" in base or "completions" in base else base + "/v1/chat/completions"


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
    default_model, default_key, default_base = _load_defaults()
    model = model or default_model
    api_key = api_key or default_key
    base_url = base_url if base_url is not None else default_base
    if not base_url or not api_key:
        return ""
    url = _build_chat_url(base_url)
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


def stream_complete(
    prompt: str,
    *,
    model: str = "",
    api_key: str = "",
    base_url: Optional[str] = None,
    system: Optional[str] = None,
) -> Iterator[str]:
    """流式调用 LLM，按增量返回文本 token。"""
    default_model, default_key, default_base = _load_defaults()
    model = model or default_model
    api_key = api_key or default_key
    base_url = base_url if base_url is not None else default_base
    if not base_url or not api_key:
        return
    url = _build_chat_url(base_url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 4096, "stream": True}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    try:
        with requests.post(url, json=payload, headers=headers, timeout=120, stream=True) as r:
            r.raise_for_status()
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip()
                if not line.startswith("data:"):
                    continue
                data_part = line[5:].strip()
                if data_part == "[DONE]":
                    break
                try:
                    import json
                    obj = json.loads(data_part)
                    choice = (obj.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield text
                except Exception:
                    continue
    except Exception:
        return
