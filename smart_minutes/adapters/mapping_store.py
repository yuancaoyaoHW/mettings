"""IMappingStore implementation (stub: in-memory or DB later)."""
from typing import List, Optional


class MappingStoreAdapter:
    """Implements IMappingStore. Can load from DB or config."""

    def __init__(self, db_uri: Optional[str] = None, initial_oral_map: Optional[dict] = None):
        self._db_uri = db_uri
        self._oral_to_formal = dict(initial_oral_map or {})
        self._meeting_terms: dict = {}

    def resolve_oral_to_formal(self, oral_name: str) -> Optional[str]:
        return self._oral_to_formal.get(oral_name.strip())

    def get_professional_terms(self, meeting_type: str, meeting_name: str) -> List[str]:
        key = (meeting_type or "", meeting_name or "")
        return list(self._meeting_terms.get(key, []))
