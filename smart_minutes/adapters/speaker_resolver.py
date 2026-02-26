"""ISpeakerResolver 实现：人脸/声纹/会场 → 正式人名。"""
from typing import Any, Optional


class SpeakerResolverAdapter:
    """实现 ISpeakerResolver；可配置外部人脸/声纹 API，按置信度融合。"""

    def __init__(self, api_config: Optional[dict] = None):
        self._api_config = api_config or {}

    def resolve_speaker(
        self,
        face_result: Any = None,
        voice_result: Any = None,
        venue_name: Optional[str] = None,
    ) -> Optional[str]:
        """多维度融合为一名发言人；当前按 venue 或 dict 的 name/置信度取最优。"""
        candidates = []
        if venue_name:
            candidates.append((venue_name, 0.8))
        if face_result and isinstance(face_result, dict):
            n = face_result.get("name") or face_result.get("formal_name")
            c = face_result.get("confidence", 0.7)
            if n:
                candidates.append((n, c))
        if voice_result and isinstance(voice_result, dict):
            n = voice_result.get("name") or voice_result.get("formal_name")
            c = voice_result.get("confidence", 0.7)
            if n:
                candidates.append((n, c))
        if not candidates:
            return None
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]
