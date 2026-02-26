"""Mapping tools: delegate to IMappingStore."""
from typing import List

from smart_minutes.contracts import IMappingStore


def resolve_oral_to_formal(mapping_store: IMappingStore, oral_name: str) -> str | None:
    return mapping_store.resolve_oral_to_formal(oral_name)


def get_professional_terms(
    mapping_store: IMappingStore,
    meeting_type: str,
    meeting_name: str,
) -> List[str]:
    return mapping_store.get_professional_terms(meeting_type, meeting_name)
