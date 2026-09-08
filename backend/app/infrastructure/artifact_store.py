"""Immutable content-addressed objects on the local persistent artifact volume."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from app.domain.tool_contracts import ArtifactRef


class ArtifactIntegrityError(ValueError):
    pass


class ArtifactStore:
    def __init__(
        self, root: Path, inline_threshold: int = 65536, max_bytes: int = 64 * 1024 * 1024
    ):
        if inline_threshold < 0 or max_bytes < inline_threshold:
            raise ValueError("Invalid artifact size limits")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.inline_threshold = inline_threshold
        self.max_bytes = max_bytes

    def _path(self, ref: ArtifactRef) -> Path:
        # Revalidate caller-created model copies before using any path component.
        checked = ArtifactRef.model_validate(ref.model_dump())
        digest = checked.digest.removeprefix("sha256:")
        path = self.root / digest[:2] / digest[2:]
        if not path.resolve().is_relative_to(self.root):
            raise ArtifactIntegrityError("Artifact path escapes the artifact volume")
        return path

    def put(self, content: bytes, media_type: str = "application/octet-stream") -> ArtifactRef:
        if len(content) > self.max_bytes:
            raise ArtifactIntegrityError("Artifact exceeds configured size limit")
        ref = ArtifactRef(
            digest="sha256:" + hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            media_type=media_type,
        )
        destination = self._path(ref)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)
                directory = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except FileExistsError:
                self.read(ref)
        finally:
            os.unlink(temporary)
        return ref

    def inspect(self, digest: str) -> ArtifactRef:
        """Read bounded object metadata; callers use read() to verify content before serving."""
        ref = ArtifactRef(digest=digest, size_bytes=0)
        path = self._path(ref)
        try:
            information = path.lstat()
        except OSError:
            raise ArtifactIntegrityError("Artifact is unavailable") from None
        if not stat.S_ISREG(information.st_mode):
            raise ArtifactIntegrityError("Artifact must be a regular file")
        if information.st_size > self.max_bytes:
            raise ArtifactIntegrityError("Artifact exceeds configured size limit")
        return ref.model_copy(update={"size_bytes": information.st_size})

    def read(self, ref: ArtifactRef) -> bytes:
        path = self._path(ref)
        try:
            if path.is_symlink():
                raise ArtifactIntegrityError("Artifact cannot be a symbolic link")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                information = os.fstat(stream.fileno())
                if not stat.S_ISREG(information.st_mode):
                    raise ArtifactIntegrityError("Artifact must be a regular file")
                size = information.st_size
                if size != ref.size_bytes or size > self.max_bytes:
                    raise ArtifactIntegrityError("Artifact size mismatch")
                content = stream.read(self.max_bytes + 1)
        except OSError:
            raise ArtifactIntegrityError("Artifact is unavailable") from None
        if (
            len(content) != ref.size_bytes
            or "sha256:" + hashlib.sha256(content).hexdigest() != ref.digest
        ):
            raise ArtifactIntegrityError("Artifact digest mismatch")
        return content

    def store_json(self, value: Any) -> Any | ArtifactRef:
        content = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(content) <= self.inline_threshold:
            return json.loads(content)
        return self.put(content, "application/json")

    def read_json(self, ref: ArtifactRef) -> Any:
        if ref.media_type != "application/json":
            raise ArtifactIntegrityError("Artifact is not JSON")
        return json.loads(self.read(ref))
