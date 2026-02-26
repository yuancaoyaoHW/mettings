"""Smart minutes: standalone feature package. Public API only."""
from smart_minutes.api import SmartMinutesService
from smart_minutes.schemas import (
    ErrorItem,
    MinutesRequest,
    MinutesResponse,
    ReferenceItem,
    RealtimeSpeakerInput,
)

__all__ = [
    "SmartMinutesService",
    "MinutesRequest",
    "MinutesResponse",
    "ReferenceItem",
    "ErrorItem",
    "RealtimeSpeakerInput",
]
