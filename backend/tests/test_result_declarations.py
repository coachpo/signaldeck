"""Result presentation is a frozen public contract, independent of business field names."""

import json
from datetime import UTC, datetime

import pytest

from app.application.result_projection import project_result
from app.domain.execution import ExecutionEvidence, ResolvedRunSpec, RunDetail
from app.domain.tool_contracts import (
    PluginRelease,
    ToolDefinition,
    canonical_digest,
    tool_contract_digest,
)
from tests.test_platform_api import source


def run_fixture(*, declared=True):
    definition = json.loads(source())
    workflow = definition["workflows"]["main"]
    if declared:
        workflow["presentation"] = {
            "version": "signaldeck.presentation/1",
            "sections": [
                {"kind": "markdown", "label": "Unrelated wording", "ref": "nodes.echo.output.text"},
                {
                    "kind": "link",
                    "label": "Open item",
                    "ref": "nodes.echo.output",
                    "toolId": "example/echo/copy",
                    "linkKey": "item",
                },
            ],
        }
    now = datetime.now(UTC)
    return RunDetail(
        id="run",
        package_key="api-package",
        workflow_key="main",
        package_hash="hash",
        status="succeeded",
        created_at=now,
        origin={"kind": "manual"},
        spec=ResolvedRunSpec(
            run_id="run",
            package_key="api-package",
            workflow_key="main",
            package_hash="hash",
            definition=definition,
            plan={},
            parameters={},
            core_artifact="core",
            deadline=now,
        ),
    )


def evidence(kind, output, **kwargs):
    return ExecutionEvidence(
        id=kind,
        run_id="run",
        node_id="echo",
        kind=kind,
        status="succeeded",
        output=output,
        **kwargs,
    )


@pytest.mark.parametrize("effect", ["read", "write"])
def test_declared_link_uses_confirmed_frozen_tool_output_offline_and_preserves_ownership(effect):
    run = run_fixture()
    schema = {"type": "object", "properties": {"externalKey": {"type": "string"}}}
    tool = ToolDefinition(
        tool_id="example/echo/copy",
        owner_plugin_id="example/echo",
        effect=effect,
        input_schema=schema,
        output_schema=schema,
        result_links=[
            {
                "version": "signaldeck.resultLink/1",
                "key": "item",
                "label": "Open",
                "path": "items",
                "query": {"selected": "tool.output.externalKey"},
            }
        ],
    )
    release = PluginRelease(
        plugin_id="example/echo",
        release_id="2",
        artifact_digest="sha256:" + "a" * 64,
        endpoint="http://127.0.0.1:1/mcp",
        page_url="https://offline.invalid/app",
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    )
    run.spec.plugin_releases = [release.model_dump(mode="json", by_alias=True)]
    run.evidence = [
        evidence("node", {"text": "Renamed mapped value"}),
        evidence(
            "tool",
            {"externalKey": "a &/=b"},
            tool_id=tool.tool_id,
            operation_id="confirmed-operation",
        ),
    ]
    projected = project_result(run)
    assert projected.sections[0].value == "Renamed mapped value"
    link = projected.sections[1]
    assert link.href == "https://offline.invalid/app/items?selected=a+%26%2F%3Db"
    assert (
        link.evidence_id == "node"
        and link.operation_id == "confirmed-operation"
        and link.plugin_id == "example/echo"
    )
    run.evidence[1].status = "unknown"
    assert all(s.kind != "link" for s in project_result(run).sections)
    uncertain = project_result(run)
    assert uncertain.content_status == ("unknown" if effect == "write" else "partial")
    assert uncertain.unknown_evidence_ids == (["tool"] if effect == "write" else [])
    assert uncertain.read_unknown_evidence_ids == (["tool"] if effect == "read" else [])


def test_historical_business_looking_keys_are_plain_values_and_optional_skip_is_not_missing():
    run = run_fixture(declared=False)
    run.spec.parameters = {"includeRisk": False}
    run.output = {
        "reportId": 7,
        "collection": "ordinary",
        "id": "x",
        "text": "plain",
        "warnings": ["ordinary"],
    }
    run.evidence = [
        ExecutionEvidence(id="skip", run_id="run", node_id="echo", kind="node", status="skipped")
    ]
    projected = project_result(run)
    assert projected.sections[0].value == run.output
    assert projected.attachments == [] and projected.missing == [] and projected.body is None
    assert projected.skipped == ["echo"] and projected.content_status == "available"


def test_old_tool_digest_omits_new_field_and_new_contract_changes_digest():
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    tool = ToolDefinition(
        tool_id="example/echo/copy",
        owner_plugin_id="example/echo",
        input_schema=schema,
        output_schema=schema,
    )
    old = tool.model_dump(mode="json", by_alias=True)
    assert "resultLinks" not in old
    assert tool_contract_digest((tool,)) == canonical_digest([old])
    updated = ToolDefinition.model_validate(
        {
            **old,
            "resultLinks": [
                {
                    "version": "signaldeck.resultLink/1",
                    "key": "item",
                    "label": "Item",
                    "path": "",
                    "query": {"id": "tool.output.text"},
                }
            ],
        }
    )
    assert tool_contract_digest((updated,)) != tool_contract_digest((tool,))


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.invalid",
        "//evil.invalid",
        "../escape",
        "%2e%2e/escape",
        "?x",
        "#x",
        "\\\\evil.invalid",
    ],
)
def test_result_link_rejects_unsafe_paths(path):
    from app.domain.tool_contracts import ResultLink

    with pytest.raises(ValueError):
        ResultLink(version="signaldeck.resultLink/1", key="x", label="x", path=path, query={})


def test_numeric_array_selectors_and_null_final_values_are_preserved():
    run = run_fixture()
    workflow = run.spec.definition["workflows"]["main"]
    workflow["outputSchema"] = {"type": "array", "items": {"type": "string"}}
    workflow["presentation"]["sections"] = [
        {"kind": "markdown", "label": "First", "ref": "workflow.output.0"}
    ]
    run.output = ["Array content"]
    assert project_result(run).sections[0].value == "Array content"
    workflow["outputSchema"] = {"type": "null"}
    workflow["presentation"]["sections"] = [
        {"kind": "value", "label": "Null", "ref": "workflow.output", "required": True}
    ]
    run.output = None
    result = project_result(run)
    assert result.sections[0].value is None and result.missing == []


def test_required_artifact_backed_section_is_deferred_not_missing():
    run = run_fixture()
    run.spec.definition["workflows"]["main"]["presentation"]["sections"] = [
        {
            "kind": "markdown",
            "label": "Full content",
            "ref": "nodes.echo.output.text",
            "required": True,
        }
    ]
    artifact = {
        "$artifact": {
            "digest": "sha256:" + "a" * 64,
            "sizeBytes": 100000,
            "mediaType": "application/json",
        }
    }
    run.evidence = [evidence("node", artifact)]
    result = project_result(run)
    assert result.missing == [] and result.deferred_sections == ["Full content"]
    assert result.attachments[0].reference == artifact and result.content_status == "available"


def test_model_node_link_ownership_is_matching_tool_not_node_strategy():
    run = run_fixture()
    run.spec.definition["agents"]["echo"]["strategy"] = {
        "kind": "model",
        "modelRef": "llm",
        "prompt": "Return JSON",
    }
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    tool = ToolDefinition(
        tool_id="example/echo/copy",
        owner_plugin_id="example/echo",
        input_schema=schema,
        output_schema=schema,
        result_links=[
            {
                "version": "signaldeck.resultLink/1",
                "key": "item",
                "label": "Open",
                "path": "",
                "query": {"key": "tool.output.text"},
            }
        ],
    )
    release = PluginRelease(
        plugin_id="example/echo",
        release_id="2",
        artifact_digest="sha256:" + "a" * 64,
        endpoint="http://127.0.0.1:1/mcp",
        page_url="https://offline.invalid",
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    )
    run.spec.plugin_releases = [release.model_dump(mode="json", by_alias=True)]
    run.evidence = [
        evidence("node", {"text": "Model"}),
        evidence("tool", {"text": "Saved"}, tool_id=tool.tool_id, operation_id="write"),
    ]
    result = project_result(run)
    assert result.sections[1].operation_id == "write"
    assert result.sections[1].plugin_id == "example/echo"
    assert result.sections[1].tool_evidence_id == "tool"


def test_required_missing_evaluates_only_terminal_and_skips_remain_separate():
    run = run_fixture()
    run.spec.definition["workflows"]["main"]["presentation"]["sections"] = [
        {"kind": "markdown", "label": "Required", "ref": "nodes.echo.output.text", "required": True}
    ]
    run.status = "running"
    assert project_result(run).missing == []
    run.status = "failed"
    assert project_result(run).missing == ["Required"]


@pytest.mark.parametrize(
    "severity,expected", [("info", "available"), ("warning", "available"), ("missing", "partial")]
)
def test_notice_declared_severity_controls_business_missing_only(severity, expected):
    run = run_fixture()
    run.spec.definition["workflows"]["main"]["presentation"]["sections"] = [
        {
            "kind": "notice",
            "label": "Message",
            "severity": severity,
            "ref": "nodes.echo.output.text",
        }
    ]
    run.evidence = [evidence("node", {"text": "Provider statement"})]
    result = project_result(run)
    assert result.sections[0].severity == severity
    assert result.content_status == expected
    assert result.missing == (["Provider statement"] if severity == "missing" else [])
    assert result.execution_issues == []


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_terminal_execution_failure_retains_confirmed_declared_content(status):
    run = run_fixture()
    run.status = status
    run.evidence = [
        evidence("node", {"text": "Confirmed before terminal"}),
        ExecutionEvidence(id="end", run_id="run", node_id="other", kind="node", status=status),
    ]
    result = project_result(run)
    assert result.sections[0].value == "Confirmed before terminal"
    assert result.missing == [] and result.content_status == "partial"
    assert result.execution_issues == [f"other: {status}"]


def test_link_query_array_selector_and_explicit_null_rejection():
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    }
    payload = {
        "toolId": "example/echo/copy",
        "ownerPluginId": "example/echo",
        "inputSchema": schema,
        "outputSchema": schema,
    }
    with pytest.raises(ValueError, match="not null"):
        ToolDefinition.model_validate({**payload, "resultLinks": None})
    tool = ToolDefinition.model_validate(
        {
            **payload,
            "resultLinks": [
                {
                    "version": "signaldeck.resultLink/1",
                    "key": "item",
                    "label": "First",
                    "path": "",
                    "query": {"selected": "tool.output.items.0"},
                }
            ],
        }
    )
    assert tool.result_links[0].query == {"selected": "tool.output.items.0"}


def test_repeated_artifact_keeps_each_confirmed_origin_and_packed_link_is_deferred():
    run = run_fixture()
    declaration = run.spec.definition["workflows"]["main"]["presentation"]["sections"][1]
    declaration["required"] = True
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    tool = ToolDefinition(
        tool_id="example/echo/copy",
        owner_plugin_id="example/echo",
        input_schema=schema,
        output_schema=schema,
        result_links=[
            {
                "version": "signaldeck.resultLink/1",
                "key": "item",
                "label": "Open",
                "path": "",
                "query": {"key": "tool.output.text"},
            }
        ],
    )
    release = PluginRelease(
        plugin_id="example/echo",
        release_id="2",
        artifact_digest="sha256:" + "a" * 64,
        endpoint="http://127.0.0.1:1/mcp",
        page_url="https://offline.invalid",
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    )
    run.spec.plugin_releases = [release.model_dump(mode="json", by_alias=True)]
    artifact = {
        "$artifact": {
            "digest": "sha256:" + "a" * 64,
            "sizeBytes": 100000,
            "mediaType": "application/json",
        }
    }
    run.output = artifact
    run.evidence = [
        evidence("node", artifact),
        evidence("tool", artifact, tool_id=tool.tool_id, operation_id="saved"),
    ]
    result = project_result(run)
    assert len(result.attachments) == 3
    assert result.attachments[0].evidence_id is None
    confirmed = [a for a in result.attachments if a.evidence_id]
    assert all(
        a.node_id == "echo"
        and a.operation_id == "saved"
        and a.tool_evidence_id == "tool"
        and a.plugin_id == "example/echo"
        for a in confirmed
    )
    assert result.missing == [] and "Open item" in result.deferred_sections
    assert result.content_status == "available"


@pytest.mark.parametrize("model_agent", [False, True])
@pytest.mark.parametrize("reverse_input", [False, True])
def test_multiple_confirmed_tool_calls_choose_latest_time_then_id_with_matching_operation(
    model_agent, reverse_input
):
    from datetime import timedelta

    run = run_fixture()
    if model_agent:
        run.spec.definition["agents"]["echo"]["strategy"] = {
            "kind": "model",
            "modelRef": "llm",
            "prompt": "Return JSON",
        }
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    tool = ToolDefinition(
        tool_id="example/echo/copy",
        owner_plugin_id="example/echo",
        input_schema=schema,
        output_schema=schema,
        result_links=[
            {
                "version": "signaldeck.resultLink/1",
                "key": "item",
                "label": "Open",
                "path": "",
                "query": {"key": "tool.output.text"},
            }
        ],
    )
    release = PluginRelease(
        plugin_id="example/echo",
        release_id="2",
        artifact_digest="sha256:" + "a" * 64,
        endpoint="http://127.0.0.1:1/mcp",
        page_url="https://offline.invalid",
        tools=(tool,),
        contract_digest=tool_contract_digest((tool,)),
    )
    run.spec.plugin_releases = [release.model_dump(mode="json", by_alias=True)]
    finished = run.created_at + timedelta(seconds=1)
    calls = [
        evidence("tool", {"text": "earlier"}, tool_id=tool.tool_id, operation_id="old").model_copy(
            update={"id": "tool-z", "finished_at": run.created_at}
        ),
        evidence(
            "tool", {"text": "same-time-lower-id"}, tool_id=tool.tool_id, operation_id="tie-lower"
        ).model_copy(update={"id": "tool-a", "finished_at": finished}),
        evidence(
            "tool", {"text": "selected"}, tool_id=tool.tool_id, operation_id="selected-op"
        ).model_copy(update={"id": "tool-b", "finished_at": finished}),
        evidence(
            "tool", {"text": "unconfirmed"}, tool_id=tool.tool_id, operation_id="unfinished"
        ).model_copy(
            update={
                "id": "tool-c",
                "finished_at": finished + timedelta(seconds=1),
                "status": "failed",
            }
        ),
    ]
    run.evidence = [evidence("node", {"text": "public-node-value"}), *calls]
    if reverse_input:
        run.evidence.reverse()
    before = run.model_dump(mode="json", by_alias=True)
    result = project_result(run)
    link = result.sections[1]
    assert link.href == "https://offline.invalid/?key=selected"
    assert link.value == {"text": "public-node-value"}
    assert link.label == "Open item"
    assert link.evidence_id == "node" and link.tool_evidence_id == "tool-b"
    assert link.operation_id == "selected-op" and link.plugin_id == "example/echo"
    assert run.model_dump(mode="json", by_alias=True) == before
    if not model_agent:
        assert result.sections[0].tool_evidence_id == "tool-b"
        assert result.sections[0].operation_id == "selected-op"


def test_confirmed_null_node_remains_readable_when_another_branch_fails():
    run = run_fixture(declared=False)
    run.status = "failed"
    run.output = None
    run.spec.definition["agents"]["echo"]["outputSchema"] = {"type": "null"}
    workflow = run.spec.definition["workflows"]["main"]
    workflow["outputSchema"] = {"type": "null"}
    workflow["nodes"]["other"] = {"uses": "echo", "inputMapping": {"ref": "workflow.input"}}
    workflow["outputMapping"] = {"ref": "nodes.other.output"}
    run.evidence = [
        evidence("node", None),
        ExecutionEvidence(
            id="failed-node", run_id="run", node_id="other", kind="node", status="failed"
        ),
    ]
    result = project_result(run)
    assert result.content_status == "partial"
    assert len(result.sections) == 1
    assert result.sections[0].value is None
    assert result.sections[0].evidence_id == "node"
    assert result.execution_issues == ["other: failed"]
