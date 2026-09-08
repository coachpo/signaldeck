"""Standalone delivery process for atomic launch and schedule configuration intents."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.dispatch import CommandDispatcher
from app.application.execution_projection import ExecutionProjector
from app.core.config import get_settings
from app.core.telemetry import configure_logfire
from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.core_artifacts import CoreArtifactStore
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.schedule_store import ScheduleStore
from app.infrastructure.temporal_client import connect_client
from app.infrastructure.temporal_dispatch import TemporalRunEngine
from app.infrastructure.temporal_projection import TemporalExecutionObserver
from app.infrastructure.temporal_schedules import TemporalScheduleService

logger = logging.getLogger(__name__)


async def deliver_until_stopped(
    dispatcher: CommandDispatcher,
    schedules: TemporalScheduleService,
    stopped: asyncio.Event,
    poll_seconds: float = 1,
    projector: ExecutionProjector | None = None,
) -> None:
    while not stopped.is_set():
        try:
            commands = await dispatcher.dispatch_once()
            if commands["failed"]:
                logger.warning("Delivery remains pending; the original commands will be retried")
        except Exception:
            logger.warning("Delivery storage is unavailable; pending commands are retained")
        try:
            configuration = await schedules.reconcile()
            if configuration["failed"]:
                logger.warning("Schedule configuration delivery remains pending")
        except Exception:
            logger.warning("Schedule configuration storage is unavailable")
        if projector is not None:
            try:
                await projector.project_once()
            except Exception:
                logger.warning("Engine fact projection storage is unavailable")
        try:
            await schedules.project_fires()
        except Exception:
            logger.warning("Schedule fire projection storage is unavailable")
        try:
            await asyncio.wait_for(stopped.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass


async def main() -> None:
    configure_logfire(service_name="signaldeck-dispatcher")
    settings = get_settings()
    database = create_engine(settings.database_url)
    sessions = sessionmaker(database, expire_on_commit=False)
    artifacts = ArtifactStore(Path(settings.artifact_dir))
    store = PlatformStore(sessions, artifacts=artifacts)
    schedule_store = ScheduleStore(sessions)
    store.initialize()
    schedule_store.initialize()
    core = CoreArtifactStore(Path(settings.core_artifact_dir))
    queue = core.task_queue(core.current_digest())
    client = await connect_client(settings.temporal_address, artifacts)
    dispatcher = CommandDispatcher(store, TemporalRunEngine(client, core))
    schedules = TemporalScheduleService(client, schedule_store, queue)
    projector = ExecutionProjector(store, TemporalExecutionObserver(client))
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    try:
        await deliver_until_stopped(dispatcher, schedules, stopped, projector=projector)
    finally:
        database.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
