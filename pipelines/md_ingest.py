"""从 FILE_PATH 下的 MD 文件解析会议纪要并入库 Milvus。

路径结构：{FILE_PATH}/{kb_name}/{file_name}/vlm/*.md
- 调用方传入 kb_name、file_name
- 全量生成，入库前删除该文档已有 chunk
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.llm import complete

# 延迟导入避免循环依赖
def _get_ingest():
    from pipelines.ingest import ingest_minutes_chunks
    return ingest_minutes_chunks


_MINUTES_ALLOWED_TYPES = {"summary", "open_issue", "conclusion", "todo"}


def _call_llm_with_retry(prompt: str, system: str = "", max_retries: int = 3) -> str:
    """调用 LLM 带重试。"""
    for attempt in range(max_retries):
        try:
            result = complete(prompt, system=system or "你是一个专业的会议纪要分析助手")
            if result:
                return result.strip()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
    return ""


def _classify_segment(text: str, section_header: str = "") -> Dict[str, Any]:
    """
    使用 LLM 对段落进行分类，生成 type、topic、level1、level2、owner（todo 时）。
    """
    prompt = f"""请分析以下会议纪要段落，输出 JSON 格式的分类结果。

要求：
1. type 必须是以下之一：summary, open_issue, conclusion, todo
2. topic 为该段落的议题/主题（简短）
3. level1 为一级分类（如会议类型、大议题）
4. level2 为二级分类（如有）
5. 若 type 为 todo，必须包含 owner（负责人，无法确定时填"待定"）

段落标题：{section_header or "（无）"}
段落内容：
{text[:3000]}

只输出 JSON，不要其他文字。格式示例：
{{"type": "summary", "topic": "需求评审", "level1": "产品", "level2": "", "owner": ""}}
"""
    result = _call_llm_with_retry(prompt)
    # 尝试解析 JSON
    try:
        # 清理可能的 markdown 代码块
        raw = result.strip()
        if "```" in raw:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            else:
                raw = raw.split("```")[1].split("```")[0].strip()
        data = json.loads(raw)
        t = str(data.get("type", "summary")).strip().lower()
        if t not in _MINUTES_ALLOWED_TYPES:
            t = "summary"
        return {
            "type": t,
            "topic": str(data.get("topic", "")).strip() or "未分类",
            "level1": str(data.get("level1", "")).strip(),
            "level2": str(data.get("level2", "")).strip(),
            "owner": str(data.get("owner", "")).strip() or ("待定" if t == "todo" else ""),
        }
    except Exception:
        return {
            "type": "summary",
            "topic": "未分类",
            "level1": "",
            "level2": "",
            "owner": "",
        }


def _split_md_by_headers(content: str) -> List[tuple[str, str]]:
    """
    按 Markdown 标题（# 或 ##）切分内容，返回 [(section_header, section_text), ...]。
    """
    sections: List[tuple[str, str]] = []
    lines = content.split("\n")
    current_header = ""
    current_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        # 匹配 # 或 ## 开头的标题
        if stripped.startswith("#"):
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append((current_header, text))
            # 提取标题文本（去掉 # 和空格）
            current_header = re.sub(r"^#+\s*", "", stripped).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append((current_header, text))

    # 若没有标题切分，将整段作为单块
    if not sections and content.strip():
        sections.append(("", content.strip()))

    return sections


def _read_md_files(vlm_dir: Path) -> List[str]:
    """读取 vlm 目录下所有 .md 文件内容，合并为字符串列表（每个文件一个）。"""
    contents: List[str] = []
    for f in sorted(vlm_dir.glob("*.md")):
        try:
            contents.append(f.read_text(encoding="utf-8"))
        except Exception as e:
            raise IOError(f"读取文件失败 {f}: {e}") from e
    return contents


def _parse_md_to_chunks(
    kb_name: str,
    file_name: str,
    md_contents: List[str],
    use_llm_classify: bool = True,
) -> List[dict]:
    """
    将 MD 内容解析为 chunk 列表。
    每个 chunk 包含 text, source, type, topic, level1, level2, source_id, source_position 等。
    """
    source_id = f"{kb_name}/{file_name}"
    chunks: List[dict] = []
    position = 0

    for file_idx, content in enumerate(md_contents):
        sections = _split_md_by_headers(content)
        for sec_header, sec_text in sections:
            if not sec_text or len(sec_text) < 10:
                continue
            position += 1
            source_position = f"file{file_idx + 1}_sec{position}"

            if use_llm_classify:
                meta = _classify_segment(sec_text, sec_header)
                chunk_type = meta["type"]
                topic = meta["topic"]
                level1 = meta["level1"]
                level2 = meta["level2"]
                owner = meta.get("owner", "") or ("待定" if chunk_type == "todo" else "")
            else:
                chunk_type = "summary"
                topic = sec_header or "未分类"
                level1 = ""
                level2 = ""
                owner = ""

            chunk = {
                "text": sec_text,
                "page_content": sec_text,
                "source": "minutes",
                "type": chunk_type,
                "topic": topic,
                "level1": level1,
                "level2": level2,
                "source_id": source_id,
                "source_position": source_position,
                "owner": owner,
                "next_step": "",
                "issue_reason": "",
            }
            if chunk_type == "todo" and not chunk.get("owner"):
                chunk["owner"] = "待定"
            chunks.append(chunk)

    return chunks


def ingest_from_md(
    kb_name: str,
    file_name: str,
    *,
    file_path: str = "",
    collection_name: str = "",
    client: Any = None,
    inserter: Optional[Callable[[str, List[dict]], Any]] = None,
    enable_dynamic_fields: bool = True,
    use_llm_for_fields: bool = True,
    use_llm_classify: bool = True,
) -> Dict[str, Any]:
    """
    从 FILE_PATH 下读取 MD 文件，解析为 chunk，删除旧数据后入库。

    Args:
        kb_name: 知识库名
        file_name: 文档名
        file_path: MD 根路径，默认从 config.settings.file_path 读取
        collection_name: Milvus 集合名
        client: Milvus 客户端（需支持 insert、delete）
        inserter: 自定义插入函数
        enable_dynamic_fields: 是否启用动态字段
        use_llm_for_fields: 是否用 LLM 生成扩展字段
        use_llm_classify: 是否用 LLM 对段落分类

    Returns:
        {"success": bool, "ingested_count": int, "errors": List[str], "deleted_count": int}
    """
    errors: List[str] = []
    deleted_count = 0

    try:
        from config.settings import settings
        base_path = file_path or settings.file_path
    except Exception as e:
        return {
            "success": False,
            "ingested_count": 0,
            "errors": [f"FILE_PATH 未配置或读取失败: {e}"],
            "deleted_count": 0,
        }

    if not base_path:
        return {
            "success": False,
            "ingested_count": 0,
            "errors": ["环境变量 FILE_PATH 未配置"],
            "deleted_count": 0,
        }

    vlm_dir = Path(base_path) / kb_name / file_name / "vlm"
    if not vlm_dir.exists():
        return {
            "success": False,
            "ingested_count": 0,
            "errors": [f"路径不存在: {vlm_dir}，请检查 kb_name 和 file_name"],
            "deleted_count": 0,
        }

    md_files = list(vlm_dir.glob("*.md"))
    if not md_files:
        return {
            "success": False,
            "ingested_count": 0,
            "errors": [f"路径下无 .md 文件: {vlm_dir}"],
            "deleted_count": 0,
        }

    if not collection_name:
        return {
            "success": False,
            "ingested_count": 0,
            "errors": ["collection_name 未配置"],
            "deleted_count": 0,
        }

    try:
        md_contents = _read_md_files(vlm_dir)
    except IOError as e:
        return {
            "success": False,
            "ingested_count": 0,
            "errors": [str(e)],
            "deleted_count": 0,
        }

    chunks = _parse_md_to_chunks(kb_name, file_name, md_contents, use_llm_classify=use_llm_classify)
    if not chunks:
        return {
            "success": True,
            "ingested_count": 0,
            "errors": [],
            "deleted_count": 0,
        }

    source_id = f"{kb_name}/{file_name}"
    coll_name = collection_name

    # 删除该文档已有 chunk（全量替换）
    if client and coll_name and hasattr(client, "delete"):
        try:
            # Milvus 字符串需转义双引号
            escaped = source_id.replace("\\", "\\\\").replace('"', '\\"')
            expr = f'source_id == "{escaped}"'
            deleted_count = client.delete(coll_name, expr)
        except Exception as e:
            errors.append(f"删除旧数据失败（继续入库）: {e}")

    # 入库
    ingest_minutes_chunks = _get_ingest()
    try:
        ingest_minutes_chunks(
            chunks,
            collection_name=coll_name,
            client=client,
            inserter=inserter,
            enable_dynamic_fields=enable_dynamic_fields,
            use_llm_for_fields=use_llm_for_fields,
        )
        return {
            "success": len(errors) == 0,
            "ingested_count": len(chunks),
            "errors": errors,
            "deleted_count": deleted_count,
        }
    except Exception as e:
        errors.append(str(e))
        return {
            "success": False,
            "ingested_count": 0,
            "errors": errors,
            "deleted_count": deleted_count,
        }
