"""Owned acceptance workflows using the Notes plugin's public release contract."""

from copy import deepcopy

PACKAGE_KEY = "verification_notes"


def _object(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "unevaluatedProperties": False,
    }


def notes_package(release):
    tools = {tool["toolId"]: tool for tool in release["tools"]}
    search = tools["example/notes/search"]
    create = tools["example/notes/create"]
    content = {
        name: deepcopy(create["inputSchema"]["properties"][name]) for name in ("title", "text")
    }
    summary_schema = _object({"text": content["text"]})
    inputs = _object(
        {
            **content,
            "query": deepcopy(search["inputSchema"]["properties"]["query"]),
            "summarize": {"type": "boolean"},
            "includeDerived": {"type": "boolean"},
        }
    )
    budget = {
        "maxModelRequests": 6,
        "maxToolCalls": 8,
        "maxTokens": 18000,
        "deadlineSeconds": 180,
        "maxParallelTools": 3,
    }

    def tool_agent(tool):
        return {
            "name": tool["toolId"],
            "inputSchema": deepcopy(tool["inputSchema"]),
            "outputSchema": deepcopy(tool["outputSchema"]),
            "strategy": {
                "kind": "deterministic",
                "toolId": tool["toolId"],
                "inputMapping": {"ref": "agent.input"},
                "outputMapping": {"ref": "tool.output"},
            },
            "tools": [tool["toolId"]],
            "resources": deepcopy(tool["resourceRequirements"]),
            "budget": deepcopy(budget),
        }

    def workflow(name, input_schema, nodes):
        return {
            "name": name,
            "inputSchema": input_schema,
            "outputSchema": deepcopy(create["outputSchema"]),
            "nodes": nodes,
            "outputMapping": {"ref": "nodes.persist.output"},
            "maxParallelNodes": 1,
            "deadlineSeconds": 900,
            "failurePolicy": "continue_independent",
            "presentation": {
                "version": "signaldeck.presentation/1",
                "title": {"kind": "input", "ref": "workflow.input.title"},
                "sections": [
                    {
                        "kind": "markdown",
                        "ref": "nodes.persist.output.text",
                        "label": "验收正文",
                        "required": True,
                    },
                    {
                        "kind": "receipt",
                        "ref": "nodes.persist.output",
                        "label": "验收写入回执",
                        "required": True,
                    },
                    {
                        "kind": "link",
                        "ref": "nodes.persist.output",
                        "label": "打开笔记",
                        "toolId": create["toolId"],
                        "linkKey": "note",
                        "required": True,
                    },
                ],
            },
        }

    return {
        "apiVersion": "signaldeck.workflowPackage/v2",
        "metadata": {"key": PACKAGE_KEY, "name": "Notes execution acceptance"},
        "agents": {
            "lookup": tool_agent(search),
            "persist": tool_agent(create),
            "compose": {
                "name": "Acceptance summary",
                "inputSchema": _object(
                    {"text": content["text"], "sources": deepcopy(search["outputSchema"])}
                ),
                "outputSchema": summary_schema,
                "strategy": {
                    "kind": "model",
                    "modelRef": "research-model",
                    "prompt": (
                        "按 text 中的要求整理 sources 内的实际笔记，输出中文 Markdown。"
                        "保留各项预算候选、来源、矛盾及未决策状态，不虚构结论。"
                        "正文包含编号列表和无序列表。只返回包含 text 字段的 JSON。"
                    ),
                },
                "tools": [],
                "resources": [],
                "budget": deepcopy(budget),
            },
        },
        "workflows": {
            "record": workflow(
                "Record acceptance source",
                _object(content),
                {
                    "persist": {
                        "uses": "persist",
                        "inputMapping": {
                            "object": {
                                "title": {"ref": "workflow.input.title"},
                                "text": {"ref": "workflow.input.text"},
                                "sourceKind": {"value": "original"},
                                "sourceNoteIds": {"value": []},
                            }
                        },
                    }
                },
            ),
            "summarize": workflow(
                "Summarize acceptance sources",
                inputs,
                {
                    "lookup": {
                        "uses": "lookup",
                        "inputMapping": {
                            "object": {
                                "query": {"ref": "workflow.input.query"},
                                "limit": {"value": 20},
                                "includeDerived": {"ref": "workflow.input.includeDerived"},
                            }
                        },
                    },
                    "compose": {
                        "uses": "compose",
                        "inputMapping": {
                            "object": {
                                "text": {"ref": "workflow.input.text"},
                                "sources": {"ref": "nodes.lookup.output"},
                            }
                        },
                        "condition": {
                            "op": "eq",
                            "args": [{"ref": "workflow.input.summarize"}, {"value": True}],
                        },
                    },
                    "persist": {
                        "uses": "persist",
                        "dependsOn": ["lookup"],
                        "acceptUpstreamStates": ["succeeded", "skipped"],
                        "inputMapping": {
                            "object": {
                                "title": {"ref": "workflow.input.title"},
                                "text": {
                                    "ref": "nodes.compose.output.text",
                                    "onMissing": {"ref": "workflow.input.text"},
                                },
                                "sourceKind": {"value": "derived"},
                                "sourceNoteIds": {
                                    "ref": "nodes.lookup.output.sourceNoteIds",
                                    "onMissing": {"value": []},
                                },
                            }
                        },
                        "condition": {"op": "exists", "args": [{"ref": "nodes.lookup.output"}]},
                    },
                },
            ),
        },
    }
