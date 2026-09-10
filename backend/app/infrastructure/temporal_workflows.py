"""Temporal-owned DAG scheduling from a frozen compiled Workflow Package."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, cast

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.infrastructure.temporal_agent import AgentWorkflow, io
    from app.infrastructure.temporal_cancellation import await_cancel_once
    from app.infrastructure.temporal_failures import failure_code


@workflow.defn
class SignalDeckWorkflow:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.stop_reason: str | None = None

    @workflow.run
    async def run(self, spec: dict[str, Any]) -> dict[str, Any]:
        self.spec = spec
        self.definition = spec["definition"]["workflows"][spec["workflowKey"]]
        self.dependencies = spec["plan"]["dependencies"]
        self.pending = list(spec["plan"]["nodeOrder"])
        self.active: dict[str, asyncio.Task] = {}
        status, error = "succeeded", None
        try:
            await io("prepare_run", spec)
            remaining = (datetime.fromisoformat(spec["deadline"]) - workflow.now()).total_seconds()
            if remaining <= 0:
                raise TimeoutError
            async with asyncio.timeout(remaining):
                await self._schedule()
            if any(
                node["status"] in {"failed", "blocked", "timed_out", "cancelled"}
                for node in self.nodes.values()
            ):
                status, error = "failed", "workflow_nodes_failed"
        except TimeoutError:
            status, error, self.stop_reason = "failed", "deadline_exceeded", "timed_out"
        except asyncio.CancelledError:
            status, error, self.stop_reason = "cancelled", "cancelled", "cancelled"
        except Exception as exc:
            status, error, self.stop_reason = (
                "failed",
                failure_code(exc, "workflow_execution_failed"),
                "blocked",
            )
        if self.stop_reason is not None:
            for task in self.active.values():
                task.cancel()
            await asyncio.gather(*self.active.values(), return_exceptions=True)
            for node_id in self.pending:
                await self._terminal(node_id, self.stop_reason, error)
        return cast(
            dict[str, Any],
            await io(
                "finalize_run",
                {
                    "spec": spec,
                    "status": status,
                    "errorCode": error,
                    "nodes": self.nodes,
                },
            ),
        )

    async def _schedule(self) -> None:
        while self.pending or self.active:
            for node_id in list(self.pending):
                if len(self.active) >= self.definition["maxParallelNodes"]:
                    break
                if not all(key in self.nodes for key in self.dependencies[node_id]):
                    continue
                self.pending.remove(node_id)
                node = self.definition["nodes"][node_id]
                if any(
                    self.nodes[key]["status"] not in node["acceptUpstreamStates"]
                    for key in self.dependencies[node_id]
                ):
                    await self._terminal(node_id, "blocked", "upstream_state_rejected")
                    continue
                self.active[node_id] = asyncio.create_task(self._run_node(node_id))
            if not self.active:
                if self.pending:
                    raise RuntimeError("Compiled graph contains unavailable dependencies")
                break
            done, _ = await workflow.wait(self.active.values(), return_when=asyncio.FIRST_COMPLETED)
            for node_id, task in list(self.active.items()):
                if task in done:
                    await task
                    del self.active[node_id]
            if self.definition["failurePolicy"] == "fail_fast" and any(
                value["status"] in {"failed", "timed_out"} for value in self.nodes.values()
            ):
                self.stop_reason = "blocked"
                for task in self.active.values():
                    task.cancel()
                await asyncio.gather(*self.active.values(), return_exceptions=True)
                self.active.clear()
                for node_id in self.pending:
                    await self._terminal(node_id, "blocked", "failure_policy_stopped")
                self.pending.clear()
                break

    async def _terminal(self, node_id: str, status: str, error: str | None = None) -> None:
        self.nodes[node_id] = {"status": status, "errorCode": error}
        await io(
            "project_node",
            {
                "spec": self.spec,
                "nodeId": node_id,
                "status": status,
                "errorCode": error,
            },
            complete_on_cancel=True,
        )

    async def _run_node(self, node_id: str) -> None:
        started = workflow.now().isoformat()
        node_input = None
        child = None
        try:
            prepared = await io(
                "prepare_node", {"spec": self.spec, "nodeId": node_id, "nodes": self.nodes}
            )
            if prepared["status"] != "ready":
                await self._terminal(node_id, prepared["status"], prepared.get("errorCode"))
                return
            node_input = prepared["input"]
            await io(
                "project_node",
                {
                    "spec": self.spec,
                    "nodeId": node_id,
                    "status": "running",
                    "input": node_input,
                    "startedAt": started,
                },
            )
            node = self.definition["nodes"][node_id]
            agent = self.spec["definition"]["agents"][node["uses"]]
            deadline = min(
                datetime.fromisoformat(self.spec["deadline"]),
                workflow.now() + timedelta(seconds=agent["budget"]["deadlineSeconds"]),
            ).isoformat()
            for attempt in range(1, node["maxAttempts"] + 1):
                invocation_id = f"{self.spec['runId']}:{node_id}:agent:{attempt}"
                child = await workflow.start_child_workflow(
                    AgentWorkflow.run,
                    {
                        "runId": self.spec["runId"],
                        "nodeId": node_id,
                        "agent": agent,
                        **self._agent_bindings(agent),
                        "input": node_input,
                        "attempt": attempt,
                        "invocationId": invocation_id,
                        "deadline": deadline,
                        "startedAt": workflow.now().isoformat(),
                    },
                    id=invocation_id,
                    cancellation_type=workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
                )
                result = await await_cancel_once(child)
                if (
                    result["status"] != "failed"
                    or result.get("errorCode") == "model_output_limit_exceeded"
                    or not self._can_restart(agent)
                ):
                    break
            self.nodes[node_id] = result
        except asyncio.CancelledError:
            self.nodes[node_id] = {
                "status": "timed_out" if self.stop_reason == "timed_out" else "cancelled",
                "errorCode": (
                    "deadline_exceeded" if self.stop_reason == "timed_out" else "cancelled"
                ),
            }
        except Exception as exc:
            if self.stop_reason is not None:
                self.nodes[node_id] = {
                    "status": "timed_out" if self.stop_reason == "timed_out" else "cancelled",
                    "errorCode": "cancelled",
                }
            else:
                self.nodes[node_id] = {
                    "status": "failed",
                    "errorCode": failure_code(exc, "node_execution_failed"),
                }
        await io(
            "project_node",
            {
                "spec": self.spec,
                "nodeId": node_id,
                "input": node_input,
                "startedAt": started,
                **self.nodes[node_id],
            },
            complete_on_cancel=True,
        )

    def _can_restart(self, agent: dict[str, Any]) -> bool:
        # A new Agent attempt can choose different calls. Never replay a writer this way.
        effects = {
            tool["toolId"]: tool["effect"]
            for release in self.spec["pluginReleases"]
            for tool in release["tools"]
        }
        return all(effects[tool_id] == "read" for tool_id in agent["tools"])

    def _agent_bindings(self, agent: dict[str, Any]) -> dict[str, Any]:
        owners = {tool_id.rsplit("/", 1)[0] for tool_id in agent["tools"]}
        return {
            "pluginReleases": [
                release for release in self.spec["pluginReleases"] if release["pluginId"] in owners
            ],
            "toolAliases": {
                alias: tool_id
                for alias, tool_id in self.spec["toolAliases"].items()
                if tool_id in agent["tools"]
            },
            "resourceBindings": {
                key: self.spec["resourceBindings"][key] for key in agent["resources"]
            },
            "modelBinding": self.spec["modelBindings"].get(agent["strategy"].get("modelRef")),
        }
