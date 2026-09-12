"""Model replies retain their declared JSON root and the user's original content."""

import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.exceptions import ApplicationError

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.temporal_activities import RuntimeActivities
from app.infrastructure.temporal_payloads import pack_value, unpack_value

OUTPUT_CASES = [
    pytest.param(
        {"type": "string"}, '  原文\n{"text": "保持"}\n```python\nprint(1)\n```  ', 7, id="string"
    ),
    pytest.param({"type": "array", "items": {"type": "string"}}, ["甲", "乙"], "甲", id="array"),
    pytest.param(
        {
            "type": "object",
            "properties": {"text": {"type": "string", "title": "正文"}},
            "required": ["text"],
        },
        {"text": "  原文\n保持  "},
        ["原文"],
        id="object",
    ),
    pytest.param({"type": "integer"}, 7, 1.5, id="integer"),
    pytest.param({"type": "number"}, 1.25, "1.25", id="number"),
    pytest.param({"type": "boolean"}, False, 0, id="boolean"),
    pytest.param({"type": "null"}, None, "null", id="null"),
]


@pytest.fixture
def runtime(tmp_path):
    return RuntimeActivities(
        Mock(), ArtifactStore(tmp_path / "artifacts"), AsyncMock(), "unused", Mock()
    )


def agent(schema):
    return {
        "inputSchema": {"type": "string"},
        "outputSchema": {**schema, "title": "回答", "description": "保留原文，不添加事实。"},
        "strategy": {
            "kind": "model",
            "modelRef": "model",
            "prompt": '  请整理以下内容。\n原始代码：print("hello")\n  ',
        },
        "budget": {"maxModelRequests": 3, "maxTokens": 900, "deadlineSeconds": 30},
    }


@pytest.mark.parametrize("schema,value,wrong_type", OUTPUT_CASES)
def test_agent_prompt_preserves_user_content_and_explains_response_root(
    runtime, schema, value, wrong_type
):
    original_input = '  用户输入\n{"回答":"不是平台字段"}\n```yaml\na: b\n```  '
    payload = {"agent": agent(schema), "input": pack_value(runtime.artifacts, original_input)}
    before = deepcopy(payload)
    prompt = json.loads(asyncio.run(runtime.agent_prompt(payload)))
    assert payload == before
    assert prompt["instructions"] == before["agent"]["strategy"]["prompt"]
    assert prompt["input"] == original_input
    assert prompt["outputContract"] == before["agent"]["outputSchema"]
    instructions = prompt["responseInstructions"]
    assert "exactly one JSON value matching outputContract" in instructions
    assert "Preserve the declared root type" in instructions
    assert "for string, return a quoted JSON string" in instructions
    assert "for array, return a JSON array" in instructions
    assert (
        "title and description are labels and documentation, not object property names"
        in instructions
    )
    assert "Do not invent an object wrapper or property from those labels" in instructions


@pytest.mark.parametrize("schema,value,wrong_type", OUTPUT_CASES)
@pytest.mark.parametrize("source", ["text", "output"])
def test_agent_output_accepts_exact_declared_root_without_rewriting(
    runtime, schema, value, wrong_type, source
):
    payload = {
        "agent": agent(schema),
        source: json.dumps(value, ensure_ascii=False) if source == "text" else value,
    }
    before = deepcopy(payload)
    output = unpack_value(runtime.artifacts, asyncio.run(runtime.validate_agent_output(payload)))
    assert output == value and type(output) is type(value)
    assert payload == before


@pytest.mark.parametrize("schema,value,wrong_type", OUTPUT_CASES)
@pytest.mark.parametrize("failure", ["wrong-type", "title-wrapper"])
def test_agent_output_rejects_wrong_root_and_title_wrappers(
    runtime, schema, value, wrong_type, failure
):
    value = wrong_type if failure == "wrong-type" else {"回答": value}
    payload = {"agent": agent(schema), "text": json.dumps(value, ensure_ascii=False)}
    before = deepcopy(payload)
    with pytest.raises(ApplicationError) as error:
        asyncio.run(runtime.validate_agent_output(payload))
    assert error.value.message == "agent_output_invalid" and error.value.non_retryable
    assert payload == before


@pytest.mark.parametrize("text", ["未加引号的文字", '```json\n"文字"\n```', '"文字"\n"更多"'])
def test_agent_output_does_not_salvage_unquoted_fenced_or_multiple_json_values(runtime, text):
    with pytest.raises(ApplicationError) as error:
        asyncio.run(
            runtime.validate_agent_output({"agent": agent({"type": "string"}), "text": text})
        )
    assert error.value.message == "agent_output_invalid" and error.value.non_retryable
