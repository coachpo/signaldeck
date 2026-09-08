"""Small value-based I/O ports consumed by durable runtime adapters."""

from collections.abc import Callable
from typing import Any, Protocol

from app.domain.execution import ExecutionEvidence, RunStatus
from app.domain.tool_contracts import ArtifactRef, ToolInvocationContext, ToolResult


class ArtifactValues(Protocol):
    def store_json(self, value: Any) -> Any | ArtifactRef: ...

    def read_json(self, ref: ArtifactRef) -> Any: ...


class ModelEvidence(Protocol):
    def get_evidence(self, evidence_id: str) -> ExecutionEvidence | None: ...

    def record_evidence(self, evidence: ExecutionEvidence) -> None: ...

    def record_evidence_batch(self, evidence: list[ExecutionEvidence]) -> None: ...


class ExecutionProjection(Protocol):
    def record_evidence(self, evidence: ExecutionEvidence) -> None: ...

    def project_run(
        self, run_id: str, status: RunStatus, output: Any = None, error_code: str | None = None
    ) -> None: ...


class ToolInvoker(Protocol):
    async def __call__(
        self,
        bindings: dict[str, Any],
        tool_id: str,
        arguments: dict[str, Any],
        context: ToolInvocationContext,
    ) -> ToolResult: ...


BoundCredentialReader = Callable[[str, str], dict[str, Any]]
