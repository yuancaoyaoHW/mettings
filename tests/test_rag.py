"""RAG 检索封装：按类型检索与权重透传。"""
from smart_minutes.tools import rag


class _MockRetrieval:
    def __init__(self):
        self.calls = []

    def search(self, query_text, **kwargs):
        self.calls.append({"query_text": query_text, **kwargs})
        type_filter = kwargs.get("type_filter")
        if type_filter == "todo":
            return [{"pk": 1, "score": 0.8, "page_content": "待办A", "type": "todo"}]
        if type_filter == "open_issue":
            return [{"pk": 2, "score": 0.9, "page_content": "遗留B", "type": "open_issue"}]
        if type_filter == "conclusion":
            return [{"pk": 3, "score": 0.7, "page_content": "结论C", "type": "conclusion"}]
        return []


def test_retrieve_similar_todos_with_weights():
    m = _MockRetrieval()
    out = rag.retrieve_similar_todos(
        m,
        "联调排期",
        5,
        dense_weight=0.7,
        sparse_weight=0.3,
        type_weight=1.2,
    )
    assert len(out) == 1
    assert out[0]["pk"] == 1
    call = m.calls[0]
    assert call["type_filter"] == "todo"
    assert call["dense_weight"] == 0.7
    assert call["sparse_weight"] == 0.3
    assert call["type_weight"] == 1.2


def test_retrieve_similar_todos_or_issues_merge_and_sort():
    m = _MockRetrieval()
    out = rag.retrieve_similar_todos_or_issues(
        m,
        "风险项",
        5,
        todo_weight=0.8,
        issue_weight=1.5,
    )
    assert len(out) == 2
    # issue 0.9 * 1.5 > todo 0.8 * 0.8
    assert out[0]["pk"] == 2
    assert out[1]["pk"] == 1


def test_retrieve_similar_conclusions_with_weights():
    m = _MockRetrieval()
    out = rag.retrieve_similar_conclusions(
        m,
        "方案定稿",
        3,
        dense_weight=0.6,
        sparse_weight=0.4,
        type_weight=1.3,
    )
    assert len(out) == 1
    call = m.calls[0]
    assert call["type_filter"] == "conclusion"
    assert call["dense_weight"] == 0.6
    assert call["sparse_weight"] == 0.4
    assert call["type_weight"] == 1.3


def test_retrieve_latest_minutes_by_series_with_attendee_overlap():
    class _SeriesRetrieval:
        def search(self, query_text, **kwargs):
            return [
                {
                    "pk": 101,
                    "time": "2026-02-28T10:00:00",
                    "score": 0.6,
                    "attendees": ["张三", "李四"],
                    "source": "minutes",
                },
                {
                    "pk": 102,
                    "time": "2026-02-28T10:00:00",
                    "score": 0.6,
                    "attendees": ["王五"],
                    "source": "minutes",
                },
            ]

    out = rag.retrieve_latest_minutes_by_series(
        _SeriesRetrieval(),
        meeting_type="周会",
        meeting_name="产品周会",
        top_k=2,
        attendees=["张三"],
    )
    assert len(out) == 2
    # 同时间下，优先参会人重叠更高的命中
    assert out[0]["pk"] == 101
