"""Execution tracing is safe metadata; PostgreSQL remains the product evidence source."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from opentelemetry import baggage, context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from temporalio.testing import WorkflowEnvironment

from app.domain.tool_contracts import ToolInvocationContext
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.execution_tracing import (
    ExecutionTracingInterceptor,
    MetadataTracer,
    TraceParentPropagator,
)
from app.infrastructure.mcp_transport import McpToolTransport
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import (
    CORE,
    make_release,
    make_spec,
    mapping,
    model_server,
    tool_server,
)


def test_production_client_registers_replay_safe_execution_tracing(tmp_path, monkeypatch):
    from app.infrastructure.temporal_client import connect_client

    captured = {}
    client = object()

    async def connect(address, **kwargs):
        captured.update(address=address, **kwargs)
        return client

    monkeypatch.setattr("app.infrastructure.temporal_client.Client.connect", connect)
    assert asyncio.run(connect_client("local:7233", ArtifactStore(tmp_path))) is client
    assert isinstance(captured["interceptors"][0], ExecutionTracingInterceptor)
    assert captured["plugins"]


def test_trace_metadata_excludes_exception_payload_and_baggage():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = MetadataTracer(provider.get_tracer("test"))
    sentinel = "sentinel-credential-must-not-be-traced"
    token = context.attach(baggage.set_baggage("authorization", sentinel))
    try:
        with (
            pytest.raises(ValueError, match=sentinel),
            tracer.start_as_current_span(
                "RunActivity:probe",
                attributes={"temporalWorkflowID": "run-1", "input": sentinel},
            ) as span,
        ):
            span.set_attribute("output", sentinel)
            span.set_attributes({"authorization": sentinel})
            span.add_event(sentinel, {"body": sentinel})
            span.update_name(sentinel)
            span.record_exception(ValueError(sentinel))
            span.set_status(trace.Status(trace.StatusCode.ERROR, sentinel))
            carrier = {}
            TraceParentPropagator().inject(carrier)
            assert set(carrier) == {"traceparent"}
            extracted = TraceParentPropagator().extract(
                {**carrier, "baggage": f"key={sentinel}", "tracestate": f"vendor={sentinel}"}
            )
            assert not trace.get_current_span(extracted).get_span_context().trace_state
            assert not baggage.get_all(extracted)
            raise ValueError(sentinel)
    finally:
        context.detach(token)
    (recorded,) = exporter.get_finished_spans()
    assert recorded.attributes == {"temporalWorkflowID": "run-1"}
    assert recorded.status.status_code == trace.StatusCode.ERROR
    assert not recorded.status.description
    assert not recorded.events
    assert sentinel not in recorded.to_json()
    provider.shutdown()


@pytest.mark.parametrize("header", ["traceparent", "TraceState", "Baggage"])
def test_resource_headers_cannot_override_trace_identity(header):
    class Resolver:
        async def resolve(self, plugin_id, resource_refs):
            return {header: "sentinel-credential"}

    def request(_):
        pytest.fail("Invalid resource headers must fail before network I/O")

    release = make_release()
    invocation = ToolInvocationContext(
        run_id="run-1",
        node_id="a",
        invocation_id="agent-1",
        operation_id="operation-1",
        deadline=datetime.now(UTC) + timedelta(seconds=10),
        tool_grants=(release.tools[0].tool_id,),
    )
    result = asyncio.run(
        McpToolTransport(Resolver(), httpx.MockTransport(request)).execute(
            release, release.tools[0], {}, invocation
        )
    )
    assert result.status == "failed"
    assert result.code == "invalid_resource_headers"
    assert "sentinel" not in result.model_dump_json()


def test_real_workflow_child_activity_mcp_trace_and_independent_evidence(
    database_url, tmp_path, monkeypatch
):
    async def scenario():
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test-runtime")
        monkeypatch.setattr(
            "app.infrastructure.mcp_transport.execution_tracer", lambda: MetadataTracer(tracer)
        )
        engine = create_engine(database_url)
        artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=1024)
        store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
        store.initialize()
        secret = "sentinel-model-credential-never-in-trace"
        store.save_resource("model", "model", {}, {"apiKey": secret})
        cli = os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
        assert Path(cli).is_file()
        events, calls, sent_headers = [], [], []
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=cli,
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
                interceptors=[ExecutionTracingInterceptor(tracer)],
            ) as environment,
            tool_server(events) as transport,
            model_server(calls) as url,
        ):
            original_transport = transport.http_transport

            class CaptureHeaders(httpx.AsyncBaseTransport):
                async def handle_async_request(self, request):
                    sent_headers.append(dict(request.headers))
                    return await original_transport.handle_async_request(request)

            transport.http_transport = CaptureHeaders()
            services = TemporalServices(
                store, artifacts, lambda spec: transport, CORE, lambda: None
            )
            async with await create_worker(environment.client, services, "tracing-test"):
                spec = make_spec(
                    {
                        "a": {
                            "uses": "shared",
                            "inputMapping": mapping("private-input", {"value": 1}),
                        }
                    },
                    kind="model",
                    model_url=url,
                    model_store=store,
                )
                store.create_run(spec, spec.run_id)
                result = await environment.client.execute_workflow(
                    "SignalDeckWorkflow",
                    spec.model_dump(mode="json", by_alias=True),
                    id=spec.run_id,
                    task_queue="tracing-test",
                )
                assert result["status"] == "succeeded"
                spans = exporter.get_finished_spans()
                names = {span.name for span in spans}
                assert "StartWorkflow:SignalDeckWorkflow" in names
                assert "RunWorkflow:SignalDeckWorkflow" in names
                assert "StartChildWorkflow:AgentWorkflow" in names
                assert "RunWorkflow:AgentWorkflow" in names
                assert any(name.startswith("RunActivity:") for name in names)
                assert "mcp.call_tool" in names
                assert len({span.context.trace_id for span in spans}) == 1
                mcp_span = next(span for span in spans if span.name == "mcp.call_tool")
                assert mcp_span.attributes["signaldeck.run_id"] == spec.run_id
                assert any(
                    span.context.span_id == mcp_span.parent.span_id
                    and span.name.startswith("RunActivity:")
                    for span in spans
                )
                expected_trace_id = format(mcp_span.context.trace_id, "032x")
                assert sent_headers and all(
                    headers["traceparent"].split("-")[1] == expected_trace_id
                    and "baggage" not in headers
                    and "tracestate" not in headers
                    for headers in sent_headers
                )
                trace_json = json.dumps([span.to_json() for span in spans])
                assert secret not in trace_json
                assert "private-input" not in trace_json

                # A disabled exporter cannot participate in execution or history reads.
                provider.shutdown()
                before = store.get_run(spec.run_id).model_dump_json()
                assert {item.kind for item in store.get_run(spec.run_id).evidence} == {
                    "node",
                    "agent",
                    "model",
                    "tool",
                    "attempt",
                }
                assert secret not in before
                fresh = make_spec()
                store.create_run(fresh, fresh.run_id)
                result = await environment.client.execute_workflow(
                    "SignalDeckWorkflow",
                    fresh.model_dump(mode="json", by_alias=True),
                    id=fresh.run_id,
                    task_queue="tracing-test",
                )
                assert result["status"] == "succeeded"
                assert store.get_run(spec.run_id).model_dump_json() == before
                assert {item.kind for item in store.get_run(fresh.run_id).evidence} == {
                    "node",
                    "agent",
                    "tool",
                    "attempt",
                }
        engine.dispose()

    asyncio.run(scenario())
