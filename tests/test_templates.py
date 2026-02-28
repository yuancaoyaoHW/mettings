"""会议类型模板配置：加载与路由合并策略测试。"""
import json

from smart_minutes.agents.router import suggest_tools
from smart_minutes.config_templates import load_templates_from_data, load_templates_from_file
from smart_minutes.schemas import MinutesRequest


def test_load_templates_from_json_file(tmp_path):
    data = {
        "周会": {
            "top_k": 3,
            "context_token_budget_multiplier": 0.8,
            "open_issue_weights": {"type_weight": 1.5, "dense_weight": 0.6, "sparse_weight": 0.4},
            "todo_weights": {"type_weight": 0.9},
            "conclusion_weights": {"type_weight": 1.2},
            "output_preferences": {"action_item_format": "owner+deadline"},
        }
    }
    p = tmp_path / "templates.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    templates = load_templates_from_file(str(p))
    assert "周会" in templates
    tpl = templates["周会"]
    assert tpl.top_k == 3
    assert tpl.context_token_budget_multiplier == 0.8
    assert tpl.open_issue_weights.type_weight == 1.5
    assert tpl.output_preferences["action_item_format"] == "owner+deadline"


def test_template_merge_priority_request_over_template_over_global():
    templates = load_templates_from_data(
        {
            "周会": {
                "top_k": 4,
                "open_issue_weights": {"type_weight": 1.5, "dense_weight": 0.6, "sparse_weight": 0.4},
                "todo_weights": {"type_weight": 0.9},
                "conclusion_weights": {"type_weight": 1.2, "dense_weight": 0.3, "sparse_weight": 0.2},
            }
        }
    )
    req = MinutesRequest(
        meeting_type="周会",
        open_issues=["历史遗留"],
        conclusions=["技术结论"],
        options={
            "top_k": 9,
            "dense_weight": 0.66,
            "retrieval_weights": {
                "todo": {"type_weight": 1.1},
                "open_issue": {"type_weight": 2.2, "dense_weight": 0.95},
            },
        },
    )
    steps = suggest_tools(
        req,
        templates=templates,
        default_top_k=7,
        default_dense_weight=0.5,
        default_sparse_weight=0.5,
    )

    issue_step = next(s for s in steps if s["tool"] == "retrieve_similar_todos_or_issues")
    assert issue_step["params"]["top_k"] == 9  # 请求覆盖模板/全局
    assert issue_step["params"]["todo_weight"] == 1.1  # 请求覆盖模板
    assert issue_step["params"]["issue_weight"] == 2.2  # 请求覆盖模板
    assert issue_step["params"]["dense_weight"] == 0.95  # 请求分类型覆盖请求全局/模板/全局默认
    assert issue_step["params"]["sparse_weight"] == 0.4  # 模板覆盖全局默认

    conclusion_step = next(s for s in steps if s["tool"] == "retrieve_similar_conclusions")
    assert conclusion_step["params"]["top_k"] == 9
    assert conclusion_step["params"]["type_weight"] == 1.2  # 模板覆盖全局默认
    assert conclusion_step["params"]["dense_weight"] == 0.66  # 请求全局覆盖模板
    assert conclusion_step["params"]["sparse_weight"] == 0.2  # 模板值


def test_unknown_meeting_type_fallback_global_defaults():
    req = MinutesRequest(meeting_type="不存在类型", open_issues=["风险项"])
    steps = suggest_tools(
        req,
        templates={},
        default_top_k=7,
        default_dense_weight=0.55,
        default_sparse_weight=0.45,
    )
    issue_step = next(s for s in steps if s["tool"] == "retrieve_similar_todos_or_issues")
    assert issue_step["params"]["top_k"] == 7
    assert issue_step["params"]["todo_weight"] == 1.0
    assert issue_step["params"]["issue_weight"] == 1.0
    assert issue_step["params"]["dense_weight"] == 0.55
    assert issue_step["params"]["sparse_weight"] == 0.45
