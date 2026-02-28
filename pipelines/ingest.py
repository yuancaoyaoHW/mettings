"""入库流水线：从结构化 chunk 生成带向量的待插入行；可选调用传入的 inserter。

针对自部署 Qwen3-30B-A3B 优化：
- 全量使用 LLM 生成高质量字段（不考虑成本）
- 支持并发批量生成
- 支持长文本处理（利用 30B 模型的长上下文能力）
"""
import concurrent.futures
from typing import Any, Callable, Dict, List, Optional

from services.embedding import get_embedding
from services.llm import complete


_MINUTES_TYPE_ALIASES = {
    "issue": "open_issue",
    "open-issue": "open_issue",
    "openissue": "open_issue",
    "action_item": "todo",
    "action-item": "todo",
    "task": "todo",
    "decision": "conclusion",
}
_MINUTES_ALLOWED_TYPES = {"summary", "open_issue", "conclusion", "todo"}

# 扩展字段生成器注册表（用于动态生成 schema 字段）
_EXTENSION_FIELD_GENERATORS: Dict[str, Callable[[dict], Any]] = {}


def register_extension_field(field_name: str, generator: Callable[[dict], Any]):
    """注册扩展字段生成器。
    
    Args:
        field_name: 字段名
        generator: 接收 chunk dict，返回字段值的函数
    """
    _EXTENSION_FIELD_GENERATORS[field_name] = generator


def _embed_chunks(chunks: List[dict], text_key: str = "text") -> List[dict]:
    """对每条 chunk 的 text 做 embedding，写入 vector 字段。"""
    out = []
    for c in chunks:
        row = dict(c)
        text = row.get(text_key) or row.get("page_content") or ""
        row["vector"] = get_embedding(text)
        out.append(row)
    return out


def _normalize_minutes_type(raw_type: str) -> str:
    """分钟类 chunk type 归一化。"""
    if not raw_type:
        return ""
    key = str(raw_type).strip().lower()
    return _MINUTES_TYPE_ALIASES.get(key, key)


def _validate_minutes_chunk(chunk: dict) -> dict:
    """
    校验并标准化 minutes chunk：
    - type 仅允许 summary/open_issue/conclusion/todo
    - text 必须非空
    - todo 必须有 owner
    - open_issue 建议有 next_step（缺失时给空字符串）
    """
    normalized = dict(chunk)
    text = normalized.get("text", normalized.get("page_content", ""))
    if not str(text).strip():
        raise ValueError("minutes chunk text is required")

    source = str(normalized.get("source", "minutes") or "minutes").strip().lower()
    normalized["source"] = source

    # 仅对 minutes 做分索引规则校验；attachment/draft 走宽松校验。
    if source == "minutes":
        normalized_type = _normalize_minutes_type(normalized.get("type", ""))
        if normalized_type not in _MINUTES_ALLOWED_TYPES:
            raise ValueError(f"minutes chunk type must be one of {_MINUTES_ALLOWED_TYPES}, got: {normalized.get('type')}")
        normalized["type"] = normalized_type

        if normalized_type == "todo" and not str(normalized.get("owner", "")).strip():
            raise ValueError("todo chunk requires owner")
        if normalized_type == "open_issue":
            normalized.setdefault("next_step", "")
            normalized.setdefault("issue_reason", "")
    return normalized


# ==================== Qwen3-30B-A3B 字段生成函数 ====================

def _call_llm_with_retry(prompt: str, system: str = "", max_retries: int = 3) -> str:
    """调用 LLM 带重试机制。"""
    for attempt in range(max_retries):
        try:
            result = complete(prompt, system=system or "你是一个专业的文本分析助手")
            if result:
                return result.strip()
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"LLM 调用失败（{max_retries}次重试）: {e}")
                return ""
    return ""


def generate_summary_short(chunk: dict, max_length: int = 50) -> Optional[str]:
    """
    生成短摘要（50字以内）- 使用 Qwen3-30B-A3B。
    
    利用大模型的语义理解能力，生成高质量的简洁摘要。
    """
    text = chunk.get("text", chunk.get("page_content", ""))
    if not text:
        return None
    
    prompt = f"""请用不超过{max_length}字总结以下内容的要点。只输出摘要，不要有前缀。

内容：
{text[:3000]}

摘要："""
    
    result = _call_llm_with_retry(prompt, "你是一个专业的文本摘要助手")
    return result[:max_length] if result else None


def generate_summary_detailed(chunk: dict, max_length: int = 200) -> Optional[str]:
    """生成详细摘要（200字以内）- 使用 Qwen3-30B-A3B。"""
    text = chunk.get("text", chunk.get("page_content", ""))
    if not text:
        return None
    
    prompt = f"""请用不超过{max_length}字总结以下会议内容的要点，包括：
1. 主要讨论内容
2. 关键结论
3. 下一步行动（如有）

会议内容：
{text[:5000]}

详细摘要："""
    
    result = _call_llm_with_retry(prompt, "你是一个专业的会议纪要助手")
    return result[:max_length] if result else None


def generate_keywords(chunk: dict, max_keywords: int = 5) -> Optional[List[str]]:
    """
    提取关键词 - 使用 Qwen3-30B-A3B。
    
    比传统 TF-IDF 更准确，能理解语义关联。
    """
    text = chunk.get("text", chunk.get("page_content", ""))
    if not text:
        return None
    
    prompt = f"""请从以下内容中提取最多{max_keywords}个关键词。
要求：
1. 关键词应能代表内容核心主题
2. 优先选择专业术语、产品名、技术名
3. 用逗号分隔
4. 只输出关键词，不要序号

内容：
{text[:3000]}

关键词："""
    
    result = _call_llm_with_retry(prompt, "你是一个专业的关键词提取助手")
    if result:
        keywords = [k.strip() for k in result.split(",") if k.strip()]
        return keywords[:max_keywords]
    return None


def generate_sentiment(chunk: dict) -> Optional[str]:
    """
    情感分析 - 使用 Qwen3-30B-A3B。
    
    返回: positive / negative / neutral
    """
    text = chunk.get("text", chunk.get("page_content", ""))
    if not text:
        return None
    
    prompt = f"""请判断以下内容的情感倾向。
只回复以下之一：positive / negative / neutral
不要解释，只输出结果。

内容：
{text[:2000]}

情感倾向："""
    
    result = _call_llm_with_retry(prompt, "你是一个情感分析专家")
    if result:
        result_lower = result.lower()
        if "positive" in result_lower or "积极" in result or "正面" in result:
            return "positive"
        elif "negative" in result_lower or "消极" in result or "负面" in result:
            return "negative"
        else:
            return "neutral"
    return "neutral"


def generate_importance(chunk: dict) -> int:
    """
    重要性评分（1-5）- 使用 Qwen3-30B-A3B 进行智能评估。
    
    评估维度：
    - 内容类型（conclusion/todo > open_issue > summary）
    - 紧急程度关键词
    - 影响范围
    """
    text = chunk.get("text", chunk.get("page_content", ""))
    chunk_type = chunk.get("type", "")
    
    prompt = f"""请评估以下内容的重要性，返回 1-5 的数字。
评分标准：
5 = 关键决策/核心结论/阻塞性问题
4 = 重要结论/高优先级待办
3 = 一般讨论/普通待办
2 = 补充信息/低优先级
1 = 背景说明/参考信息

内容类型：{chunk_type}
内容：
{text[:2000]}

重要性评分（只输出数字）："""
    
    result = _call_llm_with_retry(prompt, "你是一个内容重要性评估专家")
    try:
        # 提取数字
        import re
        numbers = re.findall(r'\d+', result)
        if numbers:
            score = int(numbers[0])
            return max(1, min(5, score))  # 限制在 1-5
    except:
        pass
    
    # 回退到规则
    if chunk_type == "conclusion":
        return 5
    elif chunk_type == "todo":
        return 4
    elif chunk_type == "open_issue":
        return 4
    return 3


def generate_category(chunk: dict) -> Optional[str]:
    """
    智能分类 - 使用 Qwen3-30B-A3B。
    
    自动识别内容所属的业务类别。
    """
    text = chunk.get("text", chunk.get("page_content", ""))
    if not text:
        return None
    
    prompt = f"""请将以下内容分类到最合适的类别。
可选类别：产品需求 / 技术方案 / 项目管理 / 运营策略 / 人事行政 / 其他
只输出类别名称，不要解释。

内容：
{text[:2000]}

类别："""
    
    result = _call_llm_with_retry(prompt, "你是一个内容分类专家")
    return result if result else "其他"


def generate_action_items_structured(chunk: dict) -> Optional[List[dict]]:
    """
    结构化提取行动项 - 使用 Qwen3-30B-A3B。
    
    返回结构化数据，包含 content/owner/deadline。
    """
    text = chunk.get("text", chunk.get("page_content", ""))
    if not text:
        return None
    
    prompt = f"""请从以下会议纪要中提取所有行动项（待办事项）。
要求：
1. 识别明确的任务分配
2. 提取负责人姓名
3. 提取截止日期（如有）
4. 以 JSON 数组格式输出

输出格式：
[
  {{"content": "任务描述", "owner": "负责人", "deadline": "YYYY-MM-DD或描述"}},
  ...
]

会议纪要：
{text[:4000]}

行动项（JSON格式）："""
    
    result = _call_llm_with_retry(prompt, "你是一个专业的行动项提取助手")
    
    # 尝试解析 JSON
    if result:
        try:
            import json
            # 清理可能的 markdown 代码块
            if "```" in result:
                result = result.split("```")[1] if "```json" in result else result.replace("```", "")
            action_items = json.loads(result.strip())
            if isinstance(action_items, list):
                return action_items
        except:
            pass
    
    return None


def generate_decision_summary(chunk: dict) -> Optional[str]:
    """
    提取决策结论 - 使用 Qwen3-30B-A3B。
    
    专门用于 conclusion 类型的内容。
    """
    text = chunk.get("text", chunk.get("page_content", ""))
    if not text:
        return None
    
    prompt = f"""请从以下内容中提取关键决策/结论。
要求：
1. 只提取明确的决定、共识、方案选择
2. 用简洁的语言描述
3. 不超过100字
4. 如果没有明确决策，回复"无明确决策"

内容：
{text[:3000]}

决策结论："""
    
    result = _call_llm_with_retry(prompt, "你是一个专业的决策提取助手")
    return result if result else None


# 注册默认的扩展字段生成器
register_extension_field("summary_short", generate_summary_short)
register_extension_field("summary_detailed", generate_summary_detailed)
register_extension_field("keywords", generate_keywords)
register_extension_field("sentiment", generate_sentiment)
register_extension_field("importance", generate_importance)
register_extension_field("category", generate_category)
register_extension_field("action_items_structured", generate_action_items_structured)
register_extension_field("decision_summary", generate_decision_summary)


def _generate_extension_fields(chunk: dict, use_llm: bool = True) -> dict:
    """
    动态生成扩展字段。
    
    Args:
        chunk: 输入数据
        use_llm: 是否使用 LLM 生成（自部署模型设为 True）
    """
    extensions = {}
    
    if use_llm:
        # 使用 LLM 生成高质量字段（自部署模型场景）
        # 可以并行生成以提高效率
        fields_to_generate = [
            ("summary_short", generate_summary_short),
            ("keywords", generate_keywords),
            ("sentiment", generate_sentiment),
            ("importance", generate_importance),
            ("category", generate_category),
        ]
        
        for field_name, generator in fields_to_generate:
            try:
                value = generator(chunk)
                if value is not None:
                    extensions[field_name] = value
            except Exception as e:
                # 生成失败时跳过，不影响其他字段
                print(f"字段 {field_name} 生成失败: {e}")
    
    # 应用用户注册的自定义生成器
    for field_name, generator in _EXTENSION_FIELD_GENERATORS.items():
        if field_name not in extensions:  # 避免覆盖已生成的
            try:
                value = generator(chunk)
                if value is not None:
                    extensions[field_name] = value
            except Exception:
                pass
    
    return extensions


def _row_for_milvus(chunk: dict, enable_dynamic_fields: bool = True, use_llm_for_fields: bool = True) -> dict:
    """
    从 chunk 拼出符合 Milvus Schema 的单条 row。
    
    Args:
        chunk: 输入数据
        enable_dynamic_fields: 是否启用动态字段扩展
        use_llm_for_fields: 是否使用 LLM 生成扩展字段（自部署模型设为 True）
    """
    # 基础字段（固定 schema）
    row = {
        "text": chunk.get("text", chunk.get("page_content", "")),
        "vector": chunk["vector"],
        "source": chunk.get("source", ""),
        "type": chunk.get("type", ""),
        "level1": chunk.get("level1", ""),
        "level2": chunk.get("level2", ""),
        "topic": chunk.get("topic", ""),
        "author": chunk.get("author", ""),
        "time": chunk.get("time", ""),
        "version": chunk.get("version", ""),
        "owner": chunk.get("owner", ""),
        "deadline": chunk.get("deadline", ""),
        "status": chunk.get("status", ""),
        "next_step": chunk.get("next_step", ""),
        "issue_reason": chunk.get("issue_reason", ""),
        "source_id": chunk.get("source_id", ""),
        "source_position": chunk.get("source_position", ""),
        "confidence": chunk.get("confidence", None),
        "project": chunk.get("project", ""),
        "department": chunk.get("department", ""),
        "organization": chunk.get("organization", ""),
    }
    
    # 动态扩展字段
    if enable_dynamic_fields:
        # 优先使用 chunk 中已有的扩展字段
        for key in ["sentiment", "keywords", "summary_short", "importance", "category", 
                    "summary_detailed", "action_items_structured", "decision_summary"]:
            if key in chunk:
                row[key] = chunk[key]
        
        # 使用 LLM 生成缺失的字段
        if use_llm_for_fields:
            generated = _generate_extension_fields(chunk, use_llm=True)
            for key, value in generated.items():
                if key not in row or not row[key]:  # 只填充缺失的
                    row[key] = value
    
    return row


def ingest_minutes_chunks(
    chunks: List[dict],
    *,
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
    enable_dynamic_fields: bool = True,
    use_llm_for_fields: bool = True,  # 自部署模型默认为 True
) -> List[dict]:
    """
    纪要 chunk 入库。
    
    Args:
        chunks: 待入库的数据块
        collection_name: Milvus collection 名称
        client: Milvus 客户端
        inserter: 自定义插入函数
        enable_dynamic_fields: 是否启用动态字段
        use_llm_for_fields: 是否使用 LLM 生成扩展字段（自部署模型推荐设为 True）
    
    Returns:
        若未提供 inserter/client，返回待插入的 rows
    """
    if not chunks:
        return []
    
    print(f"🔄 处理 {len(chunks)} 个 chunks，LLM 字段生成: {'开启' if use_llm_for_fields else '关闭'}")
    
    validated = [_validate_minutes_chunk(c) for c in chunks]
    embedded = _embed_chunks(validated)
    rows = [_row_for_milvus(c, enable_dynamic_fields=enable_dynamic_fields, use_llm_for_fields=use_llm_for_fields) for c in embedded]
    
    insert_fn = (getattr(client, "insert", None) if client and callable(getattr(client, "insert", None)) else None) or inserter
    if insert_fn and collection_name:
        insert_fn(collection_name, rows)
        print(f"✅ 成功入库 {len(rows)} 条记录到 {collection_name}")
        return []
    
    return rows


def ingest_attachments(
    chunks: List[dict],
    *,
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
    enable_dynamic_fields: bool = True,
    use_llm_for_fields: bool = True,
) -> List[dict]:
    """附件 chunk 入库。"""
    if not chunks:
        return []
    copy_chunks = [dict(c) for c in chunks]
    for c in copy_chunks:
        c.setdefault("source", "attachment")
    return ingest_minutes_chunks(
        copy_chunks, 
        collection_name=collection_name, 
        client=client, 
        inserter=inserter,
        enable_dynamic_fields=enable_dynamic_fields,
        use_llm_for_fields=use_llm_for_fields
    )


def ingest_draft_segments(
    segments: List[dict],
    *,
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
    enable_dynamic_fields: bool = True,
    use_llm_for_fields: bool = True,
) -> List[dict]:
    """口水稿按议题切分后的 segment 入库。"""
    if not segments:
        return []
    chunks = []
    for s in segments:
        chunks.append({
            "text": s.get("text", s.get("page_content", "")),
            "source": "draft",
            "type": "draft_segment",
            "topic": s.get("topic", ""),
            "level1": s.get("level1", ""),
            "level2": s.get("level2", ""),
            "author": s.get("author", ""),
            "time": s.get("time", ""),
            "version": s.get("version", ""),
        })
    return ingest_minutes_chunks(
        chunks, 
        collection_name=collection_name, 
        client=client, 
        inserter=inserter,
        enable_dynamic_fields=enable_dynamic_fields,
        use_llm_for_fields=use_llm_for_fields
    )


def ingest_structured_items(
    items: List[dict],
    *,
    item_type: str,
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
    enable_dynamic_fields: bool = True,
    use_llm_for_fields: bool = True,
) -> List[dict]:
    """针对 todo/open_issue/conclusion 的快捷入库。"""
    normalized_type = _normalize_minutes_type(item_type)
    if normalized_type not in {"todo", "open_issue", "conclusion"}:
        raise ValueError("item_type must be one of: todo, open_issue, conclusion")
    chunks = []
    for item in items:
        row = dict(item)
        row["source"] = row.get("source", "minutes")
        row["type"] = normalized_type
        chunks.append(row)
    return ingest_minutes_chunks(
        chunks, 
        collection_name=collection_name, 
        client=client, 
        inserter=inserter,
        enable_dynamic_fields=enable_dynamic_fields,
        use_llm_for_fields=use_llm_for_fields
    )
