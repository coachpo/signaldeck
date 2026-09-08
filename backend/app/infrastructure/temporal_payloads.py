"""Content-addressed Temporal payloads and explicit runtime value references."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from temporalio.api.common.v1 import Payload
from temporalio.converter import DataConverter, PayloadCodec

from app.domain.tool_contracts import ArtifactRef
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.temporal_ports import ArtifactValues


class ArtifactPayloadCodec(PayloadCodec):
    def __init__(self, artifacts: ArtifactStore):
        self.artifacts = artifacts

    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        result = []
        for payload in payloads:
            content = payload.SerializeToString(deterministic=True)
            if len(content) <= self.artifacts.inline_threshold:
                result.append(payload)
                continue
            ref = await asyncio.to_thread(
                self.artifacts.put, content, "application/x-protobuf-temporal-payload"
            )
            result.append(
                Payload(
                    metadata={"encoding": b"binary/signaldeck-artifact-v1"},
                    data=ref.model_dump_json(by_alias=True).encode(),
                )
            )
        return result

    async def decode(self, payloads: Sequence[Payload]) -> list[Payload]:
        result = []
        for payload in payloads:
            if payload.metadata.get("encoding") != b"binary/signaldeck-artifact-v1":
                result.append(payload)
                continue
            ref = ArtifactRef.model_validate_json(payload.data)
            content = await asyncio.to_thread(self.artifacts.read, ref)
            result.append(Payload.FromString(content))
        return result


def create_data_converter(artifacts: ArtifactStore) -> DataConverter:
    return DataConverter(payload_codec=ArtifactPayloadCodec(artifacts))


def pack_value(artifacts: ArtifactValues, value: Any) -> Any:
    stored = artifacts.store_json(value)
    if isinstance(stored, ArtifactRef):
        return {"$artifact": stored.model_dump(mode="json", by_alias=True)}
    return stored


def unpack_value(artifacts: ArtifactValues, value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"$artifact"}:
        return artifacts.read_json(ArtifactRef.model_validate(value["$artifact"]))
    # Clone inline values so mappings cannot mutate confirmed output dictionaries.
    return json.loads(json.dumps(value))
