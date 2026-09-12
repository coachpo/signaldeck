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
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.domain.execution import ApplicationError as DomainApplicationError
from app.domain.execution import ExecutionEvidence
from app.domain.model_diagnostics import model_binding_digest
from app.domain.resources import ResolvedModelConfiguration
from app.infrastructure.model_usage_capture import (
    ModelOutputLimitExceeded,
    ModelResponseFailure,
    ReportedModelUsage,
)
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
        if confirmed is not None and confirmed.error_code == "model_output_limit_exceeded":
            raise ApplicationError("model_output_limit_exceeded", non_retryable=True)
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
        binding_metadata = {
            "resourceId": context["resourceId"],
            "modelBindingDigest": model_binding_digest(context["binding"]),
            "outputTokenLimit": settings.get("max_tokens"),
            "outputTokenLimitParameter": ResolvedModelConfiguration.model_validate(
                context["binding"]
            ).output_token_limit_parameter,
        }
        evidence = ExecutionEvidence(
            id=model_id,
            run_id=context["runId"],
            node_id=context["nodeId"],
            parent_id=context["invocationId"],
            kind="model",
            status="running",
            input=input_value,
            started_at=datetime.now(UTC),
            metadata=binding_metadata,
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
            metadata={
                "networkKind": "model_request",
                **binding_metadata,
            },
        )
        await asyncio.to_thread(store.record_evidence, network)
        try:
            response, reported_usage = await self._request_io(
                messages, settings, model_request_parameters, context
            )
            output = pack_value(artifacts, RESPONSE.dump_python(response, mode="json"))
            # Both confirmations commit together before replying to Temporal.
            await asyncio.to_thread(
                store.record_evidence_batch,
                [
                    network.model_copy(
                        update={
                            "status": "succeeded",
                            "metadata": {
                                **network.metadata,
                                "usage": reported_usage,
                                "finishReason": response.finish_reason,
                            },
                            "output": output,
                            "finished_at": datetime.now(UTC),
                        }
                    ),
                    evidence.model_copy(
                        update={
                            "status": "succeeded",
                            "metadata": {
                                **binding_metadata,
                                "usage": reported_usage,
                                "finishReason": response.finish_reason,
                            },
                            "output": output,
                            "finished_at": datetime.now(UTC),
                        }
                    ),
                ],
            )
            return response
        except asyncio.CancelledError:
            cancellation = activity.cancellation_details()
            # A lost activity lease is retryable; it does not confirm that the
            # logical model call was cancelled by its workflow. Terminal evidence
            # would otherwise prevent Temporal's next attempt from recovering it.
            runtime_interrupted = activity.is_worker_shutdown() or (
                cancellation is not None and not cancellation.cancel_requested
            )
            updates = {
                "status": "unknown" if runtime_interrupted else "cancelled",
                "error_code": "worker_interrupted" if runtime_interrupted else "model_cancelled",
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
                            "metadata": {**binding_metadata, **failure_metadata},
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
    ) -> tuple[ModelResponse, dict[str, int | None]]:
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
        reported_usage = ReportedModelUsage(binding.api_style, settings.get("max_tokens"))
        async with httpx2.AsyncClient(
            timeout=min(binding.timeout_seconds, remaining),
            event_hooks={"response": [reported_usage.observe]},
        ) as http:
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
                profile=OpenAIModelProfile(
                    json_schema_transformer=None,
                    openai_chat_supports_max_completion_tokens=(
                        binding.output_token_limit_parameter != "max_tokens"
                    ),
                ),
            )
            # Exact declared constraints must reach the adapter unchanged.
            _, rendered = model.prepare_request(cast(ModelSettings, settings), parameters)
            if [tool.parameters_json_schema for tool in rendered.function_tools] != [
                tool.parameters_json_schema for tool in parameters.function_tools
            ]:
                raise ApplicationError("provider_schema_unsupported", non_retryable=True)
            try:
                response = await model.request(messages, cast(ModelSettings, settings), parameters)
            except Exception as exc:
                reported_usage.check_limit()
                raise ModelResponseFailure(
                    exc, reported_usage.value, reported_usage.finish_reason
                ) from None
            reported_usage.check_limit()
            encoded = json.dumps(RESPONSE.dump_python(response, mode="json"))
            if any(
                isinstance(value, str) and value and value in encoded
                for value in credentials.values()
            ):
                raise ApplicationError("model_response_contains_credential", non_retryable=True)
            return response, reported_usage.value


def model_failure(exc: Exception) -> tuple[str, bool, dict[str, Any]]:
    if isinstance(exc, ModelResponseFailure):
        code, non_retryable, metadata = model_failure(exc.cause)
        return (
            code,
            non_retryable,
            {
                **metadata,
                "usage": exc.usage,
                "finishReason": exc.finish_reason,
            },
        )
    if isinstance(exc, ModelOutputLimitExceeded):
        return (
            "model_output_limit_exceeded",
            True,
            {
                "failureType": "execution_contract",
                "errorCategory": "output_limit",
                "networkStarted": True,
                "usage": exc.usage,
                "outputTokenLimit": exc.limit,
                "finishReason": exc.finish_reason,
            },
        )
    if isinstance(exc, ApplicationError):
        return (
            exc.message,
            exc.non_retryable,
            {
                "failureType": "execution_contract",
                "errorCategory": "unknown",
                "networkStarted": exc.message
                not in {"deadline_exceeded", "provider_schema_unsupported"},
            },
        )
    if isinstance(exc, DomainApplicationError):
        return (
            exc.code,
            True,
            {
                "failureType": "resource_contract",
                "networkStarted": False,
                "errorCategory": "unknown",
            },
        )
    if isinstance(exc, UnexpectedModelBehavior):
        return (
            "model_response_invalid",
            True,
            {"failureType": "invalid_model_response", "errorCategory": "unknown"},
        )
    if isinstance(exc, (ModelHTTPError, APIStatusError)):
        status = exc.status_code
        return (
            "model_http_error",
            status != 429 and status < 500,
            {
                "failureType": "http_error",
                "httpStatus": status,
                "errorCategory": model_http_category(exc),
            },
        )
    return (
        "model_request_failed",
        False,
        {"failureType": "transport_or_provider_error", "errorCategory": "unknown"},
    )


def model_http_category(exc: ModelHTTPError | APIStatusError) -> str:
    # Exact structured identifiers only: provider messages may echo credentials.
    body = exc.body
    error = body.get("error", body) if isinstance(body, dict) else {}
    identifiers = {
        error.get(key)
        for key in ("code", "type")
        if isinstance(error, dict) and isinstance(error.get(key), str)
    }
    if identifiers & {
        "insufficient_quota",
        "insufficient_user_quota",
        "quota_exceeded",
        "billing_hard_limit_reached",
        "credit_balance_too_low",
    }:
        return "quota"
    if exc.status_code in {401, 403} or identifiers & {"invalid_api_key", "authentication_error"}:
        return "authentication"
    if exc.status_code == 429 or identifiers & {"rate_limit_exceeded"}:
        return "rate_limit"
    if identifiers & {"model_not_found", "model_not_available", "unsupported_model"}:
        return "model"
    if identifiers & {
        "context_length_exceeded",
        "invalid_prompt",
        "invalid_request_error",
        "invalid_value",
        "unsupported_parameter",
    }:
        return "input"
    return "unknown"
