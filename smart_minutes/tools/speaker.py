"""Speaker fusion: delegate to ISpeakerResolver."""
from typing import Any, Optional

from smart_minutes.contracts import ISpeakerResolver


def resolve_speaker(
    speaker_resolver: ISpeakerResolver,
    face_result: Any = None,
    voice_result: Any = None,
    venue_name: Optional[str] = None,
) -> Optional[str]:
    return speaker_resolver.resolve_speaker(face_result, voice_result, venue_name)
