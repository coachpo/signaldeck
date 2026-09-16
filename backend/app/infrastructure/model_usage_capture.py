"""Capture only explicitly reported token counters before SDK defaulting."""

import json
from typing import Literal

import httpx2
from openai.types.chat import ChatCompletion
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.openai import OpenAIChatModel


def token_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


class ModelOutputLimitExceeded(Exception):
    def __init__(self, usage: dict[str, int | None], limit: int, finish_reason: str | None):
        super().__init__("model_output_limit_exceeded")
        self.usage, self.limit, self.finish_reason = usage, limit, finish_reason


class ModelBudgetFailure(Exception):
    def __init__(self, code: str, usage: dict[str, int | None], finish_reason: str | None):
        super().__init__(code)
        self.code, self.usage, self.finish_reason = code, usage, finish_reason


class ModelResponseFailure(Exception):
    def __init__(self, cause: Exception, usage: dict[str, int | None], finish_reason: str | None):
        super().__init__("model_response_failed")
        self.cause, self.usage, self.finish_reason = cause, usage, finish_reason


class ReportedModelUsage:
    def __init__(
        self,
        api_style: Literal["chat_completions", "responses"],
        output_limit: int | None = None,
        require_usage: bool = False,
    ):
        self.api_style = api_style
        self.output_limit = output_limit
        self.require_usage = require_usage
        self.observed = False
        self.finish_reason: str | None = None
        self.value: dict[str, int | None] = {"inputTokens": None, "outputTokens": None}

    async def observe(self, response: httpx2.Response) -> None:
        if not response.is_success:
            return
        self.observed = True
        await response.aread()
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(body, dict):
            return
        usage = body.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        input_key, output_key = (
            ("prompt_tokens", "completion_tokens")
            if self.api_style == "chat_completions"
            else ("input_tokens", "output_tokens")
        )
        self.value = {
            "inputTokens": token_count(usage.get(input_key)),
            "outputTokens": token_count(usage.get(output_key)),
        }
        # Keep only counters and a closed finish reason, never raw text.
        choices = body.get("choices")
        reason = (
            choices[0].get("finish_reason")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else None
        )
        if not isinstance(reason, str) or reason not in {
            "stop",
            "length",
            "tool_calls",
            "content_filter",
            "function_call",
        }:
            reason = None
        if self.api_style == "responses":
            details = body.get("incomplete_details")
            if isinstance(details, dict) and details.get("reason") == "max_output_tokens":
                reason = "length"
            elif body.get("status") == "completed":
                reason = "stop"
        self.finish_reason = reason

    def check_limit(self) -> None:
        output_tokens = self.value["outputTokens"]
        if (
            self.output_limit is not None
            and output_tokens is not None
            and output_tokens > self.output_limit
        ):
            raise ModelOutputLimitExceeded(self.value, self.output_limit, self.finish_reason)

        if self.finish_reason == "length":
            raise ModelBudgetFailure("model_output_truncated", self.value, self.finish_reason)
        if self.observed and (
            (self.require_usage and any(v is None for v in self.value.values()))
            or (self.output_limit is not None and output_tokens is None)
        ):
            raise ModelBudgetFailure("model_usage_unavailable", self.value, self.finish_reason)


class UsageTolerantChatModel(OpenAIChatModel):
    def _process_response(self, response: ChatCompletion | str) -> ModelResponse:
        # The Chat SDK requires every usage counter whenever usage is present.
        # Partial accounting is valid for an output-only budget. Keep unknowns
        # in ReportedModelUsage; SDK counters are only internal loop arithmetic.
        if isinstance(response, ChatCompletion) and response.usage is not None:
            raw = response.usage.model_dump()
            if any(
                token_count(raw.get(key)) is None
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            ):
                result = super()._process_response(response.model_copy(update={"usage": None}))
                result.usage.input_tokens = token_count(raw.get("prompt_tokens")) or 0
                result.usage.output_tokens = token_count(raw.get("completion_tokens")) or 0
                return result
        return super()._process_response(response)
