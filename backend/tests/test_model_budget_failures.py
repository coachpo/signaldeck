"""Unverifiable and truncated model calls remain terminal across activity recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from temporalio.exceptions import ApplicationError

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.model_runtime import GatewayModel
from tests.fake_openai_provider import _response
from tests.test_durable_runtime_support import serve_app
from tests.test_model_output_enforcement import EvidenceMemory, _chat_response


@pytest.mark.parametrize("style", ["chat_completions", "responses"])
@pytest.mark.parametrize("failure", ["missing", "partial", "truncated"])
def test_incomplete_model_call_is_not_reissued(tmp_path, monkeypatch, style, failure):
    monkeypatch.setattr(
        "app.infrastructure.model_runtime.activity.info", lambda: SimpleNamespace(attempt=1)
    )

    async def scenario():
        app, calls, store = FastAPI(), [], EvidenceMemory()

        @app.post("/v1/{path:path}")
        async def completion(request: Request):
            calls.append(await request.json())
            if style == "chat_completions":
                response = _chat_response({"prompt_tokens": 3, "completion_tokens": 2})
                if failure == "truncated":
                    response["choices"][0]["finish_reason"] = "length"
                elif failure == "partial":
                    del response["usage"]["prompt_tokens"]
            else:
                response = _response("partial output")
                response["usage"] = {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}
                if failure == "truncated":
                    response["status"] = "incomplete"
                    response["incomplete_details"] = {"reason": "max_output_tokens"}
                elif failure == "partial":
                    del response["usage"]["input_tokens"]
            if failure == "missing":
                del response["usage"]
            return response

        gateway = GatewayModel(store, lambda *_: {}, ArtifactStore(tmp_path / "artifacts"))
        async with serve_app(app) as url:
            settings = {
                "signaldeck_context": {
                    "runId": "run",
                    "nodeId": "node",
                    "invocationId": "agent",
                    "modelCallId": "model",
                    "resourceId": "model",
                    "requireUsage": True,
                    "deadline": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
                    "binding": {
                        "baseUrl": url + "/v1",
                        "modelId": "test",
                        "apiStyle": style,
                        "credentialRevision": "one",
                    },
                }
            }
            expected = (
                "model_output_truncated" if failure == "truncated" else "model_usage_unavailable"
            )
            for _ in range(2):
                with pytest.raises(ApplicationError) as error:
                    await gateway.request(
                        [ModelRequest(parts=[UserPromptPart("hello")])],
                        settings,
                        ModelRequestParameters(),
                    )
                assert error.value.message == expected
                assert error.value.non_retryable
        assert len(calls) == 1
        assert not (set(calls[0]) & {"max_tokens", "max_completion_tokens", "max_output_tokens"})
        for key in ("model", "model:attempt:1"):
            evidence = store.rows[key]
            assert evidence.status == "failed" and evidence.error_code == expected
            assert evidence.metadata["usage"] == {
                "inputTokens": 3 if failure == "truncated" else None,
                "outputTokens": None if failure == "missing" else 2,
            }
            assert evidence.metadata["finishReason"] == (
                "length" if failure == "truncated" else "stop"
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("style", ["chat_completions", "responses"])
def test_output_only_budget_accepts_unknown_input_usage(tmp_path, style):
    async def scenario():
        app = FastAPI()

        @app.post("/v1/{path:path}")
        async def completion():
            if style == "chat_completions":
                return _chat_response({"completion_tokens": 2})
            response = _response("hello")
            response["usage"] = {"output_tokens": 2}
            return response

        gateway = GatewayModel(None, lambda *_: {}, ArtifactStore(tmp_path / "artifacts"))
        async with serve_app(app) as url:
            _, usage = await gateway._request_io(
                [ModelRequest(parts=[UserPromptPart("hello")])],
                {"max_tokens": 12},
                ModelRequestParameters(),
                {
                    "resourceId": "model",
                    "requireUsage": False,
                    "deadline": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
                    "binding": {
                        "baseUrl": url + "/v1",
                        "modelId": "test",
                        "apiStyle": style,
                        "credentialRevision": "one",
                    },
                },
            )
        assert usage == {"inputTokens": None, "outputTokens": 2}

    asyncio.run(scenario())
