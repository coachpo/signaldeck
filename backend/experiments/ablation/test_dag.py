"""Ablate only Workflow maxParallelNodes on the real Temporal DAG runtime."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from time import perf_counter

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.testing import WorkflowEnvironment

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_payloads import create_data_converter
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker
from tests.test_durable_runtime_support import (
    CORE,
    make_spec,
    mapping,
    recompile_spec,
    tool_server,
)

DELAY_SECONDS = 0.35


def _workload(shape):
    nodes, expected = {}, {}
    for index in range(4):
        name = f"step_{index}"
        previous = f"step_{index - 1}"
        chained = shape == "chain" and index > 0
        value = {"ref": f"nodes.{previous}.output.value"} if chained else {"value": 1}
        nodes[name] = {
            "uses": "shared",
            "inputMapping": mapping(name, value, DELAY_SECONDS),
        }
        expected[name] = {
            "value": index + 2 if shape == "chain" else 2,
            "delay": DELAY_SECONDS,
            "tag": name,
        }
    if shape == "branches":
        nodes["join"] = {
            "uses": "shared",
            "dependsOn": list(nodes),
            "inputMapping": mapping("join", {"ref": "nodes.step_0.output.value"}),
        }
        expected["join"] = {"value": 3, "delay": 0, "tag": "join"}
    return nodes, expected


def _event_metrics(events, shape, parallelism):
    times = {(event, tag): at for event, tag, at in events}
    active, peak = 0, 0
    for event, _, _ in events:
        assert event in {"start", "end"}, events
        active += 1 if event == "start" else -1
        peak = max(peak, active)
    assert active == 0
    if shape == "branches":
        dependency_gaps = [
            times["start", "join"] - times["end", f"step_{index}"] for index in range(4)
        ]
        # Node admission is a cap; the unchanged resource limiter can stagger tool I/O.
        if parallelism > 1:
            assert 1 < peak <= parallelism, events
        else:
            assert peak == 1, events
    else:
        dependency_gaps = [
            times["start", f"step_{index}"] - times["end", f"step_{index - 1}"]
            for index in range(1, 4)
        ]
        assert peak == 1, events
    assert min(dependency_gaps) > 0, events
    return {
        "peak_active": peak,
        "tool_calls": sum(event == "start" for event, _, _ in events),
        "min_dependency_gap_ms": min(dependency_gaps) * 1000,
    }


@pytest.mark.parametrize("shape", ["branches", "chain"])
def test_dag_parallelism(session_factory, tmp_path, variant, sample, record, shape):
    async def scenario():
        artifacts = ArtifactStore(tmp_path / "artifacts", inline_threshold=1024)
        store = PlatformStore(session_factory, artifacts=artifacts)
        store.initialize()
        events = []
        cli = os.environ.get("TEMPORAL_CLI", "/tmp/sd-temporal-bin/temporal")
        assert Path(cli).is_file(), "TEMPORAL_CLI must point at pinned Temporal CLI 1.8.3"
        temporal_version = subprocess.run(
            [cli, "--version"], check=True, capture_output=True, text=True, timeout=10
        ).stdout.strip()
        assert temporal_version.startswith("temporal version 1.8.3 ("), temporal_version
        async with (
            await WorkflowEnvironment.start_local(
                dev_server_existing_path=cli,
                data_converter=create_data_converter(artifacts),
                plugins=[PydanticAIPlugin()],
            ) as environment,
            tool_server(events) as transport,
        ):
            services = TemporalServices(
                store, artifacts, lambda spec: transport, CORE, lambda: None
            )
            worker = await create_worker(environment.client, services, "dag-ablation")
            async with worker:
                nodes, expected = _workload(shape)
                spec = make_spec(nodes, deadline=60)
                parallelism = 4 if variant == "baseline" else 1
                spec.definition["workflows"]["main"]["maxParallelNodes"] = parallelism
                spec = recompile_spec(spec)
                store.create_run(spec, spec.run_id)
                started = perf_counter()
                result = await environment.client.execute_workflow(
                    "SignalDeckWorkflow",
                    spec.model_dump(mode="json", by_alias=True),
                    id=spec.run_id,
                    task_queue="dag-ablation",
                )
                elapsed_ms = (perf_counter() - started) * 1000
                detail = store.get_run(spec.run_id)
                assert result["status"] == detail.status == "succeeded", detail
                node_evidence = [item for item in detail.evidence if item.kind == "node"]
                assert len(node_evidence) == len(expected)
                assert all(item.status == "succeeded" for item in node_evidence)
                assert {item.node_id: item.output for item in node_evidence} == expected
                assert detail.output == expected[list(nodes)[-1]]
                assert all(item.status == "succeeded" for item in detail.evidence)
                metrics = _event_metrics(events, shape, parallelism)
                assert metrics["tool_calls"] == len(nodes)
                record(
                    {
                        "scenario": f"dag_{shape}",
                        "mechanism": "dag_parallelism",
                        "variant": variant,
                        "sample": sample,
                        "metrics": {
                            **metrics,
                            "elapsed_ms": elapsed_ms,
                            "successes": len(node_evidence),
                            "max_parallel_nodes": parallelism,
                            "controlled_tool_delay_ms": DELAY_SECONDS * 1000,
                        },
                        "temporal_version": temporal_version,
                        "events": [
                            {
                                "event": event,
                                "tag": tag,
                                "offset_ms": (at - events[0][2]) * 1000,
                            }
                            for event, tag, at in events
                        ],
                        "output": detail.output,
                    }
                )

    asyncio.run(scenario())
