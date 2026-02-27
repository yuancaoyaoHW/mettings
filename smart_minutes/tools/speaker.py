"""发言人融合：委托 ISpeakerResolver。"""
from typing import Any, Optional

from smart_minutes.contracts import ISpeakerResolver
from smart_minutes.schemas import SpeakerResolution


def resolve_speaker(
    speaker_resolver: ISpeakerResolver,
    face_result: Any = None,
    voice_result: Any = None,
    venue_name: Optional[str] = None,
) -> Optional[SpeakerResolution]:
    """人脸/声纹/会场 → 正式发言人名。"""
    return speaker_resolver.resolve_speaker(face_result, voice_result, venue_name)
