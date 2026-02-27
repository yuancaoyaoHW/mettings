"""MinutesRequest / MinutesResponse 序列化与默认值。"""
import pytest
from pydantic import ValidationError

from smart_minutes.schemas import (
    ErrorItem,
    MinutesRequest,
    MinutesResponse,
    ReferenceItem,
    RealtimeSpeakerInput,
)


def test_minutes_request_defaults():
    r = MinutesRequest()
    assert r.meeting_type is None
    assert r.topics == []
    assert r.person_names == []
    assert r.options is None


def test_minutes_request_serialize_roundtrip():
    r = MinutesRequest(meeting_name="周会", topics=["进度"], oral_names=["老张"])
    d = r.model_dump()
    r2 = MinutesRequest.model_validate(d)
    assert r2.meeting_name == r.meeting_name
    assert r2.topics == r.topics
    assert r2.oral_names == r.oral_names


def test_minutes_response_defaults():
    resp = MinutesResponse()
    assert resp.minutes_content == ""
    assert resp.references == []
    assert resp.errors == []
    assert resp.partial is False


def test_reference_item():
    ref = ReferenceItem(page_content="abc", source="minutes", topic="议题1")
    assert ref.page_content == "abc"
    assert ref.source == "minutes"
    assert ref.topic == "议题1"


def test_error_item():
    e = ErrorItem(code="ERR", message="msg")
    assert e.code == "ERR"
    assert e.message == "msg"
