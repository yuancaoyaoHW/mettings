"""ISpeakerResolver 实现：人脸/声纹/会场 → 正式人名。"""
from typing import Any, Optional

from smart_minutes.schemas import SpeakerCandidate, SpeakerResolution


class SpeakerResolverAdapter:
    """实现 ISpeakerResolver；可配置外部人脸/声纹 API，按置信度融合。"""

    def __init__(self, api_config: Optional[dict] = None):
        self._api_config = api_config or {}

    def resolve_speaker(
        self,
        face_result: Any = None,
        voice_result: Any = None,
        venue_name: Optional[str] = None,
    ) -> Optional[SpeakerResolution]:
        """多维度融合为一名发言人；返回置信度、候选集与冲突状态。"""
        candidates = []
        if venue_name:
            candidates.append(SpeakerCandidate(name=venue_name, confidence=0.6, source="venue"))
        if face_result and isinstance(face_result, dict):
            n = face_result.get("name") or face_result.get("formal_name")
            c = face_result.get("confidence", 0.7)
            if n:
                candidates.append(SpeakerCandidate(name=n, confidence=float(c), source="face"))
        if voice_result and isinstance(voice_result, dict):
            n = voice_result.get("name") or voice_result.get("formal_name")
            c = voice_result.get("confidence", 0.7)
            if n:
                candidates.append(SpeakerCandidate(name=n, confidence=float(c), source="voice"))

        if not candidates:
            return SpeakerResolution(
                resolved_name=None,
                confidence=0.0,
                candidates=[],
                status="unknown",
                conflict_reason="no_modal_signal",
            )

        candidates.sort(key=lambda x: -x.confidence)
        top = candidates[0]
        conflict_reason = ""
        status = "resolved"
        if len(candidates) > 1 and candidates[1].name != top.name and abs(top.confidence - candidates[1].confidence) < 0.15:
            status = "conflict"
            conflict_reason = "face_voice_close_confidence"

        if top.confidence < 0.5:
            status = "unknown"
            conflict_reason = conflict_reason or "low_confidence"

        return SpeakerResolution(
            resolved_name=top.name if status != "unknown" else None,
            confidence=top.confidence,
            candidates=candidates,
            status=status,
            conflict_reason=conflict_reason,
        )
