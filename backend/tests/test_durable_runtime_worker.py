"""Test-owned subprocess for killing a real worker without killing the test host."""

import asyncio
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.artifact_store import ArtifactStore
from app.infrastructure.mcp_transport import EmptySecretResolver, McpToolTransport
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.temporal_client import connect_client
from app.infrastructure.temporal_services import TemporalServices
from app.workers.durable_worker import create_worker


async def main():
    artifacts = ArtifactStore(Path(os.environ["PROBE_ARTIFACTS"]), inline_threshold=1024)
    engine = create_engine(os.environ["PROBE_DATABASE"])
    store = PlatformStore(sessionmaker(engine, expire_on_commit=False), artifacts=artifacts)
    services = TemporalServices(
        store,
        artifacts,
        lambda spec: McpToolTransport(EmptySecretResolver()),
        os.environ["PROBE_CORE"],
        lambda: None,
    )
    client = await connect_client(os.environ["PROBE_ADDRESS"], artifacts)
    async with await create_worker(client, services, "recovery-test"):
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
