"""Abstract interfaces for smart_minutes (dependency inversion)."""
from typing import Any, List, Optional, Protocol


class IRetrieval(Protocol):
    """Retrieval interface: filter/query -> list of chunks."""

    def search(
        self,
        query_text: str,
        *,
        topic_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        level1_filter: Optional[str] = None,
        author_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[dict]:
        """Hybrid/search with optional filters. Returns list of dicts with pk, score, page_content, source, level1, level2, author, time, version, topic (if needed)."""
        ...


class IMappingStore(Protocol):
    """Mapping query interface: oral -> formal name, meeting_type -> professional terms."""

    def resolve_oral_to_formal(self, oral_name: str) -> Optional[str]:
        """Resolve oral/nickname to formal person name. Returns None if not found."""
        ...

    def get_professional_terms(self, meeting_type: str, meeting_name: str) -> List[str]:
        """Get professional terms for meeting type/name. Returns empty list if none."""
        ...


class ISpeakerResolver(Protocol):
    """Speaker fusion: face/voice/venue results -> formal name."""

    def resolve_speaker(
        self,
        face_result: Any = None,
        voice_result: Any = None,
        venue_name: Optional[str] = None,
    ) -> Optional[str]:
        """Fuse face/voice/venue to one formal speaker name. Returns None if cannot determine."""
        ...
