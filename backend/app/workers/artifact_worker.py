"""Start the worker code from a retained, verified core closure."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.infrastructure.core_artifacts import CoreArtifactError, CoreArtifactStore, CoreBundle


def _environment_files(root: Path) -> dict[str, str]:
    records = {}
    for path in sorted(root.rglob("*")):
        if path == root / ".core-environment.json":
            continue
        if path.is_symlink():
            target = path.resolve()
            link = os.readlink(path).encode()
            if target.is_dir() and target.is_relative_to(root.resolve()):
                # Linux venvs expose lib64 -> lib; the actual directory's files
                # are already included below. Never follow an external directory.
                records[path.relative_to(root).as_posix()] = hashlib.sha256(
                    b"directory\0" + link
                ).hexdigest()
                continue
            if not target.is_file():
                raise CoreArtifactError("Core environment has an invalid symbolic link")
            records[path.relative_to(root).as_posix()] = hashlib.sha256(
                link + b"\0" + path.read_bytes()
            ).hexdigest()
        elif path.is_file():
            records[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return records


def _safe_environment() -> dict[str, str]:
    env = os.environ.copy()
    # Execution must not resolve app modules or Python libraries from the current
    # checkout, a caller's editable install, or a user startup hook.
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "UV_PROJECT",
        "UV_PROJECT_ENVIRONMENT",
        "UV_WORKING_DIRECTORY",
        "UV_ENV_FILE",
    ):
        env.pop(key, None)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    return env


def _verify_environment(destination: Path, digest: str) -> Path:
    metadata = destination / ".core-environment.json"
    if destination.is_symlink() or not metadata.is_file() or metadata.is_symlink():
        raise CoreArtifactError("Pinned core environment is incomplete")
    try:
        expected = json.loads(metadata.read_bytes())
    except (OSError, json.JSONDecodeError):
        raise CoreArtifactError("Pinned core environment manifest is invalid") from None
    if expected != {"coreArtifact": digest, "files": _environment_files(destination)}:
        raise CoreArtifactError("Pinned core environment integrity check failed")
    return destination / "bin" / "python"


def prepare_environment(bundle: CoreBundle, environments: Path, uv: str = "uv") -> Path:
    """Resolve only the locked closure; reuse an environment only after verification."""
    environments = environments.resolve()
    environments.mkdir(parents=True, exist_ok=True)
    destination = environments / bundle.digest.removeprefix("sha256:")
    metadata = destination / ".core-environment.json"
    # uv writes interpreter paths into the venv, so its final location must be
    # stable. An exclusive lock prevents two supervisors from building it at once.
    lock = environments / (bundle.digest.removeprefix("sha256:") + ".lock")
    with lock.open("a") as locked:
        fcntl.flock(locked, fcntl.LOCK_EX)
        if destination.exists():
            return _verify_environment(destination, bundle.digest)
        env = _safe_environment()
        env["UV_PROJECT_ENVIRONMENT"] = str(destination)
        env["UV_LINK_MODE"] = "copy"
        try:
            completed = subprocess.run(
                [
                    uv,
                    "sync",
                    "--locked",
                    "--no-dev",
                    "--no-default-groups",
                    "--python",
                    bundle.python_version,
                    "--project",
                    str(bundle.path),
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
            )
            if completed.returncode:
                raise CoreArtifactError("Cannot install the pinned core dependency closure")
            python = destination / "bin" / "python"
            version = subprocess.run(
                [
                    str(python),
                    "-I",
                    "-B",
                    "-c",
                    "import platform; print(platform.python_version())",
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if version.returncode or version.stdout.strip() != bundle.python_version:
                raise CoreArtifactError("Pinned Python runtime is unavailable")
            metadata.write_text(
                json.dumps(
                    {"coreArtifact": bundle.digest, "files": _environment_files(destination)},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            metadata.chmod(0o444)
            for path in destination.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    path.chmod(path.stat().st_mode & ~0o222)
            return python
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            raise


def worker_command(
    store: CoreArtifactStore, digest: str, environments: Path, uv: str = "uv"
) -> tuple[list[str], dict[str, str], Path]:
    bundle = store.verify(digest)
    python = prepare_environment(bundle, environments, uv)
    # Recheck after installation: never start from a source tree changed while
    # dependencies were being resolved.
    store.verify(digest)
    env = _safe_environment()
    artifacts = Path(
        env.get(
            "SIGNALDECK_ARTIFACT_DIR",
            str(Path(__file__).resolve().parents[2] / ".data" / "artifacts"),
        )
    ).resolve()
    env["SIGNALDECK_ARTIFACT_DIR"] = str(artifacts)
    env.update(
        SIGNALDECK_CORE_ARTIFACT=digest,
        SIGNALDECK_CORE_ARTIFACT_DIR=str(store.root),
        SIGNALDECK_TASK_QUEUE=store.task_queue(digest),
    )
    return [str(python), "-B", "-s", "-m", "app.workers.durable_worker"], env, bundle.path


def serve(store: CoreArtifactStore, environments: Path) -> None:
    """Keep one real worker for every retained closure, independently of Run projections."""
    processes: dict[str, subprocess.Popen[bytes]] = {}
    retries: dict[str, tuple[int, float]] = {}
    failures: dict[str, str] = {}

    def announce(digest: str, state: str) -> None:
        print(json.dumps({"coreArtifact": digest, "workerState": state}), flush=True)

    def stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                process.wait(timeout=5)
                return
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)

    try:
        while True:
            candidates = {
                "sha256:" + path.name
                for path in store.root.iterdir()
                if len(path.name) == 64 and all(c in "0123456789abcdef" for c in path.name)
            }
            for digest in set(processes) - candidates:
                stop(processes.pop(digest))
                announce(digest, "artifact_missing")
            for digest in sorted(candidates):
                try:
                    store.verify(digest)
                except CoreArtifactError:
                    if digest in processes:
                        stop(processes.pop(digest))
                    if failures.get(digest) != "artifact_invalid":
                        announce(digest, "artifact_invalid")
                    failures[digest] = "artifact_invalid"
                    continue
                process = processes.get(digest)
                if process is not None:
                    if process.poll() is None:
                        continue
                    del processes[digest]
                    count = retries.get(digest, (0, 0.0))[0] + 1
                    retries[digest] = (count, time.monotonic() + min(30, 2 ** min(count, 5)))
                    announce(digest, "exited")
                if time.monotonic() < retries.get(digest, (0, 0.0))[1]:
                    continue
                try:
                    command, env, cwd = worker_command(store, digest, environments)
                    processes[digest] = subprocess.Popen(
                        command,
                        env=env,
                        cwd=cwd,
                        start_new_session=True,
                    )
                    failures.pop(digest, None)
                    announce(digest, "started")
                except (CoreArtifactError, OSError, subprocess.SubprocessError):
                    count = retries.get(digest, (0, 0.0))[0] + 1
                    retries[digest] = (count, time.monotonic() + min(30, 2 ** min(count, 5)))
                    if failures.get(digest) != "bootstrap_failed":
                        announce(digest, "bootstrap_failed")
                    failures[digest] = "bootstrap_failed"
            time.sleep(1)
    finally:
        for process in processes.values():
            stop(process)


def _shutdown(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", default=os.environ.get("SIGNALDECK_CORE_ARTIFACT"))
    parser.add_argument("--serve", action="store_true", help="Serve every retained core closure")
    parser.add_argument("--publish", action="store_true", help="Publish the current core and exit")
    parser.add_argument("--source", type=Path, default=None)
    args = parser.parse_args()
    data = Path(__file__).resolve().parents[2] / ".data"
    store = CoreArtifactStore(
        Path(os.environ.get("SIGNALDECK_CORE_ARTIFACT_DIR", str(data / "core"))),
        source_root=args.source,
        python_version=os.environ.get("SIGNALDECK_CORE_PYTHON_VERSION", "3.13.13"),
    )
    try:
        if args.publish:
            print(store.current_digest())
            return
        if args.serve:
            signal.signal(signal.SIGTERM, _shutdown)
            signal.signal(signal.SIGINT, _shutdown)
            serve(
                store,
                Path(os.environ.get("SIGNALDECK_CORE_ENV_DIR", str(data / "core-environments"))),
            )
            return
        if not args.digest:
            raise CoreArtifactError("A pinned core artifact digest is required")
        command, env, cwd = worker_command(
            store,
            args.digest,
            Path(os.environ.get("SIGNALDECK_CORE_ENV_DIR", str(data / "core-environments"))),
        )
        os.chdir(cwd)
        os.execve(command[0], command, env)
    except KeyboardInterrupt:
        return
    except CoreArtifactError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
