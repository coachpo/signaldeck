"""Deliver committed commands; execution state remains owned by the engine."""

from contextlib import AbstractContextManager
from typing import Protocol

from app.domain.execution import ResolvedRunSpec, RunDetail, StartCommand


class CommandStore(Protocol):
    def pending_commands(self, limit: int = 100) -> list[StartCommand]: ...

    def get_run(self, run_id: str) -> RunDetail | None: ...

    def note_command_attempt(self, command_id: str) -> None: ...

    def acknowledge_command(self, command_id: str) -> None: ...

    def command_delivery(self, command_id: str) -> AbstractContextManager[bool]: ...

    def reject_run_admission(self, command_id: str, error_code: str) -> None: ...

    def command_rejection(self, command_id: str) -> str | None: ...


class AdmissionRejected(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ExecutionEngine(Protocol):
    async def start(self, spec: ResolvedRunSpec) -> None: ...

    async def cancel(self, run_id: str) -> None: ...


class CommandDispatcher:
    def __init__(self, store: CommandStore, engine: ExecutionEngine) -> None:
        self.store = store
        self.engine = engine

    async def dispatch_once(self, limit: int = 100) -> dict[str, int]:
        delivered, failed = 0, 0
        for command in self.store.pending_commands(limit):
            try:
                delivered += int(await self._deliver(command.id, command.run_id, command.kind))
            except AdmissionRejected:
                delivered += 1
            except Exception:
                # Keep the original intent pending. Provider text can contain credentials.
                failed += 1
        return {"delivered": delivered, "failed": failed}

    async def dispatch_start(self, run_id: str) -> None:
        await self._deliver("start:" + run_id, run_id, "start")

    async def _deliver(self, command_id: str, run_id: str, kind: str) -> bool:
        with self.store.command_delivery(command_id) as pending:
            rejection = self.store.command_rejection("start:" + run_id)
            if kind == "start" and rejection:
                raise AdmissionRejected(rejection)
            if not pending:
                return False
            self.store.note_command_attempt(command_id)
            try:
                if kind == "start":
                    run = self.store.get_run(run_id)
                    if run is None:
                        raise LookupError("Run snapshot is unavailable")
                    await self.engine.start(run.spec)
                elif not rejection:
                    await self.engine.cancel(run_id)
                self.store.acknowledge_command(command_id)
                return True
            except AdmissionRejected as exc:
                self.store.reject_run_admission(command_id, exc.code)
                raise
