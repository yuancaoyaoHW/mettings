"""
专有名词提取：从文本中提取专有名词（仅提取不解释）
"""
import json
import logging
import re
from typing import List

logger = logging.getLogger(__name__)


def extract_proper_nouns_from_text(text: str) -> List[str]:
    """
    从文本中提取专有名词。优先使用 LLM，失败时回退到简单规则。

    Returns:
        专有名词列表（去重）
    """
    if not text or not text.strip():
        return []

    try:
        from services.llm import complete
    except ImportError:
        return _extract_by_rules(text)

    system = (
        "你是一个专有名词提取助手。从给定文本中提取专有名词，包括："
        "人名、公司名、产品名、项目名、技术术语、缩写等。"
        "只输出 JSON 数组，例如 [\"名词1\", \"名词2\"]，不要其他解释。"
    )
    prompt = f"文本：\n{text[:3000]}\n\n请提取专有名词，输出 JSON 数组："
    result = complete(prompt, system=system)
    if not result:
        return _extract_by_rules(text)

    result = result.strip()
    # 尝试解析 JSON
    candidates = [result]
    if "```" in result:
        parts = result.split("```")
        if len(parts) >= 2:
            candidates.append(parts[1])
    for raw in candidates:
        if not raw:
            continue
        raw = re.sub(r"^```\w*\n?", "", raw).strip()
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                terms = [str(x).strip() for x in arr if x and len(str(x).strip()) > 1]
                return list(dict.fromkeys(terms))
        except json.JSONDecodeError:
            pass

    return _extract_by_rules(text)


def _extract_by_rules(text: str) -> List[str]:
    """简单规则提取：中英文专有名词模式。"""
    terms = set()
    # 中文：2-8 个连续汉字（排除常见词）
    for m in re.finditer(r"[\u4e00-\u9fff]{2,8}", text):
        w = m.group()
        if w not in ("的", "是", "在", "和", "与", "或", "及", "等", "不", "有", "为", "了"):
            terms.add(w)
    # 英文：首字母大写的单词
    for m in re.finditer(r"\b[A-Z][a-zA-Z0-9]{1,20}\b", text):
        terms.add(m.group())
    return list(terms)
