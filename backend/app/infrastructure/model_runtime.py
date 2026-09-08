"""Model I/O with confirmed-call reuse and independent network attempt evidence."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, cast

import httpx2
from openai import APIStatusError, AsyncOpenAI
from pydantic import TypeAdapter
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.domain.execution import ApplicationError as DomainApplicationError
from app.domain.execution import ExecutionEvidence
from app.domain.resources import ResolvedModelConfiguration
from app.infrastructure.temporal_payloads import pack_value, unpack_value
from app.infrastructure.temporal_ports import ArtifactValues, BoundCredentialReader, ModelEvidence

RESPONSE = TypeAdapter(ModelResponse)


class GatewayModel(Model):
    def __init__(
        self, evidence: ModelEvidence, credentials: BoundCredentialReader, artifacts: ArtifactValues
    ) -> None:
        super().__init__()
        self.evidence, self.credentials, self.artifacts = evidence, credentials, artifacts

    @property
    def model_name(self) -> str:
        return "signaldeck-model-gateway"

    @property
    def system(self) -> str:
        return "signaldeck"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        settings: dict[str, Any] = dict(model_settings or {})
        context = settings.pop("signaldeck_context")
        store, artifacts = self.evidence, self.artifacts
        model_id = context["modelCallId"]
        confirmed = await asyncio.to_thread(store.get_evidence, model_id)
        if confirmed is not None and confirmed.status == "succeeded":
            return RESPONSE.validate_python(unpack_value(artifacts, confirmed.output))
        input_value = pack_value(
            artifacts,
            {
                "messages": ModelMessagesTypeAdapter.dump_python(messages, mode="json"),
                "modelBinding": context["binding"],
                "tools": [
                    {"name": tool.name, "schema": tool.parameters_json_schema}
                    for tool in model_request_parameters.function_tools
                ],
            },
        )
        evidence = ExecutionEvidence(
            id=model_id,
            run_id=context["runId"],
            node_id=context["nodeId"],
            parent_id=context["invocationId"],
            kind="model",
            status="running",
            input=input_value,
            started_at=datetime.now(UTC),
        )
        await asyncio.to_thread(store.record_evidence, evidence)
        attempt = activity.info().attempt
        for earlier in range(1, attempt):
            interrupted = await asyncio.to_thread(
                store.get_evidence, f"{model_id}:attempt:{earlier}"
            )
            if interrupted is not None and interrupted.status == "running":
                await asyncio.to_thread(
                    store.record_evidence,
                    interrupted.model_copy(
                        update={
                            "status": "unknown",
                            "error_code": "worker_interrupted",
                            "finished_at": datetime.now(UTC),
                        }
                    ),
                )
        network = ExecutionEvidence(
            id=f"{model_id}:attempt:{attempt}",
            run_id=context["runId"],
            node_id=context["nodeId"],
            parent_id=model_id,
            kind="attempt",
            status="running",
            attempt=attempt,
            input=input_value,
            started_at=datetime.now(UTC),
            metadata={"networkKind": "model_request"},
        )
        await asyncio.to_thread(store.record_evidence, network)
        try:
            response = await self._request_io(messages, settings, model_request_parameters, context)
            output = pack_value(artifacts, RESPONSE.dump_python(response, mode="json"))
            # Both confirmations commit together before replying to Temporal.
            await asyncio.to_thread(
                store.record_evidence_batch,
                [
                    network.model_copy(
                        update={
                            "status": "succeeded",
                            "output": output,
                            "finished_at": datetime.now(UTC),
                        }
                    ),
                    evidence.model_copy(
                        update={
                            "status": "succeeded",
                            "output": output,
                            "finished_at": datetime.now(UTC),
                        }
                    ),
                ],
            )
            return response
        except asyncio.CancelledError:
            updates = {
                "status": "unknown" if activity.is_worker_shutdown() else "cancelled",
                "error_code": (
                    "worker_interrupted" if activity.is_worker_shutdown() else "model_cancelled"
                ),
                "finished_at": datetime.now(UTC),
            }
            await asyncio.shield(
                asyncio.to_thread(
                    store.record_evidence_batch,
                    [network.model_copy(update=updates), evidence.model_copy(update=updates)],
                )
            )
            raise
        except Exception as exc:
            code, non_retryable, failure_metadata = model_failure(exc)
            await asyncio.to_thread(
                store.record_evidence_batch,
                [
                    network.model_copy(
                        update={
                            "status": "failed",
                            "error_code": code,
                            "finished_at": datetime.now(UTC),
                            "metadata": {**network.metadata, **failure_metadata},
                        }
                    ),
                    evidence.model_copy(
                        update={
                            "status": "failed" if non_retryable or attempt >= 3 else "unknown",
                            "error_code": code,
                            "finished_at": datetime.now(UTC),
                        }
                    ),
                ],
            )
            # SDK/HTTP exception text can embed credentials. Only stable adapter codes cross.
            raise ApplicationError(code, non_retryable=non_retryable) from None

    async def _request_io(
        self,
        messages: list[ModelMessage],
        settings: dict[str, Any],
        parameters: ModelRequestParameters,
        context: dict[str, Any],
    ) -> ModelResponse:
        binding = ResolvedModelConfiguration.model_validate(context["binding"])
        credentials = await asyncio.to_thread(
            self.credentials, context["resourceId"], binding.credential_revision
        )
        remaining = (
            datetime.fromisoformat(context["deadline"]) - datetime.now(UTC)
        ).total_seconds()
        if remaining <= 0:
            raise ApplicationError("deadline_exceeded", non_retryable=True)
        api_key = credentials.get("apiKey", "")
        async with httpx2.AsyncClient(timeout=min(binding.timeout_seconds, remaining)) as http:
            client = AsyncOpenAI(
                base_url=binding.base_url,
                api_key=api_key or "local-no-credential",
                max_retries=0,
                http_client=http,
            )
            provider = OpenAIProvider(openai_client=client)
            model_type = (
                OpenAIChatModel if binding.api_style == "chat_completions" else OpenAIResponsesModel
            )
            model = model_type(
                binding.model_id,
                provider=provider,
                profile={
                    "json_schema_transformer": None,
                },
            )
            # Exact declared constraints must reach the adapter unchanged.
            _, rendered = model.prepare_request(cast(ModelSettings, settings), parameters)
            if [tool.parameters_json_schema for tool in rendered.function_tools] != [
                tool.parameters_json_schema for tool in parameters.function_tools
            ]:
                raise ApplicationError("provider_schema_unsupported", non_retryable=True)
            response = await model.request(messages, cast(ModelSettings, settings), parameters)
            encoded = json.dumps(RESPONSE.dump_python(response, mode="json"))
            if any(
                isinstance(value, str) and value and value in encoded
                for value in credentials.values()
            ):
                raise ApplicationError("model_response_contains_credential", non_retryable=True)
            return response


def model_failure(exc: Exception) -> tuple[str, bool, dict[str, Any]]:
    if isinstance(exc, ApplicationError):
        return exc.message, exc.non_retryable, {"failureType": "execution_contract"}
    if isinstance(exc, DomainApplicationError):
        return exc.code, True, {"failureType": "resource_contract", "networkStarted": False}
    if isinstance(exc, UnexpectedModelBehavior):
        return "model_response_invalid", True, {"failureType": "invalid_model_response"}
    if isinstance(exc, (ModelHTTPError, APIStatusError)):
        status = exc.status_code
        return (
            "model_http_error",
            status != 429 and status < 500,
            {"failureType": "http_error", "httpStatus": status},
        )
    return "model_request_failed", False, {"failureType": "transport_or_provider_error"}
