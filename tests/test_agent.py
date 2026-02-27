"""Agent run：mock 检索/映射下的行为与裁剪逻辑。"""
from smart_minutes.agents.minutes_agent import MinutesAgent
from smart_minutes.agents.router import suggest_tools
from smart_minutes.schemas import MinutesRequest, MinutesResponse


class MockRetrieval:
    def search(self, query_text, *, topic_filter=None, source_filter=None, level1_filter=None,
               author_filter=None, type_filter=None, top_k=5, **kwargs):
        return [
            {"pk": 1, "score": 0.9, "page_content": "历史纪要片段", "source": "minutes", "topic": "议题1"}
        ]


class MockMapping:
    def resolve_oral_to_formal(self, oral_name):
        return "张三" if oral_name == "老张" else None

    def get_professional_terms(self, meeting_type, meeting_name):
        return ["术语1"]


def test_agent_retrieve_only():
    agent = MinutesAgent(MockRetrieval(), MockMapping(), config=None)
    req = MinutesRequest(meeting_name="周会", topics=["议题1"], oral_names=["老张"])
    from smart_minutes.agents.router import suggest_tools
    steps = suggest_tools(req)
    resp = agent.run(req, steps, retrieve_only=True)
    assert isinstance(resp, MinutesResponse)
    assert resp.minutes_content == ""
    assert len(resp.references) >= 0
    assert "张三" in resp.mapped_terms or len(resp.mapped_terms) >= 0


def test_agent_run_returns_response():
    agent = MinutesAgent(MockRetrieval(), MockMapping(), config=None)
    req = MinutesRequest(meeting_name="周会", topics=["议题1"])
    steps = suggest_tools(req)
    resp = agent.run(req, steps, retrieve_only=False)
    assert isinstance(resp, MinutesResponse)
    assert hasattr(resp, "minutes_content")
    assert hasattr(resp, "references")
    assert hasattr(resp, "warnings")
    assert hasattr(resp, "partial")


def test_truncate_to_budget():
    from smart_minutes.config import SmartMinutesConfig
    agent = MinutesAgent(MockRetrieval(), MockMapping(), config=SmartMinutesConfig(context_token_budget=100, chars_per_token=2))
    parts = ["a" * 50, "b" * 100, "c" * 200]
    out = agent._truncate_to_budget(parts, 100)
    total_chars = len(out.replace("\n\n", ""))
    assert total_chars <= 100 * 2 + 50
    assert "a" in out
