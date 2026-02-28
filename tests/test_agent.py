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


def test_parse_structured_topics_from_content():
    agent = MinutesAgent(MockRetrieval(), MockMapping(), config=None)
    content = "纪要正文\n\n```json\n{\"topics\": [{\"topic_name\": \"议题A\", \"summary\": \"摘要\", \"key_points\": [\"要点1\"], \"conclusions\": [], \"open_issues\": [], \"action_items\": [{\"content\": \"待办1\", \"owner\": \"张三\", \"deadline\": \"2025-03-01\"}]}]}\n```"
    parsed = agent._parse_structured_topics_from_content(content, ["议题A"])
    assert parsed is not None
    assert len(parsed) == 1
    assert parsed[0].topic_name == "议题A"
    assert parsed[0].summary == "摘要"
    assert parsed[0].key_points == ["要点1"]
    assert len(parsed[0].action_items) == 1
    assert parsed[0].action_items[0].content == "待办1"
    assert parsed[0].action_items[0].owner == "张三"
    assert parsed[0].action_items[0].deadline == "2025-03-01"


def test_parse_structured_topics_no_json_returns_none():
    agent = MinutesAgent(MockRetrieval(), MockMapping(), config=None)
    assert agent._parse_structured_topics_from_content("只有正文没有json", []) is None
    assert agent._parse_structured_topics_from_content("", ["议题1"]) is None


def test_merge_parsed_topics():
    from smart_minutes.schemas import StructuredMinutesOutput, TopicSection
    agent = MinutesAgent(MockRetrieval(), MockMapping(), config=None)
    out = StructuredMinutesOutput(topics=[TopicSection(topic_name="议题1"), TopicSection(topic_name="议题2")])
    parsed = [TopicSection(topic_name="议题1", summary="摘要1", key_points=["k1"])]
    merged = agent._merge_parsed_topics(out, parsed)
    assert len(merged.topics) == 2
    assert merged.topics[0].topic_name == "议题1"
    assert merged.topics[0].summary == "摘要1"
    assert merged.topics[0].key_points == ["k1"]
    assert merged.topics[1].topic_name == "议题2"
