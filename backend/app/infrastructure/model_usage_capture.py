"""Capture only explicitly reported token counters before SDK defaulting."""

import json
from typing import Literal

import httpx2


def token_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


class ReportedModelUsage:
    def __init__(self, api_style: Literal["chat_completions", "responses"]):
        self.api_style = api_style
        self.value: dict[str, int | None] = {"inputTokens": None, "outputTokens": None}

    async def observe(self, response: httpx2.Response) -> None:
        if not response.is_success:
            return
        await response.aread()
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        usage = body.get("usage") if isinstance(body, dict) else None
        if not isinstance(usage, dict):
            return
        input_key, output_key = (
            ("prompt_tokens", "completion_tokens")
            if self.api_style == "chat_completions"
            else ("input_tokens", "output_tokens")
        )
        self.value = {
            "inputTokens": token_count(usage.get(input_key)),
            "outputTokens": token_count(usage.get(output_key)),
        }
