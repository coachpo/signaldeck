"""Stable Run identities translated into Temporal start and cancel operations."""

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.application.dispatch import AdmissionRejected
from app.domain.execution import ResolvedRunSpec
from app.domain.tool_contracts import canonical_digest
from app.infrastructure.core_artifacts import CoreArtifactError, task_queue


class CoreArtifactVerifier(Protocol):
    def verify(self, digest: str) -> Any: ...


class TemporalRunEngine:
    def __init__(self, client: Client, core_artifacts: CoreArtifactVerifier | None = None) -> None:
        self.client, self.core_artifacts = client, core_artifacts

    async def _exists(self, run_id: str, spec_hash: str) -> bool:
        try:
            description = await self.client.get_workflow_handle(run_id).describe(
                rpc_timeout=timedelta(seconds=10)
            )
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                return False
            raise
        if await description.memo_value("signaldeckSpecHash", None) != spec_hash:
            raise AdmissionRejected("engine_identity_conflict")
        return True

    async def start(self, spec: ResolvedRunSpec) -> None:
        payload = spec.model_dump(mode="json", by_alias=True)
        spec_hash = canonical_digest(payload)
        if await self._exists(spec.run_id, spec_hash):
            return
        try:
            if self.core_artifacts is None:
                raise CoreArtifactError("Core artifact verifier is unavailable")
            self.core_artifacts.verify(spec.core_artifact)
        except CoreArtifactError:
            raise AdmissionRejected("core_artifact_unavailable") from None
        remaining = (spec.deadline - datetime.now(UTC)).total_seconds()
        try:
            await self.client.start_workflow(
                "SignalDeckWorkflow",
                payload,
                id=spec.run_id,
                task_queue=task_queue(spec.core_artifact),
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                execution_timeout=timedelta(seconds=max(remaining, 0) + 60),
                memo={
                    "signaldeckSpecHash": spec_hash,
                    "signaldeckCoreArtifact": spec.core_artifact,
                },
                rpc_timeout=timedelta(seconds=10),
            )
        except WorkflowAlreadyStartedError:
            # Delivery can be repeated after an accepted response was lost.
            await self._exists(spec.run_id, spec_hash)

    async def cancel(self, run_id: str) -> None:
        handle = self.client.get_workflow_handle(run_id)
        try:
            await handle.cancel()
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                raise
            description = await handle.describe()
            if description.status == WorkflowExecutionStatus.RUNNING:
                raise

    async def result(self, run_id: str) -> Any:
        return await self.client.get_workflow_handle(run_id).result()
