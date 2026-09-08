"""Keep the isolated engine alive independently of the fault-injected workers."""

import os
import signal
import time
from pathlib import Path

from hatchet_sdk import ClientConfig, EmbeddedHatchetConfig, Hatchet


def stop(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    root = Path(os.environ["SD_HATCHET_STATE"])
    client = Path(os.environ["SD_HATCHET_CLIENT"])
    hatchet = Hatchet.from_embedded(
        ClientConfig(
            embedded=EmbeddedHatchetConfig(
                version="v0.105.16",
                postgres_data_dir=str(root / "postgres"),
                grpc_port=int(os.environ.get("SD_HATCHET_GRPC_PORT", "17079")),
                api_port=int(os.environ.get("SD_HATCHET_API_PORT", "28249")),
            )
        )
    )
    try:
        fd = os.open(client, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(
                hatchet.config.model_dump_json(
                    include={"token", "host_port", "server_url", "tls_config"}
                )
            )
        print("ENGINE_READY", flush=True)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        hatchet.stop_embedded()
        client.unlink(missing_ok=True)
