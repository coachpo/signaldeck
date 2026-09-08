"""Temporal terminal observation without execution lifecycle mutations."""

from datetime import timedelta

from temporalio.client import Client, WorkflowExecutionStatus

from app.application.execution_projection import EngineTerminalFact


class TemporalExecutionObserver:
    def __init__(self, client: Client, observation_timeout: float = 5):
        self.client = client
        self.rpc_timeout = timedelta(seconds=observation_timeout)

    async def terminal_fact(self, run_id: str) -> EngineTerminalFact | None:
        handle = self.client.get_workflow_handle(run_id)
        description = await handle.describe(rpc_timeout=self.rpc_timeout)
        if description.close_time is None:
            return None
        status = description.status
        if status == WorkflowExecutionStatus.COMPLETED:
            result = await handle.result(follow_runs=False, rpc_timeout=self.rpc_timeout)
            if not isinstance(result, dict) or result.get("status") not in {
                "succeeded",
                "failed",
                "cancelled",
            }:
                raise ValueError("Execution result contract is unavailable")
            return EngineTerminalFact(
                status=result["status"],
                finished_at=description.close_time,
                output=result.get("output"),
                error_code=result.get("errorCode"),
            )
        if status == WorkflowExecutionStatus.TIMED_OUT:
            return EngineTerminalFact(
                status="failed",
                finished_at=description.close_time,
                error_code="engine_execution_timed_out",
                interrupted_status="timed_out",
            )
        if status == WorkflowExecutionStatus.CANCELED:
            return EngineTerminalFact(
                status="cancelled",
                finished_at=description.close_time,
                error_code="engine_execution_cancelled",
                interrupted_status="cancelled",
            )
        if status in {WorkflowExecutionStatus.FAILED, WorkflowExecutionStatus.TERMINATED}:
            code = (
                "engine_execution_failed"
                if status == WorkflowExecutionStatus.FAILED
                else "engine_execution_terminated"
            )
            return EngineTerminalFact(
                status="failed", finished_at=description.close_time, error_code=code
            )
        return None
