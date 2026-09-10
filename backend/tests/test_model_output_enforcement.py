"""Provider responses must satisfy the requested cap before becoming Agent input."""

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


class EvidenceMemory:
    def __init__(self):
        self.rows = {}

    def get_evidence(self, key):
        return self.rows.get(key)

    def record_evidence(self, evidence):
        self.rows[evidence.id] = evidence

    def record_evidence_batch(self, evidence):
        for row in evidence:
            self.record_evidence(row)


@pytest.mark.parametrize(
    "style,field",
    [
        ("chat_completions", "max_tokens"),
        ("chat_completions", "max_completion_tokens"),
        ("responses", "max_output_tokens"),
    ],
)
@pytest.mark.parametrize("output_tokens", [12, 13, None])
@pytest.mark.parametrize("malformed", [False, True])
def test_gateway_checks_reported_usage_and_replays_violation_without_network(
    tmp_path, monkeypatch, style, field, output_tokens, malformed
):
    monkeypatch.setattr(
        "app.infrastructure.model_runtime.activity.info", lambda: SimpleNamespace(attempt=1)
    )

    async def scenario():
        app, calls, store = FastAPI(), [], EvidenceMemory()

        @app.post("/v1/{path:path}")
        async def completion(request: Request):
            calls.append(await request.json())
            if style == "responses":
                response = _response("hello", include_usage=False)
                if malformed:
                    response["output"] = [{"type": "not-a-valid-output"}]
                if output_tokens is not None:
                    response["usage"] = {
                        "input_tokens": 3,
                        "output_tokens": output_tokens,
                        "total_tokens": 3 + output_tokens,
                    }
                return response
            response = {
                "id": "chat-cap",
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
            if output_tokens is not None:
                response["usage"] = {
                    "prompt_tokens": 3,
                    "completion_tokens": output_tokens,
                    "total_tokens": 3 + output_tokens,
                }
            if malformed:
                response["choices"] = []
            return response

        gateway = GatewayModel(
            store, lambda *_: {"apiKey": "controlled-secret"}, ArtifactStore(tmp_path / "artifacts")
        )
        async with serve_app(app) as url:
            settings = {
                "max_tokens": 12,
                "signaldeck_context": {
                    "runId": "run",
                    "nodeId": "node",
                    "invocationId": "agent",
                    "modelCallId": "model",
                    "resourceId": "model",
                    "deadline": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
                    "binding": {
                        "baseUrl": url + "/v1",
                        "modelId": "arbitrary",
                        "apiStyle": style,
                        "credentialRevision": "one",
                        "providerCapabilities": {"outputTokenLimitParameter": field},
                    },
                },
            }

            async def call():
                return await gateway.request(
                    [ModelRequest(parts=[UserPromptPart("hello")])],
                    settings,
                    ModelRequestParameters(),
                )

            if output_tokens == 13:
                for _ in range(2):
                    with pytest.raises(ApplicationError) as error:
                        await call()
                    assert error.value.message == "model_output_limit_exceeded"
                    assert error.value.non_retryable
                assert store.rows["model"].status == "failed"
                assert store.rows["model"].metadata["errorCategory"] == "output_limit"
                assert store.rows["model"].output is None
                assert store.rows["model"].metadata["finishReason"] == (
                    None if malformed and style == "chat_completions" else "stop"
                )
            elif malformed:
                with pytest.raises(ApplicationError) as error:
                    await call()
                # Preserve the existing retry classification for SDK parsing errors;
                # reported usage survives even when the response was not accepted.
                assert error.value.message == "model_request_failed"
                assert store.rows["model"].status == "unknown"
            else:
                await call()
                assert store.rows["model"].status == "succeeded"
            assert len(calls) == 1
            assert calls[0][field] == 12
            for key in ("model", "model:attempt:1"):
                metadata = store.rows[key].metadata
                assert metadata["outputTokenLimitParameter"] == field
                assert metadata["outputTokenLimit"] == 12
                assert metadata["usage"] == {
                    "inputTokens": 3 if output_tokens is not None else None,
                    "outputTokens": output_tokens,
                }
            assert "controlled-secret" not in str(store.rows)

    asyncio.run(scenario())


def _chat_response(usage):
    return {
        "id": "chat-usage-boundary",
        "object": "chat.completion",
        "created": 0,
        "model": "arbitrary",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "x"},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


def _chat_settings(url):
    return {
        "max_tokens": 12,
        "signaldeck_context": {
            "runId": "run",
            "nodeId": "node",
            "invocationId": "agent",
            "modelCallId": "model",
            "resourceId": "model",
            "deadline": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            "binding": {
                "baseUrl": url + "/v1",
                "modelId": "arbitrary",
                "apiStyle": "chat_completions",
                "credentialRevision": "one",
            },
        },
    }


@pytest.mark.parametrize(
    "counter,reasoning,expected",
    [
        pytest.param(13, 12, 13, id="reasoning-counts-toward-limit"),
        pytest.param(0, 0, 0, id="explicit-zero"),
        pytest.param(True, 0, None, id="boolean-is-unknown"),
        pytest.param(-1, 0, None, id="negative-is-unknown"),
        pytest.param("13", 0, None, id="string-is-unknown"),
        pytest.param(13.5, 0, None, id="fraction-is-unknown"),
    ],
)
def test_gateway_preserves_raw_counter_presence_and_total_reasoning(
    tmp_path, monkeypatch, counter, reasoning, expected
):
    monkeypatch.setattr(
        "app.infrastructure.model_runtime.activity.info", lambda: SimpleNamespace(attempt=1)
    )

    async def scenario():
        app, calls, store = FastAPI(), [], EvidenceMemory()

        @app.post("/v1/chat/completions")
        async def completion(request: Request):
            calls.append(await request.json())
            return _chat_response(
                {
                    "prompt_tokens": counter,
                    "completion_tokens": counter,
                    "total_tokens": 26 if reasoning else 0,
                    "completion_tokens_details": {"reasoning_tokens": reasoning},
                }
            )

        gateway = GatewayModel(
            store, lambda *_: {"apiKey": "controlled-secret"}, ArtifactStore(tmp_path / "artifacts")
        )
        async with serve_app(app) as url:
            error = None
            try:
                await gateway.request(
                    [ModelRequest(parts=[UserPromptPart("hello")])],
                    _chat_settings(url),
                    ModelRequestParameters(),
                )
            except ApplicationError as exc:
                error = exc
            if reasoning:
                assert error is not None
                assert error.message == "model_output_limit_exceeded" and error.non_retryable
                assert store.rows["model"].status == "failed"
                assert store.rows["model"].output is None
            elif expected == 0:
                assert error is None
                assert store.rows["model"].status == "succeeded"
            elif error is not None:
                # SDKs may reject malformed counters; they must not reinterpret
                # them as provider-reported integers or claim an output violation.
                assert error.message in {"model_request_failed", "model_response_invalid"}
            assert len(calls) == 1
            assert calls[0]["max_completion_tokens"] == 12
            for key in ("model", "model:attempt:1"):
                assert store.rows[key].metadata["usage"] == {
                    "inputTokens": expected,
                    "outputTokens": expected,
                }

    asyncio.run(scenario())


@pytest.mark.parametrize("worker_shutdown", [False, True])
def test_gateway_cancellation_before_response_keeps_unreported_usage_unknown(
    tmp_path, monkeypatch, worker_shutdown
):
    monkeypatch.setattr(
        "app.infrastructure.model_runtime.activity.info", lambda: SimpleNamespace(attempt=1)
    )
    monkeypatch.setattr(
        "app.infrastructure.model_runtime.activity.is_worker_shutdown", lambda: worker_shutdown
    )

    async def scenario():
        app, calls, store = FastAPI(), [], EvidenceMemory()
        request_started, release_response = asyncio.Event(), asyncio.Event()

        @app.post("/v1/chat/completions")
        async def completion(request: Request):
            calls.append(await request.json())
            request_started.set()
            await release_response.wait()
            return _chat_response({"prompt_tokens": 3, "completion_tokens": 13})

        gateway = GatewayModel(
            store, lambda *_: {"apiKey": "controlled-secret"}, ArtifactStore(tmp_path / "artifacts")
        )
        async with serve_app(app) as url:
            task = asyncio.create_task(
                gateway.request(
                    [ModelRequest(parts=[UserPromptPart("hello")])],
                    _chat_settings(url),
                    ModelRequestParameters(),
                )
            )
            try:
                await asyncio.wait_for(request_started.wait(), timeout=5)
                assert store.rows["model:attempt:1"].status == "running"
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=5)
                assert len(calls) == 1
                for key in ("model", "model:attempt:1"):
                    row = store.rows[key]
                    assert row.status == ("unknown" if worker_shutdown else "cancelled")
                    assert row.error_code == (
                        "worker_interrupted" if worker_shutdown else "model_cancelled"
                    )
                    assert row.output is None and row.finished_at is not None
                    assert "usage" not in row.metadata
            finally:
                release_response.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
