"""Exercise actual model-directed tool calls through the public package contract."""

import json
from copy import deepcopy

from acceptance import QUERY, require_success, save
from probe import launch, request


def run():
    definition = request("/workflow-packages/research_notes")["definition"]
    note_schema = deepcopy(definition["agents"]["write_note"]["outputSchema"])
    inputs = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "title": {"type": "string"}},
        "required": ["query", "title"],
        "unevaluatedProperties": False,
    }
    agent = {
        "name": "Actual model-directed Notes query and save",
        "inputSchema": inputs,
        "outputSchema": note_schema,
        "strategy": {
            "kind": "model",
            "modelRef": "research-model",
            "prompt": "必须先调用授权的notes/search工具，query采用输入值，"
            "limit=20，includeDerived=false。"
            "根据真实返回笔记，写一句简短中文保留10欧元与12欧元候选的矛盾及未决策事实。"
            "再调用notes/create一次，title采用输入值，sourceKind=derived，sourceNoteIds使用搜索返回的原始笔记ID。"
            "最后只返回create工具实际确认的完整JSON对象，保留其所有字段。不得模拟工具回复。",
        },
        "tools": ["example/notes/search", "example/notes/create"],
        "resources": ["notes-workspace"],
        "budget": {
            "maxModelRequests": 5,
            "maxToolCalls": 2,
            "maxTokens": 18000,
            "maxOutputTokens": 4096,
            "deadlineSeconds": 600,
            "maxParallelTools": 1,
        },
    }
    workflow = {
        "name": "Actual tool chain",
        "inputSchema": inputs,
        "outputSchema": note_schema,
        "nodes": {"act": {"uses": "worker", "inputMapping": {"ref": "workflow.input"}}},
        "outputMapping": {"ref": "nodes.act.output"},
        "maxParallelNodes": 1,
        "deadlineSeconds": 900,
        "presentation": {
            "version": "signaldeck.presentation/1",
            "title": {"kind": "input", "ref": "workflow.input.title"},
            "sections": [
                {
                    "kind": "markdown",
                    "ref": "workflow.output.text",
                    "label": "正文",
                    "required": True,
                }
            ],
        },
    }
    request(
        "/workflow-packages",
        {
            "manifestSource": json.dumps(
                {
                    "apiVersion": "signaldeck.workflowPackage/v2",
                    "metadata": {
                        "key": "verification_active_tools",
                        "name": "Actual model tool acceptance",
                    },
                    "agents": {"worker": agent},
                    "workflows": {"run": workflow},
                },
                ensure_ascii=False,
            )
        },
    )
    row = require_success(
        launch(
            "verification_active_tools",
            "run",
            {"query": QUERY, "title": "主动工具验收成品"},
            "real-model-read-write",
        )
    )
    calls = [e for e in row["evidence"] if e["kind"] == "tool"]
    assert [e["toolId"] for e in calls] == ["example/notes/search", "example/notes/create"], calls
    assert all(e["status"] == "succeeded" for e in calls)
    assert any(e.get("toolCalls") and any(e["toolCalls"]) for e in row["providerObservations"])
    stored = calls[-1]["output"]
    if "output" in stored and "id" not in stored:
        stored = stored["output"]
    assert row["output"] == stored, "Model output must retain actual confirmed tool receipt"
    save(
        "active-tools.json",
        {
            "run": row,
            "assertions": {
                "realModelRequestedTools": True,
                "searchThenCreateSucceeded": True,
                "confirmedReceiptPreserved": True,
            },
        },
    )


if __name__ == "__main__":
    run()
