"""Read-only reconciliation of execution-engine terminal facts into query projections."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from app.domain.execution import RunSummary


@dataclass(frozen=True)
class EngineTerminalFact:
    status: Literal["succeeded", "failed", "cancelled"]
    finished_at: datetime
    error_code: str | None = None
    output: Any = None
    interrupted_status: Literal["failed", "cancelled", "timed_out"] = "failed"


class TerminalObserver(Protocol):
    async def terminal_fact(self, run_id: str) -> EngineTerminalFact | None: ...


class TerminalProjectionStore(Protocol):
    def list_unfinished_runs(self) -> list[RunSummary]: ...

    def project_engine_terminal(self, run_id: str, fact: EngineTerminalFact) -> bool: ...


class ExecutionProjector:
    """Observation never issues start, retry or cancel commands."""

    def __init__(self, store: TerminalProjectionStore, observer: TerminalObserver):
        self.store = store
        self.observer = observer

    async def project_once(self) -> dict[str, int]:
        counts = {"examined": 0, "projected": 0, "unavailable": 0}
        runs = await asyncio.to_thread(self.store.list_unfinished_runs)
        for run in runs:
            counts["examined"] += 1
            try:
                fact = await self.observer.terminal_fact(run.id)
                if fact is not None:
                    changed = await asyncio.to_thread(
                        self.store.project_engine_terminal, run.id, fact
                    )
                    counts["projected"] += int(changed)
            except Exception:
                # Observation failure is no evidence that execution has stopped.
                counts["unavailable"] += 1
        return counts
