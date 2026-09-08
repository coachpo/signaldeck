"""Retained executable core closures, addressed by a canonical file manifest."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PYTHON = re.compile(r"3\.\d+\.\d+\Z")
_ROOT_FILES = frozenset({"pyproject.toml", "uv.lock", "VERSION", "README.md"})
_SOURCE_SUFFIXES = frozenset({".py", ".sql", ".json", ".yaml", ".yml", ".jinja2", ".j2"})


class CoreArtifactError(ValueError):
    """The pinned executable closure cannot be trusted or loaded."""


def task_queue(digest: str) -> str:
    if not _DIGEST.fullmatch(digest):
        raise CoreArtifactError("Invalid core artifact digest")
    return "sd-core-" + digest.removeprefix("sha256:")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _allowed(path: PurePosixPath) -> bool:
    if path.is_absolute() or any(
        part.startswith(".") or part == "__pycache__" for part in path.parts
    ):
        return False
    return str(path) in _ROOT_FILES or (
        len(path.parts) > 1 and path.parts[0] == "app" and path.suffix in _SOURCE_SUFFIXES
    )


def _files(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted([*(root / name for name in _ROOT_FILES), *(root / "app").rglob("*")]):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        # README remains allowed when verifying retained artifacts from older publishers.
        if not _allowed(relative) or str(relative) == "README.md":
            continue
        if path.is_symlink() or any(
            parent.is_symlink() for parent in path.parents if parent != root
        ):
            raise CoreArtifactError("Core source cannot contain symbolic links")
        if path.is_file():
            files[str(relative)] = path.read_bytes()
    if not {"pyproject.toml", "uv.lock", "app/__init__.py"}.issubset(files):
        raise CoreArtifactError("Core source closure is incomplete")
    return files


@dataclass(frozen=True)
class CoreBundle:
    digest: str
    path: Path
    python_version: str
    manifest: dict[str, Any]


class CoreArtifactStore:
    task_queue = staticmethod(task_queue)

    def __init__(
        self,
        root: Path,
        source_root: Path | None = None,
        python_version: str = "3.13.13",
    ) -> None:
        if not _PYTHON.fullmatch(python_version):
            raise CoreArtifactError("Core Python version must include its exact patch version")
        self.root = root.resolve()
        self.source_root = (source_root or Path(__file__).resolve().parents[2]).resolve()
        self.python_version = python_version
        self.root.mkdir(parents=True, exist_ok=True)

    def current_digest(self) -> str:
        return self.publish().digest

    def publish(self) -> CoreBundle:
        files = _files(self.source_root)
        manifest = {
            "format": 1,
            "pythonVersion": self.python_version,
            "files": {
                name: {"sha256": _digest(content), "size": len(content)}
                for name, content in files.items()
            },
        }
        encoded = _canonical(manifest)
        digest = _digest(encoded)
        destination = self.root / digest.removeprefix("sha256:")
        if destination.exists():
            return self.verify(digest)
        pending = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.root))
        try:
            for name, content in {**files, "manifest.json": encoded}.items():
                path = pending / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                path.chmod(0o444)
            for directory in [
                *sorted((p for p in pending.rglob("*") if p.is_dir()), reverse=True),
                pending,
            ]:
                directory.chmod(0o555)
                descriptor = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            try:
                pending.rename(destination)
            except OSError:
                if not destination.exists():
                    raise
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if pending.exists():
                for path in [pending, *(p for p in pending.rglob("*") if p.is_dir())]:
                    path.chmod(0o755)
                shutil.rmtree(pending)
        return self.verify(digest)

    def verify(self, digest: str) -> CoreBundle:
        task_queue(digest)
        path = self.root / digest.removeprefix("sha256:")
        try:
            if path.is_symlink() or not path.is_dir():
                raise CoreArtifactError("Pinned core artifact is unavailable")
            manifest_path = path / "manifest.json"
            if manifest_path.is_symlink():
                raise CoreArtifactError("Core manifest cannot be a symbolic link")
            encoded = manifest_path.read_bytes()
            if _digest(encoded) != digest:
                raise CoreArtifactError("Core manifest digest mismatch")
            manifest = json.loads(encoded)
            if (
                set(manifest) != {"format", "pythonVersion", "files"}
                or manifest["format"] != 1
                or not _PYTHON.fullmatch(manifest["pythonVersion"])
                or not isinstance(manifest["files"], dict)
            ):
                raise CoreArtifactError("Invalid core artifact manifest")
            actual = set()
            for item in path.rglob("*"):
                if item.is_symlink():
                    raise CoreArtifactError("Core artifact cannot contain symbolic links")
                if item.is_file() and item.relative_to(path).as_posix() != "manifest.json":
                    actual.add(item.relative_to(path).as_posix())
            if actual != set(manifest["files"]):
                raise CoreArtifactError("Core artifact file set mismatch")
            for name, expected in manifest["files"].items():
                if not _allowed(PurePosixPath(name)) or set(expected) != {"sha256", "size"}:
                    raise CoreArtifactError("Invalid core artifact file record")
                content = (path / name).read_bytes()
                if len(content) != expected["size"] or _digest(content) != expected["sha256"]:
                    raise CoreArtifactError("Core artifact content digest mismatch")
            if not {"pyproject.toml", "uv.lock", "app/__init__.py"}.issubset(actual):
                raise CoreArtifactError("Core artifact closure is incomplete")
        except (OSError, TypeError, KeyError, json.JSONDecodeError):
            raise CoreArtifactError("Pinned core artifact is unavailable or invalid") from None
        return CoreBundle(digest, path, manifest["pythonVersion"], manifest)

    def verify_worker(self, digest: str) -> CoreBundle:
        bundle = self.verify(digest)
        if self.source_root != bundle.path.resolve():
            raise CoreArtifactError("Worker is not executing its pinned core artifact")
        if platform.python_version() != bundle.python_version:
            raise CoreArtifactError("Worker Python does not match its pinned core artifact")
        return bundle
