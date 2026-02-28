"""会议类型策略模板：定义数据模型与 JSON/YAML 加载入口。

本模块职责：
1) 约束 meeting_type 级别的模板结构；
2) 将外部配置（dict / json / yaml）规范化为强类型对象；
3) 对缺失文件等场景做温和降级（返回空模板表）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


@dataclass
class RetrievalWeights:
    """单类型检索权重（todo/open_issue/conclusion 通用）。"""

    dense_weight: Optional[float] = None
    sparse_weight: Optional[float] = None
    type_weight: float = 1.0

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "RetrievalWeights":
        """从字典解析权重，自动处理缺省值与数值转换。"""
        payload = dict(data or {})
        dense = payload.get("dense_weight")
        sparse = payload.get("sparse_weight")
        type_weight = payload.get("type_weight", 1.0)
        return cls(
            dense_weight=float(dense) if dense is not None else None,
            sparse_weight=float(sparse) if sparse is not None else None,
            type_weight=float(type_weight),
        )


@dataclass
class MeetingTypeTemplate:
    """会议类型策略模板。

    说明：
    - `top_k` 与权重均作为“默认值”，最终由路由按优先级合并；
    - `output_preferences` 预留给输出格式偏好（当前仅透传存储）。
    """

    meeting_type: str
    top_k: int = 5
    context_token_budget_multiplier: float = 1.0
    todo_weights: RetrievalWeights = field(default_factory=RetrievalWeights)
    open_issue_weights: RetrievalWeights = field(default_factory=RetrievalWeights)
    conclusion_weights: RetrievalWeights = field(default_factory=RetrievalWeights)
    output_preferences: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, meeting_type: str, data: Optional[Mapping[str, Any]]) -> "MeetingTypeTemplate":
        """从单个 meeting_type 对应配置构造模板对象。"""
        payload = dict(data or {})
        output_preferences = payload.get("output_preferences", {})
        if not isinstance(output_preferences, Mapping):
            output_preferences = {}
        return cls(
            meeting_type=meeting_type,
            top_k=int(payload.get("top_k", 5)),
            context_token_budget_multiplier=float(payload.get("context_token_budget_multiplier", 1.0)),
            todo_weights=RetrievalWeights.from_dict(payload.get("todo_weights")),
            open_issue_weights=RetrievalWeights.from_dict(payload.get("open_issue_weights")),
            conclusion_weights=RetrievalWeights.from_dict(payload.get("conclusion_weights")),
            output_preferences={str(k): str(v) for k, v in output_preferences.items()},
        )


TemplateMap = Dict[str, MeetingTypeTemplate]


def load_templates_from_data(data: Optional[Mapping[str, Any]]) -> TemplateMap:
    """从字典载入模板，键为 meeting_type，值为模板配置。"""
    out: TemplateMap = {}
    for meeting_type, raw_template in (data or {}).items():
        if not isinstance(meeting_type, str):
            continue
        if not isinstance(raw_template, Mapping):
            continue
        out[meeting_type] = MeetingTypeTemplate.from_dict(meeting_type, raw_template)
    return out


def _load_yaml_text(raw: str) -> Dict[str, Any]:
    """解析 YAML 文本；未安装 PyYAML 时给出明确错误。"""
    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise ValueError("YAML 模板解析需要安装 PyYAML（pip install pyyaml）。") from exc
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError("模板文件顶层必须是对象（meeting_type -> 配置）。")
    return data


def load_templates_from_file(path: str) -> TemplateMap:
    """从 JSON/YAML 文件载入模板。

    行为约定：
    - 文件不存在：返回空字典（不阻断启动）；
    - 后缀不明确：先按 JSON 解析，失败后回退 YAML；
    - 顶层必须是对象（meeting_type -> 模板）。
    """
    file_path = Path(path)
    if not file_path.exists():
        return {}
    raw = file_path.read_text(encoding="utf-8")
    ext = file_path.suffix.lower()
    if ext == ".json":
        data = json.loads(raw or "{}")
    elif ext in (".yaml", ".yml"):
        data = _load_yaml_text(raw)
    else:
        # 非标准后缀：优先按 JSON 解析，失败后再尝试 YAML。
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = _load_yaml_text(raw)
    if not isinstance(data, dict):
        raise ValueError("模板文件顶层必须是对象（meeting_type -> 配置）。")
    return load_templates_from_data(data)
