"""智能纪要模块配置（全局参数 + 会议类型模板）。"""
from dataclasses import dataclass, field
from typing import Dict, Optional

from smart_minutes.config_templates import MeetingTypeTemplate, load_templates_from_data, load_templates_from_file


@dataclass
class SmartMinutesConfig:
    """智能纪要配置对象。

    包含两类配置：
    - 全局默认参数（`default_top_k`、`dense_weight`、`sparse_weight` 等）；
    - `meeting_type` 模板集合（由 `templates` 承载）。
    """

    collection_name: str = ""  # Milvus 集合名
    default_top_k: int = 5
    context_token_budget: int = 8000  # 单次送入模型的 token 上限
    chars_per_token: int = 4  # 中文粗算：每 token 约 4 字，用于无 tokenizer 时
    sparse_weight: float = 0.5
    dense_weight: float = 0.5
    templates: Dict[str, MeetingTypeTemplate] = field(default_factory=dict)

    @classmethod
    def from_env(cls, collection_name: Optional[str] = None) -> "SmartMinutesConfig":
        """从环境变量读取配置并构建 SmartMinutesConfig。

        模板加载优先级：
        1) `SMART_MINUTES_TEMPLATES_PATH`（文件，JSON/YAML）；
        2) `SMART_MINUTES_TEMPLATES_JSON`（JSON 字符串）。
        """
        import json
        import os
        templates_path = os.environ.get("SMART_MINUTES_TEMPLATES_PATH", "").strip()
        templates_json = os.environ.get("SMART_MINUTES_TEMPLATES_JSON", "").strip()
        templates: Dict[str, MeetingTypeTemplate] = {}
        if templates_path:
            templates = load_templates_from_file(templates_path)
        elif templates_json:
            data = json.loads(templates_json)
            if isinstance(data, dict):
                templates = load_templates_from_data(data)
        return cls(
            collection_name=collection_name or os.environ.get("MILVUS_COLLECTION_NAME", ""),
            default_top_k=int(os.environ.get("DEFAULT_TOP_K", "5")),
            context_token_budget=int(os.environ.get("CONTEXT_TOKEN_BUDGET", "8000")),
            chars_per_token=int(os.environ.get("CHARS_PER_TOKEN", "4")),
            templates=templates,
        )
