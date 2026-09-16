"""Small workflow fixtures owned by the isolated deployment checks."""


def _object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "unevaluatedProperties": False,
    }


def _content_schema() -> dict:
    return _object(
        {
            "title": {"type": "string", "minLength": 1, "maxLength": 160},
            "text": {"type": "string", "minLength": 1, "maxLength": 100000},
        }
    )


def _model_agent(suffix: str) -> dict:
    text = _object({"text": _content_schema()["properties"]["text"]})
    return {
        "inputSchema": text,
        "outputSchema": text,
        "strategy": {
            "kind": "model",
            "modelRef": "compose-model-" + suffix,
            "prompt": "Return the supplied text using the required output schema.",
        },
    }


def _processing_workflow(output: dict) -> dict:
    inputs = _content_schema()
    inputs["properties"]["useModel"] = {"type": "boolean"}
    inputs["required"].append("useModel")
    return {
        "inputSchema": inputs,
        "outputSchema": output,
        "nodes": {
            "process": {
                "uses": "process",
                "inputMapping": {"object": {"text": {"ref": "workflow.input.text"}}},
                "condition": {
                    "op": "eq",
                    "args": [{"ref": "workflow.input.useModel"}, {"value": True}],
                },
            },
            "save": {
                "uses": "save",
                "acceptUpstreamStates": ["succeeded", "skipped"],
                "inputMapping": {
                    "object": {
                        "title": {"ref": "workflow.input.title"},
                        "text": {
                            "ref": "nodes.process.output.text",
                            "onMissing": {"ref": "workflow.input.text"},
                        },
                    }
                },
            },
        },
        "outputMapping": {"ref": "nodes.save.output"},
    }


def notes_package(suffix: str) -> dict:
    output = _object({"id": {"type": "string"}, "text": {"type": "string"}})
    return {
        "apiVersion": "signaldeck.workflowPackage/v2",
        "metadata": {"key": "compose-notes-" + suffix, "name": "Notes deployment check"},
        "agents": {
            "process": _model_agent(suffix),
            "save": {
                "inputSchema": _content_schema(),
                "outputSchema": output,
                "tools": ["example/notes/create"],
                "resources": ["notes-workspace"],
                "strategy": {
                    "kind": "deterministic",
                    "toolId": "example/notes/create",
                    "inputMapping": {"ref": "agent.input"},
                    "outputMapping": {
                        "object": {
                            "id": {"ref": "tool.output.id"},
                            "text": {"ref": "tool.output.text"},
                        }
                    },
                },
            },
        },
        "workflows": {
            "capture": {
                "inputSchema": _content_schema(),
                "outputSchema": output,
                "nodes": {"save": {"uses": "save", "inputMapping": {"ref": "workflow.input"}}},
                "outputMapping": {"ref": "nodes.save.output"},
            },
            "process": _processing_workflow(output),
        },
    }


def finance_package(suffix: str) -> dict:
    output = _object({"slug": {"type": "string"}})
    return {
        "apiVersion": "signaldeck.workflowPackage/v2",
        "metadata": {"key": "compose-finance-" + suffix, "name": "Report deployment check"},
        "agents": {
            "process": _model_agent(suffix),
            "save": {
                "inputSchema": _content_schema(),
                "outputSchema": output,
                "tools": ["signaldeck/finance/reports_create"],
                "strategy": {
                    "kind": "deterministic",
                    "toolId": "signaldeck/finance/reports_create",
                    "inputMapping": {
                        "object": {
                            "name": {"ref": "agent.input.title"},
                            "content": {"ref": "agent.input.text"},
                        }
                    },
                    "outputMapping": {"object": {"slug": {"ref": "tool.output.slug"}}},
                },
            },
        },
        "workflows": {"report": _processing_workflow(output)},
    }
