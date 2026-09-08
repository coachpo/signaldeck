"""The local provider speaks the same required response contract as OpenAI."""

import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic_ai.messages import ModelRequest, TextPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from tests.fake_openai_provider import run_fake_openai_provider


@pytest.mark.parametrize("model_class", [OpenAIChatModel, OpenAIResponsesModel])
def test_prompted_dynamic_output_through_real_sdk(
    model_class: type[OpenAIChatModel] | type[OpenAIResponsesModel],
) -> None:
    asyncio.run(_assert_output(model_class))


async def _assert_output(
    model_class: type[OpenAIChatModel] | type[OpenAIResponsesModel],
) -> None:
    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}, "flag": {"type": "boolean"}},
        "required": ["count", "flag"],
    }
    with run_fake_openai_provider(base_path="/v1") as base_url:
        async with httpx2.AsyncClient() as http:
            provider = OpenAIProvider(
                openai_client=AsyncOpenAI(base_url=base_url, api_key="fake-only", http_client=http)
            )
            model = model_class("fake-test", provider=provider)
            response = await model.request(
                [ModelRequest(parts=[UserPromptPart(json.dumps({"outputContract": schema}))])],
                None,
                ModelRequestParameters(),
            )
    assert isinstance(response.parts[0], TextPart)
    assert json.loads(response.parts[0].content) == {"count": 1, "flag": True}


def test_fake_provider_hold_has_an_observable_release_boundary() -> None:
    asyncio.run(_assert_hold_boundary())


async def _assert_hold_boundary() -> None:
    with run_fake_openai_provider(base_path="/v1") as base_url:
        control = base_url.removesuffix("/v1") + "/control"
        async with httpx2.AsyncClient() as http:
            await http.post(control + "/hold/held-fixture")
            pending = asyncio.create_task(
                http.post(
                    base_url + "/chat/completions",
                    json={"model": "held-fixture", "messages": []},
                )
            )
            try:
                async with asyncio.timeout(5):
                    while (await http.get(control + "/state/held-fixture")).json()["entered"] != 1:
                        pass
                assert not pending.done()
            finally:
                await http.post(control + "/release/held-fixture")
            response = await pending
            assert response.status_code == 200
            assert response.json()["choices"][0]["message"]["role"] == "assistant"
