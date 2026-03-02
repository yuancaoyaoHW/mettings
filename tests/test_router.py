"""路由：suggest_tools 返回的工具列表与参数。"""
from smart_minutes.agents.router import suggest_tools
from smart_minutes.schemas import MinutesRequest


def test_suggest_tools_empty_request():
    req = MinutesRequest()
    steps = suggest_tools(req)
    assert isinstance(steps, list)
    assert len(steps) == 0


def test_suggest_tools_with_meeting_and_topics():
    req = MinutesRequest(meeting_name="周会", topics=["议题1", "议题2"], attendees=["张三"])
    steps = suggest_tools(req)
    tool_names = [s["tool"] for s in steps]
    assert "professional_terms" in tool_names
    assert "retrieve_latest_minutes_by_series" in tool_names
    assert tool_names.count("retrieve_by_topic") == 2
    assert all("params" in s for s in steps)
    series_step = next(s for s in steps if s["tool"] == "retrieve_latest_minutes_by_series")
    assert series_step["params"]["attendees"] == ["张三"]


def test_suggest_tools_with_oral_names():
    req = MinutesRequest(oral_names=["老张"])
    steps = suggest_tools(req)
    assert any(s["tool"] == "mapping" for s in steps)
    params = next(s["params"] for s in steps if s["tool"] == "mapping")
    assert "oral_names" in params
    assert params["oral_names"] == ["老张"]


def test_suggest_tools_with_draft_and_topics():
    req = MinutesRequest(draft_text="会议内容...", topics=["A"])
    steps = suggest_tools(req)
    assert any(s["tool"] == "get_draft_segments_by_topics" for s in steps)
    assert any(s["tool"] == "retrieve_similar_topic_by_draft" for s in steps)


def test_suggest_tools_with_weighted_retrieval_params():
    req = MinutesRequest(
        open_issues=["遗留1"],
        conclusions=["结论1"],
        options={
            "top_k": 6,
            "retrieval_weights": {
                "todo": {"type_weight": 0.8},
                "open_issue": {"type_weight": 1.4, "dense_weight": 0.65, "sparse_weight": 0.35},
                "conclusion": {"type_weight": 1.3, "dense_weight": 0.7, "sparse_weight": 0.3},
            },
        },
    )
    steps = suggest_tools(req)
    issue_step = next(s for s in steps if s["tool"] == "retrieve_similar_todos_or_issues")
    assert issue_step["params"]["todo_weight"] == 0.8
    assert issue_step["params"]["issue_weight"] == 1.4
    assert issue_step["params"]["dense_weight"] == 0.65
    assert issue_step["params"]["sparse_weight"] == 0.35

    conclusion_step = next(s for s in steps if s["tool"] == "retrieve_similar_conclusions")
    assert conclusion_step["params"]["type_weight"] == 1.3
    assert conclusion_step["params"]["dense_weight"] == 0.7
    assert conclusion_step["params"]["sparse_weight"] == 0.3
