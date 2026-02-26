"""统一门面：请求 → 路由/Agent → 响应。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from smart_minutes.schemas import MinutesRequest, MinutesResponse

if TYPE_CHECKING:
    from smart_minutes.contracts import IMappingStore, IRetrieval, ISpeakerResolver
    from smart_minutes.config import SmartMinutesConfig


class SmartMinutesService:
    """智能纪要唯一入口，依赖注入的检索/映射/发言人实现。"""

    def __init__(
        self,
        retrieval: IRetrieval,
        mapping_store: IMappingStore,
        speaker_resolver: Optional[ISpeakerResolver] = None,
        *,
        config: Optional[SmartMinutesConfig] = None,
    ):
        from smart_minutes.config import SmartMinutesConfig
        self._retrieval = retrieval
        self._mapping_store = mapping_store
        self._speaker_resolver = speaker_resolver
        self._config = config or SmartMinutesConfig.from_env()

    def run(self, request: MinutesRequest, *, retrieve_only: bool = False) -> MinutesResponse:
        """执行纪要生成或仅检索；内部走路由 + Agent。"""
        from smart_minutes.agents.minutes_agent import MinutesAgent
        from smart_minutes.agents.router import suggest_tools
        tool_suggestions = suggest_tools(request)
        agent = MinutesAgent(
            retrieval=self._retrieval,
            mapping_store=self._mapping_store,
            speaker_resolver=self._speaker_resolver,
            config=self._config,
        )
        return agent.run(request, tool_suggestions=tool_suggestions, retrieve_only=retrieve_only)
