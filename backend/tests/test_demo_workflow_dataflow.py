"""Exercise the preset data paths without substituting model quality for validation."""

from copy import deepcopy
from pathlib import Path

import pytest

from app.domain.definition_parser import parse_package_source
from app.domain.mappings import evaluate_condition, resolve_mapping
from app.domain.schema_contract import validate_value

DEMO = Path(__file__).resolve().parents[2] / "demo"


def package(key):
    return parse_package_source((DEMO / f"{key}.yaml").read_text()).package


@pytest.mark.parametrize("key", ["tradingagents_advisory_research", "digital_oracle_researcher"])
@pytest.mark.parametrize("previous", [None, "先前判断：缺乏证据。日期与范围待核实。"])
def test_research_presets_accept_minimal_inputs_and_compare_only_after_independent_analysis(
    key, previous
):
    definition = package(key)
    workflow = definition.workflows["research"]
    parameters = {"question": "哪些证据支持或推翻近期的变化？"}
    if previous is not None:
        parameters["previousReport"] = previous
    is_market = key == "tradingagents_advisory_research"
    if is_market:
        parameters.update({"symbols": ["MSFT", "AAPL"], "includeRisk": False})
        namespace = {
            "workflow": {"input": parameters},
            "nodes": {
                "collect": {"output": {"quotes": []}},
                "evidence": {"output": {"text": "行情与新闻尚未取得，不能判断方向。"}},
                "opportunity": {"output": {"text": "证据不足。"}},
            },
        }
        independent = ("evidence", "opportunity", "risk")
        final = "summary"
    else:
        namespace = {
            "workflow": {"input": parameters},
            "nodes": {
                "macro": {"output": {"text": "未取得有效宏观证据。"}},
                "company": {"output": {"text": "仅取得申报索引。"}},
            },
        }
        independent = ("macro", "company")
        final = "editor"
    validate_value(workflow.input_schema, parameters)
    for node_id in (*independent, final):
        node = workflow.nodes[node_id]
        agent_input = resolve_mapping(node.input_mapping, namespace)
        validate_value(definition.agents[node.uses].input_schema, agent_input)
        if node_id == final:
            assert agent_input["previousReport"] == (previous or "")
        else:
            assert "previousReport" not in agent_input
        if not is_market:
            assert agent_input["asOfDate"] == agent_input["supportingMaterials"] == ""
    if is_market:
        assert not evaluate_condition(workflow.nodes["risk"].condition, namespace)
        assert agent_input["riskReviewRequested"] is False
        assert "未请求与已请求但未完成" in agent_input["risk"]["text"]
        assert "risk" not in namespace["nodes"]


@pytest.mark.parametrize("previous", [None, "NVDA，2026-08-15，未来3个月：偏多。依据待核实。"])
@pytest.mark.parametrize("unavailable", [(), ("company",), ("market", "company", "macro", "news")])
def test_equity_research_keeps_prior_judgment_out_of_new_evidence(previous, unavailable):
    definition = package("us_equity_research")
    workflow = definition.workflows["research"]
    parameters = {
        "symbol": "NVDA",
        "asOfDate": "2026-09-15",
        "horizonMonths": 3,
        "question": "哪些事实支持或推翻未来三个月的判断？",
    }
    if previous is not None:
        parameters["previousReport"] = previous
    validate_value(workflow.input_schema, parameters)
    namespace = {"workflow": {"input": parameters}, "nodes": {}}
    for node_id in ("market", "company", "macro", "news"):
        node = workflow.nodes[node_id]
        agent_input = resolve_mapping(node.input_mapping, namespace)
        validate_value(definition.agents[node.uses].input_schema, agent_input)
        assert "previousReport" not in agent_input
        assert "supportingMaterials" not in agent_input
        assert agent_input["evidence"] == []
        if node_id not in unavailable:
            namespace["nodes"][node_id] = {"output": {"content": f"{node_id}：已取得有限资料。"}}

    for node_id in ("bull", "bear", "bull_reply", "bear_reply", "risk", "decision"):
        node = workflow.nodes[node_id]
        agent_input = resolve_mapping(node.input_mapping, namespace)
        validate_value(definition.agents[node.uses].input_schema, agent_input)
        for missing in unavailable:
            assert "未取得确认结果" in agent_input[missing]
        assert "supportingMaterials" not in agent_input
        assert agent_input["evidence"] == []
        if node_id == "decision":
            assert agent_input["previousReport"] == (previous or "")
        else:
            assert "previousReport" not in agent_input
            namespace["nodes"][node_id] = {"output": {"content": "依据有限，保留数据缺口。"}}
    assert set(namespace["nodes"]).isdisjoint(unavailable)


def test_equity_review_preserves_original_materials_beside_incorrect_analysis(monkeypatch):
    from datetime import UTC, datetime

    for directory in ("runtime", "finance"):
        monkeypatch.syspath_prepend(str(DEMO.parent / "plugins" / directory))
    from finance_plugin.research_collection import ResearchMergeInput, merge_evidence
    from finance_plugin.research_report import compile_research_report

    definition = package("us_equity_research")
    workflow = definition.workflows["research"]
    materials = [
        {
            "category": "公司财报",
            "title": "季度财报摘录",
            "publishedDate": "2026-08-26",
            "source": "公司季度财报，第12页",
            "content": "  费用为USD2.7十亿。\n本季毛利率62%，下季指引60%。\n",
        },
        {
            "category": "美国政策",
            "title": "出口规定摘录",
            "publishedDate": "2026-07-01",
            "source": "主管部门公告，第三段",
            "content": "许可逐案审查；不等于已实现销售。\n本期收入指引未计入相关市场。",
        },
    ]
    materials.append(
        {
            "category": "其他",
            "title": "长原文",
            "publishedDate": "2026-07-01",
            "source": "完整公开原文，附录",
            "content": "需要保留的原始说明。" * 200 + "正文末尾的完整性凭据。",
        }
    )
    previous = "上一次报告：证据不完整，等待公司披露。"
    parameters = {
        "symbol": "ACME",
        "asOfDate": "2026-09-15",
        "horizonMonths": 3,
        "question": "核对原始资料与各阶段分析。",
        "supportingMaterials": deepcopy(materials),
        "previousReport": previous,
    }
    unchanged = deepcopy(parameters)
    incorrect_company = "U1显示费用2.7亿美元，毛利率指引由62%上升至60%。"
    incorrect_news = "U1为出口公告；许可收紧必然减少已经计入指引的收入。"
    namespace = {
        "workflow": {"input": parameters},
        "nodes": {
            node_id: {"output": {"content": "沿用分析稿中的数字与编号。"}}
            for node_id in ("market", "macro", "bull", "bear", "bull_reply", "bear_reply")
        },
    }
    namespace["nodes"]["company"] = {"output": {"content": incorrect_company}}
    namespace["nodes"]["news"] = {"output": {"content": incorrect_news}}
    validate_value(workflow.input_schema, parameters)
    namespace["nodes"]["scope"] = {"output": {"cutoffAt": "2026-09-16T04:00:00Z"}}
    collection_input = resolve_mapping(workflow.nodes["collection"].input_mapping, namespace)
    collection = merge_evidence(
        ResearchMergeInput.model_validate(collection_input),
        now=datetime(2026, 9, 16, 20, tzinfo=UTC),
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    namespace["nodes"]["collection"] = {"output": collection}
    originals = {item["title"]: item for item in collection["evidence"]}
    assert {title: item["text"] for title, item in originals.items()} == {
        item["title"]: item["content"] for item in materials
    }

    for node_id in ("risk", "decision"):
        node = workflow.nodes[node_id]
        agent_input = resolve_mapping(node.input_mapping, namespace)
        validate_value(definition.agents[node.uses].input_schema, agent_input)
        assert "supportingMaterials" not in agent_input
        projected = {item["title"]: item for item in agent_input["evidence"]}
        for material in materials[:2]:
            item = projected[material["title"]]
            assert item["text"] == material["content"]
            assert item["locator"] == material["source"]
            assert item["evidenceId"] == originals[material["title"]]["evidenceId"]
            assert item["verified"] is False
        assert agent_input["analysisContextTruncated"] is True
        assert projected["长原文"]["excerptTruncated"] is True
        assert projected["长原文"]["text"] == materials[2]["content"][:800]
        assert agent_input["company"] == incorrect_company
        assert agent_input["news"] == incorrect_news
        if node_id == "risk":
            assert "previousReport" not in agent_input
            namespace["nodes"]["risk"] = {"output": {"content": "分析稿一致，无须更正。"}}
        else:
            assert agent_input["previousReport"] == previous
            assert agent_input["riskReview"] == "分析稿一致，无须更正。"
    compile_input = resolve_mapping(workflow.nodes["compile"].input_mapping, namespace)
    assert compile_input["evidence"] == collection["evidence"]
    canonical = compile_research_report(compile_input, now=datetime(2026, 9, 16, 20, tzinfo=UTC))
    assert "正文末尾的完整性凭据。" in canonical["content"]
    assert "费用为USD2.7十亿" in canonical["content"]
    assert parameters == unchanged


def test_equity_report_keeps_comparison_in_saved_content_and_public_output(monkeypatch):
    from datetime import UTC, datetime

    plugins = DEMO.parent / "plugins"
    for directory in ("runtime", "finance"):
        monkeypatch.syspath_prepend(str(plugins / directory))
    from finance_plugin.research_report import compile_research_report

    definition = package("us_equity_research")
    workflow = definition.workflows["research"]
    changes = "未提供上一份报告，本次只形成定性研究，尚无可核实的历史比较。"
    decision = {
        "name": "NVDA 三个月研究",
        "symbol": "NVDA",
        "asOfDate": "2026-09-15",
        "horizonMonths": 3,
        "stance": "insufficient_evidence",
        "reasons": ["未取得财务事实，不能支持方向判断。"],
        "counterevidence": [],
        "invalidation": ["取得同期财报后重新评估。"],
        "dataGaps": ["公司财务事实缺失。"],
        "evidenceConfidence": "low",
        "sources": [],
        "changes": changes,
        "content": "证据不足，暂不能判断方向。",
        "claims": [],
        "thresholds": [],
    }
    validate_value(definition.agents["adjudicate"].output_schema, decision)
    parameters = {"symbol": "NVDA", "asOfDate": "2026-09-15", "horizonMonths": 3}
    decision.update(symbol="MSFT", asOfDate="2026-08-01", horizonMonths=6)
    namespace = {
        "workflow": {"input": parameters},
        "nodes": {
            "scope": {"output": {"cutoffAt": "2026-09-16T04:00:00Z"}},
            "collection": {"output": {"evidence": [], "gaps": ["公司财务事实缺失。"]}},
            "decision": {"output": decision},
        },
    }
    compile_input = resolve_mapping(workflow.nodes["compile"].input_mapping, namespace)
    assert compile_input["comparison"] == changes
    canonical = compile_research_report(compile_input, now=datetime(2026, 9, 16, 20, tzinfo=UTC))
    namespace["nodes"]["compile"] = {"output": canonical}
    save = workflow.nodes["save"]
    save_agent = definition.agents[save.uses]
    save_input = resolve_mapping(save.input_mapping, namespace)
    validate_value(save_agent.input_schema, save_input)
    tool_input = resolve_mapping(
        save_agent.strategy.input_mapping, {"agent": {"input": save_input}}
    )
    assert tool_input == {"name": canonical["name"], "content": canonical["content"]}
    assert changes in tool_input["content"]
    assert tool_input["content"] != decision["content"]
    saved = resolve_mapping(
        save_agent.strategy.output_mapping,
        {"tool": {"output": {"id": 7, "name": canonical["name"]}}},
    )
    namespace["nodes"]["save"] = {"output": saved}
    output = resolve_mapping(workflow.output_mapping, namespace)
    validate_value(workflow.output_schema, output)
    assert output["content"] == tool_input["content"]
    assert output["changes"] == changes
    assert output["reportId"] == 7
    assert output["modelAssessmentStatus"] == "unverified"
    assert {key: output[key] for key in parameters} == parameters
    for field in (
        "stance",
        "reasons",
        "counterevidence",
        "invalidation",
        "evidenceConfidence",
        "sources",
    ):
        assert output[field] == decision[field]
    assert "未核实" in workflow.output_schema["properties"]["changes"]["title"]
    section = next(item for item in workflow.presentation.sections if "较上次的变化" in item.label)
    assert section.ref == "nodes.decision.output.changes"


def test_notes_capture_and_skipped_edit_preserve_verbatim_text_and_source_ownership():
    definition = package("research_notes")
    original = "  初始估计：节省30分钟。\n实测更正：只节省5分钟。\n\n"
    for workflow_key in ("capture", "research"):
        workflow = definition.workflows[workflow_key]
        parameters = {"title": "试用记录", "text": original}
        namespace = {"workflow": {"input": parameters}, "nodes": {}}
        if workflow_key == "research":
            parameters.update({"query": "试用", "summarize": False})
            prior = resolve_mapping(workflow.nodes["prior"].input_mapping, namespace)
            assert prior == {"query": "试用", "limit": 20, "includeDerived": False}
            namespace["nodes"]["prior"] = {
                "output": {
                    "notes": [
                        {
                            "id": "source-1",
                            "collection": "research",
                            "title": "最初估计",
                            "text": "尚未试用，估计节省30分钟。",
                            "sourceKind": "original",
                            "sourceNoteIds": [],
                        }
                    ],
                    "sourceNoteIds": ["source-1"],
                }
            }
            assert not evaluate_condition(workflow.nodes["edit"].condition, namespace)
        validate_value(workflow.input_schema, parameters)
        save = workflow.nodes["save"]
        agent = definition.agents[save.uses]
        save_input = resolve_mapping(save.input_mapping, namespace)
        validate_value(agent.input_schema, save_input)
        tool_input = resolve_mapping(agent.strategy.input_mapping, {"agent": {"input": save_input}})
        assert tool_input["title"] == parameters["title"]
        assert tool_input["text"] == original
        assert tool_input["sourceKind"] == ("original" if workflow_key == "capture" else "derived")
        assert tool_input["sourceNoteIds"] == ([] if workflow_key == "capture" else ["source-1"])
