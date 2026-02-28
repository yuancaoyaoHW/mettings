"""ingest 分索引规则与校验。"""
import pytest

from pipelines import ingest


@pytest.fixture(autouse=True)
def _mock_embedding(monkeypatch):
    monkeypatch.setattr(ingest, "get_embedding", lambda text: [0.1, 0.2, 0.3])


def test_ingest_structured_items_todo_success():
    rows = ingest.ingest_structured_items(
        [
            {
                "text": "完成接口联调",
                "owner": "张三",
                "deadline": "2026-03-01",
                "topic": "联调",
            }
        ],
        item_type="todo",
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "minutes"
    assert rows[0]["type"] == "todo"
    assert rows[0]["owner"] == "张三"
    assert rows[0]["vector"] == [0.1, 0.2, 0.3]


def test_ingest_minutes_chunks_normalizes_alias_type():
    rows = ingest.ingest_minutes_chunks(
        [
            {
                "source": "minutes",
                "type": "decision",
                "text": "本周冻结需求范围",
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["type"] == "conclusion"


def test_ingest_minutes_chunks_reject_invalid_todo():
    with pytest.raises(ValueError, match="todo chunk requires owner"):
        ingest.ingest_minutes_chunks(
            [
                {
                    "source": "minutes",
                    "type": "todo",
                    "text": "补充测试用例",
                }
            ]
        )


def test_ingest_draft_segments_not_blocked_by_minutes_rules():
    rows = ingest.ingest_draft_segments(
        [{"page_content": "先讨论需求，再讨论排期", "topic": "需求评审"}]
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "draft"
    assert rows[0]["type"] == "draft_segment"
