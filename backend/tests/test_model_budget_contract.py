"""Optional output limits preserve old hashes and bound both provider protocols."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.usage import RunUsage

from app.domain.compiler import compile_package
from app.domain.definition_parser import parse_package_source
from app.domain.schema_contract import DomainValidationError
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.model_runtime import GatewayModel
from app.infrastructure.temporal_agent import model_settings
from tests.fake_openai_provider import _response
from tests.test_dag_compiler import package
from tests.test_durable_runtime_support import serve_app
from tests.test_platform_api import source
from tests.test_task_experience import configured
from tests.test_task_experience import platform as platform_fixture

platform = platform_fixture


def test_omitted_output_limit_preserves_pre_s3_hash_and_serialization():
    compiled = compile_package(package())
    # Independently captured with the pre-S3 definitions at 5a993684.
    assert (
        compiled.content_hash == "97f5fdbc44285fbabf7a200a2d7f7825ae5af4cb31e9aa822d5b44073dd799b6"
    )
    encoded = compiled.package.model_dump(mode="json", by_alias=True)
    assert "maxOutputTokens" not in encoded["agents"]["echo"]["budget"]
    assert compile_package(encoded).content_hash == compiled.content_hash
    explicit = package()
    explicit["agents"]["echo"]["budget"] = {"maxOutputTokens": 512}
    changed = parse_package_source(json.dumps(explicit))
    assert changed.content_hash != compiled.content_hash
    assert (
        changed.package.model_dump(mode="json", by_alias=True)["agents"]["echo"]["budget"][
            "maxOutputTokens"
        ]
        == 512
    )


@pytest.mark.parametrize("value", [None, 0, -1, 1.5, "invalid"])
def test_invalid_output_limit_has_source_location(value):
    definition = package()
    definition["agents"]["echo"]["budget"] = {"maxOutputTokens": value}
    with pytest.raises(DomainValidationError) as error:
        parse_package_source(json.dumps(definition, indent=2))
    diagnostic = next(d for d in error.value.diagnostics if "maxOutputTokens" in d.path)
    assert diagnostic.line and diagnostic.column


def context(budget):
    return SimpleNamespace(
        deps={
            "agent": {"budget": budget, "strategy": {"modelRef": "model"}},
            "runId": "run",
            "nodeId": "node",
            "invocationId": "invocation",
            "modelBinding": {},
            "deadline": "unused",
        },
        usage=RunUsage(input_tokens=30, output_tokens=20),
        run_step=1,
    )


@pytest.mark.parametrize(
    "budget,expected",
    [
        ({"maxTokens": 100}, 50),
        ({"maxTokens": 100, "maxOutputTokens": 80}, 50),
        ({"maxTokens": 100, "maxOutputTokens": 12}, 12),
    ],
)
def test_output_limit_is_independent_and_capped_by_remaining_total(budget, expected):
    assert model_settings(context(budget))["max_tokens"] == expected


def test_exhausted_explicit_budget_cannot_request_an_extra_token():
    with pytest.raises(UsageLimitExceeded):
        model_settings(context({"maxTokens": 50, "maxOutputTokens": 12}))
    assert model_settings(context({"maxTokens": 50}))["max_tokens"] == 1


def test_output_limit_changes_only_new_frozen_runs(platform):
    client, store, _ = platform
    configured(client, store, model=True)
    launch = {"workflowKey": "main", "parameters": {"text": "hello"}}
    old = client.post(
        "/api/workflow-packages/api-package/launches", json={**launch, "launchId": "budget-old"}
    ).json()
    definition = json.loads(source(model=True))
    definition["agents"]["echo"]["budget"] = {"maxOutputTokens": 128}
    assert (
        client.post(
            "/api/workflow-packages", json={"manifestSource": json.dumps(definition)}
        ).status_code
        == 201
    )
    new = client.post(
        "/api/workflow-packages/api-package/launches", json={**launch, "launchId": "budget-new"}
    ).json()
    assert (
        "maxOutputTokens"
        not in store.get_run(old["id"]).spec.definition["agents"]["echo"]["budget"]
    )
    assert (
        store.get_run(new["id"]).spec.definition["agents"]["echo"]["budget"]["maxOutputTokens"]
        == 128
    )
    prepared = client.post("/api/workflow-packages/api-package/prepare", json=launch).json()
    assert prepared["effectiveSettings"]["agents"]["echo"]["budget"]["maxOutputTokens"] == 128


@pytest.mark.parametrize(
    "style,field",
    [("chat_completions", "max_completion_tokens"), ("responses", "max_output_tokens")],
)
@pytest.mark.parametrize("report_usage", [True, False])
def test_actual_adapter_wire_output_cap_and_usage_presence(tmp_path, style, field, report_usage):
    async def scenario():
        app = FastAPI()
        calls = []

        @app.post("/v1/{path:path}")
        async def completion(request: Request):
            body = await request.json()
            calls.append(body)
            if style == "responses":
                response = _response("hello", include_usage=report_usage)
                if report_usage:
                    response["usage"] = {"input_tokens": 3, "output_tokens": 0, "total_tokens": 3}
                return response
            response = {
                "id": "chat-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hello"},
                        "finish_reason": "stop",
                    }
                ],
            }
            if report_usage:
                response["usage"] = {"prompt_tokens": 3, "completion_tokens": 0, "total_tokens": 3}
            return response

        gateway = GatewayModel(
            None, lambda *_: {"apiKey": "controlled-key"}, ArtifactStore(tmp_path / "artifacts")
        )
        async with serve_app(app) as url:
            _, usage = await gateway._request_io(
                [ModelRequest(parts=[UserPromptPart("hello")])],
                {
                    "max_tokens": model_settings(
                        context({"maxTokens": 100, "maxOutputTokens": 12})
                    )["max_tokens"]
                },
                ModelRequestParameters(),
                {
                    "resourceId": "model",
                    "binding": {
                        "baseUrl": url + "/v1",
                        "modelId": "test",
                        "apiStyle": style,
                        "credentialRevision": "one",
                    },
                    "deadline": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
                },
            )
        assert len(calls) == 1
        assert calls[0][field] == 12
        assert usage == (
            {"inputTokens": 3, "outputTokens": 0}
            if report_usage
            else {"inputTokens": None, "outputTokens": None}
        )

    asyncio.run(scenario())
