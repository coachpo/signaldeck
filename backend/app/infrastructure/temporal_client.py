"""Temporal client with the same durable serialization as execution workers."""

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.execution_tracing import ExecutionTracingInterceptor
from app.infrastructure.temporal_payloads import create_data_converter


async def connect_client(address: str, artifacts: ArtifactStore) -> Client:
    return await Client.connect(
        address,
        data_converter=create_data_converter(artifacts),
        interceptors=[ExecutionTracingInterceptor()],
        plugins=[PydanticAIPlugin()],
    )
