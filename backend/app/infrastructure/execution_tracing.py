"""Metadata-only OTel spans and propagation for the durable execution boundary."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagators.textmap import Getter, Setter, default_getter, default_setter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.util._decorator import _agnosticcontextmanager
from opentelemetry.util.types import Attributes, AttributeValue
from temporalio.contrib.opentelemetry import TracingInterceptor, TracingWorkflowInboundInterceptor
from temporalio.worker import WorkflowInboundInterceptor, WorkflowInterceptorClassInput

_IDENTITIES = frozenset(
    {
        "temporalWorkflowID",
        "temporalRunID",
        "temporalActivityID",
        "temporalActivityType",
        "temporalUpdateID",
        "signaldeck.run_id",
        "signaldeck.node_id",
        "signaldeck.invocation_id",
        "signaldeck.operation_id",
        "signaldeck.tool_id",
        "signaldeck.plugin_id",
    }
)


def _identities(attributes: Attributes) -> dict[str, AttributeValue]:
    return {key: value for key, value in (attributes or {}).items() if key in _IDENTITIES}


class TraceParentPropagator(TraceContextTextMapPropagator):
    """Retain W3C identity, excluding arbitrary baggage and vendor tracestate."""

    def inject(
        self,
        carrier: Any,
        context: Context | None = None,
        setter: Setter[Any] = default_setter,
    ) -> None:
        headers: dict[str, str] = {}
        super().inject(headers, context)
        if "traceparent" in headers:
            setter.set(carrier, "traceparent", headers["traceparent"])

    def extract(
        self,
        carrier: Any,
        context: Context | None = None,
        getter: Getter[Any] = default_getter,
    ) -> Context:
        return super().extract({"traceparent": getter.get(carrier, "traceparent") or []}, context)

    @property
    def fields(self) -> set[str]:
        return {"traceparent"}


class _MetadataSpan(trace.Span):
    def __init__(self, span: trace.Span):
        self._span = span

    def end(self, end_time: int | None = None) -> None:
        self._span.end(end_time)

    def get_span_context(self) -> trace.SpanContext:
        return self._span.get_span_context()

    def is_recording(self) -> bool:
        return self._span.is_recording()

    def set_attribute(self, key: str, value: AttributeValue) -> None:
        if key in _IDENTITIES:
            self._span.set_attribute(key, value)

    def set_attributes(self, attributes: Mapping[str, AttributeValue]) -> None:
        self._span.set_attributes(_identities(attributes))

    def set_status(
        self, status: trace.Status | trace.StatusCode, description: str | None = None
    ) -> None:
        self._span.set_status(
            trace.Status(status.status_code if isinstance(status, trace.Status) else status)
        )

    def record_exception(
        self,
        exception: BaseException,
        attributes: Attributes = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        # SDK exceptions can include request bodies, headers and credentials.
        self._span.set_status(trace.Status(trace.StatusCode.ERROR))

    def add_event(
        self, name: str, attributes: Attributes = None, timestamp: int | None = None
    ) -> None:
        pass

    def update_name(self, name: str) -> None:
        pass


class MetadataTracer(trace.Tracer):
    """Keep native Temporal tracing without its exception text/stack capture.

    Call names are static registered SDK operations. Inputs, outputs and error
    details belong to the platform's separately protected evidence adapters.
    """

    def __init__(self, tracer: trace.Tracer):
        self._tracer = tracer

    def start_span(
        self,
        name: str,
        context: Context | None = None,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
        attributes: Attributes = None,
        links: Sequence[trace.Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> trace.Span:
        return _MetadataSpan(
            self._tracer.start_span(
                name,
                context,
                kind,
                _identities(attributes),
                [trace.Link(link.context) for link in links or ()],
                start_time,
                record_exception=False,
                set_status_on_exception=False,
            )
        )

    @_agnosticcontextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Context | None = None,
        kind: trace.SpanKind = trace.SpanKind.INTERNAL,
        attributes: Attributes = None,
        links: Sequence[trace.Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True,
    ) -> Iterator[trace.Span]:
        with trace.use_span(
            self.start_span(name, context, kind, attributes, links, start_time),
            end_on_exit=end_on_exit,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except BaseException:
                span.set_status(trace.StatusCode.ERROR)
                raise


def execution_tracer() -> MetadataTracer:
    return MetadataTracer(trace.get_tracer("signaldeck.execution"))


class _TraceParentWorkflowInterceptor(TracingWorkflowInboundInterceptor):
    def __init__(self, next: WorkflowInboundInterceptor) -> None:
        super().__init__(next)
        self.text_map_propagator = TraceParentPropagator()


class ExecutionTracingInterceptor(TracingInterceptor):
    def __init__(self, tracer: trace.Tracer | None = None) -> None:
        # Scheduled starts have no client parent. Native completed workflow spans
        # are replay-safe markers, not elapsed-duration or product evidence spans.
        super().__init__(
            MetadataTracer(tracer) if tracer is not None else execution_tracer(),
            always_create_workflow_spans=True,
        )
        self.text_map_propagator = TraceParentPropagator()

    def workflow_interceptor_class(
        self, input: WorkflowInterceptorClassInput
    ) -> type[TracingWorkflowInboundInterceptor]:
        super().workflow_interceptor_class(input)
        return _TraceParentWorkflowInterceptor
