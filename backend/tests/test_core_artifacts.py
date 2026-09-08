from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.infrastructure.core_artifacts import (
    CoreArtifactError,
    CoreArtifactStore,
    CoreBundle,
    _files,
    task_queue,
)
from app.workers.artifact_worker import _environment_files, worker_command


def test_linux_venv_directory_alias_preserves_dependency_integrity(tmp_path: Path) -> None:
    environment = tmp_path / "environment"
    library = environment / "lib/python3.13/site-packages"
    library.mkdir(parents=True)
    dependency = library / "dependency.py"
    dependency.write_text("VALUE = 1\n")
    (environment / "lib64").symlink_to("lib", target_is_directory=True)
    original = _environment_files(environment)
    assert "lib64" in original
    dependency.write_text("VALUE = 2\n")
    assert _environment_files(environment) != original
    external = tmp_path / "external"
    external.mkdir()
    (environment / "lib64").unlink()
    (environment / "lib64").symlink_to(external, target_is_directory=True)
    with pytest.raises(CoreArtifactError, match="invalid symbolic link"):
        _environment_files(environment)


def source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    (root / "app/workers").mkdir(parents=True)
    (root / "app/__init__.py").write_text("")
    (root / "app/workers/__init__.py").write_text("")
    (root / "app/workers/durable_worker.py").write_text("print('core-one')\n")
    (root / "pyproject.toml").write_text(
        '[project]\nname="core-artifact-fixture"\nversion="0.0.0"\n'
        'requires-python=">=3.13"\ndependencies=[]\n[tool.uv]\npackage=false\n'
    )
    (root / "uv.lock").write_text(
        'version = 1\nrevision = 3\nrequires-python = ">=3.13"\n'
        '[[package]]\nname = "core-artifact-fixture"\nversion = "0.0.0"\n'
        'source = { virtual = "." }\n'
    )
    return root


def publish_legacy_readme_bundle(store: CoreArtifactStore) -> CoreBundle:
    """Publish the pre-exclusion file set with the unchanged format-1 manifest writer."""

    def legacy_files(root: Path) -> dict[str, bytes]:
        return {**_files(root), "README.md": (root / "README.md").read_bytes()}

    with patch("app.infrastructure.core_artifacts._files", legacy_files):
        return store.publish()


def test_readme_changes_do_not_publish_another_executable_closure(tmp_path: Path) -> None:
    root = source(tmp_path)
    store = CoreArtifactStore(tmp_path / "artifacts", root)
    bundle = store.publish()
    readme = root / "README.md"
    for content in ["# Core documentation\n", "# Updated documentation\n"]:
        readme.write_text(content)
        assert store.publish() == bundle
    readme.unlink()
    assert store.current_digest() == bundle.digest
    assert "README.md" not in bundle.manifest["files"]
    assert not (bundle.path / "README.md").exists()
    assert list(store.root.iterdir()) == [bundle.path]


@pytest.mark.parametrize("name", ["app/workers/durable_worker.py", "pyproject.toml", "uv.lock"])
def test_execution_source_project_and_lock_remain_in_core_identity(
    tmp_path: Path, name: str
) -> None:
    root = source(tmp_path)
    store = CoreArtifactStore(tmp_path / "artifacts", root)
    old = store.publish()
    path = root / name
    original = path.read_bytes()
    path.write_bytes(original + b"\n# changed executable closure\n")
    new = store.publish()
    assert new.digest != old.digest
    assert store.verify(old.digest).path.joinpath(name).read_bytes() == original
    assert store.verify(new.digest).path.joinpath(name).read_bytes() == path.read_bytes()


def test_historical_readme_remains_readable_and_integrity_checked(tmp_path: Path) -> None:
    root = source(tmp_path)
    (root / "README.md").write_text("# Retained documentation\n")
    store = CoreArtifactStore(tmp_path / "artifacts", root)
    old = publish_legacy_readme_bundle(store)
    new = store.publish()
    assert old.digest != new.digest
    assert "README.md" in store.verify(old.digest).manifest["files"]
    retained = old.path / "README.md"
    assert retained.read_text() == "# Retained documentation\n"
    assert "README.md" not in new.manifest["files"]
    retained.chmod(0o644)
    retained.write_text("# Tampered documentation\n")
    with pytest.raises(CoreArtifactError, match="content digest"):
        store.verify(old.digest)


def test_deterministic_closure_excludes_runtime_secrets_and_retains_old_code(
    tmp_path: Path,
) -> None:
    root = source(tmp_path)
    (root / ".env").write_text("FAKE_SECRET=must-not-be-bundled")
    (root / "app/.env").write_text("FAKE_SECRET=must-not-be-bundled")
    (root / "app/__pycache__").mkdir()
    (root / "app/__pycache__/cached.pyc").write_bytes(b"not executable source")
    store = CoreArtifactStore(
        tmp_path / "artifacts", root, python_version=platform.python_version()
    )
    old = store.publish()
    assert store.current_digest() == old.digest
    assert not any(".env" in p or "__pycache__" in p for p in old.manifest["files"])
    assert old.path.stat().st_mode & 0o222 == 0
    assert all((old.path / name).stat().st_mode & 0o222 == 0 for name in old.manifest["files"])
    (root / "app/workers/durable_worker.py").write_text("print('core-two')\n")
    new = store.publish()
    assert new.digest != old.digest
    assert store.verify(old.digest).path.joinpath("app/workers/durable_worker.py").read_text() == (
        "print('core-one')\n"
    )
    assert task_queue(old.digest) != task_queue(new.digest)
    with pytest.raises(CoreArtifactError, match="not executing"):
        store.verify_worker(old.digest)
    assert CoreArtifactStore(store.root, old.path).verify_worker(old.digest) == old


def test_missing_tampered_extra_or_symlinked_bundle_is_rejected(tmp_path: Path) -> None:
    store = CoreArtifactStore(tmp_path / "artifacts", source(tmp_path))
    bundle = store.publish()
    with pytest.raises(CoreArtifactError, match="unavailable"):
        store.verify("sha256:" + "0" * 64)
    code = bundle.path / "app/workers/durable_worker.py"
    code.chmod(0o644)
    code.write_text("print('tampered')\n")
    with pytest.raises(CoreArtifactError, match="content digest"):
        store.verify(bundle.digest)
    code.write_text("print('core-one')\n")
    bundle.path.chmod(0o755)
    extra = bundle.path / "credentials.json"
    extra.write_text("{}")
    with pytest.raises(CoreArtifactError, match="file set"):
        store.verify(bundle.digest)
    extra.unlink()
    code.parent.chmod(0o755)
    code.unlink()
    code.symlink_to(store.source_root / "app/workers/durable_worker.py")
    with pytest.raises(CoreArtifactError, match="symbolic"):
        store.verify(bundle.digest)


def test_exact_python_and_locked_dependencies_execute_each_retained_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SIGNALDECK_ARTIFACT_DIR", raising=False)
    root = source(tmp_path)
    store = CoreArtifactStore(tmp_path / "artifacts", root)
    old = store.publish()
    (root / "app/workers/durable_worker.py").write_text("print('core-two')\n")
    new = store.publish()
    outputs = []
    for bundle in [old, new, old]:
        command, env, cwd = worker_command(store, bundle.digest, tmp_path / "environments")
        assert "PYTHONPATH" not in env
        assert env["SIGNALDECK_ARTIFACT_DIR"] == str(
            Path(__file__).resolve().parents[1] / ".data" / "artifacts"
        )
        assert env["SIGNALDECK_TASK_QUEUE"] == task_queue(bundle.digest)
        result = subprocess.run(
            command, env=env, cwd=cwd, text=True, capture_output=True, check=True
        )
        outputs.append(result.stdout.strip())
        python = subprocess.run(
            [command[0], "-I", "-B", "-c", "import platform; print(platform.python_version())"],
            text=True,
            capture_output=True,
            check=True,
        )
        assert python.stdout.strip() == "3.13.13"
    assert outputs == ["core-one", "core-two", "core-one"]
    environment = tmp_path / "environments" / old.digest.removeprefix("sha256:")
    (environment / "injected.py").write_text("print('unexpected file')")
    with pytest.raises(CoreArtifactError, match="environment integrity"):
        worker_command(store, old.digest, tmp_path / "environments")


def test_path_like_digest_and_unpinned_python_are_rejected(tmp_path: Path) -> None:
    for digest in ["../current", "sha256:" + "a" * 63, "sha256:" + "g" * 64]:
        with pytest.raises(CoreArtifactError, match="digest"):
            task_queue(digest)
    with pytest.raises(CoreArtifactError, match="patch"):
        CoreArtifactStore(tmp_path, python_version="3.13")


def test_supervisor_starts_retained_versions_and_stops_owned_workers(tmp_path: Path) -> None:
    import json
    import os
    import sys
    import time

    root = source(tmp_path)
    code = root / "app/workers/durable_worker.py"
    worker_source = (
        "import json, os, time\nfrom pathlib import Path\n"
        "with Path(os.environ['CORE_FIXTURE_LOG']).open('a') as stream:\n"
        " stream.write(json.dumps({'pid':os.getpid(), 'artifact':"
        "os.environ['SIGNALDECK_CORE_ARTIFACT'], 'version': VERSION})+'\\n')\n"
        "while True: time.sleep(1)\n"
    )
    code.write_text("VERSION='one'\n" + worker_source)
    store = CoreArtifactStore(tmp_path / "artifacts", root)
    old = store.publish()
    code.write_text("VERSION='two'\n" + worker_source)
    new = store.publish()
    # A directory name alone cannot authorize executing code outside the volume.
    (store.root / ("f" * 64)).symlink_to(root, target_is_directory=True)
    evidence = tmp_path / "workers.jsonl"
    env = dict(
        os.environ,
        SIGNALDECK_CORE_ARTIFACT_DIR=str(store.root),
        SIGNALDECK_CORE_ENV_DIR=str(tmp_path / "environments"),
        CORE_FIXTURE_LOG=str(evidence),
    )
    with (tmp_path / "supervisor.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "app.workers.artifact_worker", "--serve"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        records = []
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evidence.exists():
                    records = [json.loads(line) for line in evidence.read_text().splitlines()]
                if len(records) >= 2:
                    break
                assert process.poll() is None
                time.sleep(0.05)
            assert {record["artifact"] for record in records} == {old.digest, new.digest}
            assert {record["version"] for record in records} == {"one", "two"}
            assert len({record["pid"] for record in records}) == 2
        finally:
            process.terminate()
            process.wait(timeout=15)
        assert process.returncode == 0
        for record in records:
            with pytest.raises(ProcessLookupError):
                os.kill(record["pid"], 0)
    assert "artifact_invalid" in (tmp_path / "supervisor.log").read_text()


def test_stale_dependency_lock_cannot_start_worker(tmp_path: Path) -> None:
    root = source(tmp_path)
    project = root / "pyproject.toml"
    project.write_text(project.read_text().replace('version="0.0.0"', 'version="0.0.1"'))
    store = CoreArtifactStore(tmp_path / "artifacts", root)
    bundle = store.publish()
    with pytest.raises(CoreArtifactError, match="dependency closure"):
        worker_command(store, bundle.digest, tmp_path / "environments")
    assert not (tmp_path / "environments" / bundle.digest.removeprefix("sha256:")).exists()
