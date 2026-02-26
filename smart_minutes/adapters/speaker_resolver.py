"""ISpeakerResolver implementation: fuse face/voice/venue -> formal name."""
from typing import Any, Optional


class SpeakerResolverAdapter:
    """
    Implements ISpeakerResolver.
    Fuse face_result, voice_result, venue_name (from external APIs) -> formal name.
    Wire real face/voice/venue service URLs in api_config and call them in resolve_speaker.
    """

    def __init__(self, api_config: Optional[dict] = None):
        self._api_config = api_config or {}

    def resolve_speaker(
        self,
        face_result: Any = None,
        voice_result: Any = None,
        venue_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Fuse multi-dimensional inputs to one speaker. Stub: use venue_name or dict name fields.
        Production: call face/voice APIs, then vote or weight by confidence.
        """
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
