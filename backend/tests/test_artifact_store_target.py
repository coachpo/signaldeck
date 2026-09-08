from concurrent.futures import ThreadPoolExecutor

import pytest

from app.domain.tool_contracts import ArtifactRef
from app.infrastructure.artifact_store import ArtifactIntegrityError, ArtifactStore


def test_content_addressing_concurrent_immutable_put_and_corruption_detection(tmp_path):
    store = ArtifactStore(tmp_path, inline_threshold=4, max_bytes=100)
    with ThreadPoolExecutor(max_workers=4) as executor:
        refs = list(executor.map(lambda _: store.put(b"original"), range(12)))
    assert len({ref.digest for ref in refs}) == 1
    assert store.read(refs[0]) == b"original"
    path = next(path for path in tmp_path.rglob("*") if path.is_file())
    path.write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="digest mismatch"):
        store.read(refs[0])
    with pytest.raises(ArtifactIntegrityError):
        store.put(b"original")
    assert path.read_bytes() == b"tampered"


def test_json_threshold_reference_and_missing_size_validation(tmp_path):
    store = ArtifactStore(tmp_path, inline_threshold=8, max_bytes=100)
    assert store.store_json({"a": 1}) == {"a": 1}
    value = {"payload": "large object"}
    ref = store.store_json(value)
    assert isinstance(ref, ArtifactRef)
    assert store.read_json(ref) == value
    assert set(ref.model_dump(by_alias=True)) == {"digest", "sizeBytes", "mediaType"}
    with pytest.raises(ArtifactIntegrityError, match="size mismatch"):
        store.read(ref.model_copy(update={"size_bytes": 1}))
    with pytest.raises(ArtifactIntegrityError, match="unavailable"):
        store.read(ArtifactRef(digest="sha256:" + "a" * 64, size_bytes=1))
    with pytest.raises(ArtifactIntegrityError, match="size limit"):
        store.put(b"x" * 101)


def test_artifact_path_and_symbolic_link_escape_rejected(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put(b"original")
    path = next(path for path in store.root.rglob("*") if path.is_file())
    outside = tmp_path / "outside"
    outside.write_bytes(b"original")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ArtifactIntegrityError):
        store.read(ref)
    with pytest.raises(ValueError):
        store.read(ref.model_copy(update={"digest": "../../outside"}))


def test_digest_inspection_supports_safe_download_without_run_scan(tmp_path):
    store = ArtifactStore(tmp_path)
    original = store.put(b"download body", "application/json")
    inspected = store.inspect(original.digest)
    assert inspected.size_bytes == len(b"download body")
    assert inspected.media_type == "application/octet-stream"
    assert store.read(inspected) == b"download body"
    with pytest.raises(ValueError):
        store.inspect("../../outside")
    with pytest.raises(ArtifactIntegrityError):
        store.inspect("sha256:" + "a" * 64)
    path = next(path for path in tmp_path.rglob("*") if path.is_file())
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(ArtifactIntegrityError):
        store.inspect(original.digest)


def test_inspection_rejects_oversized_and_nonregular_objects(tmp_path):
    store = ArtifactStore(tmp_path, inline_threshold=0, max_bytes=4)
    ref = store.put(b"body")
    path = next(path for path in tmp_path.rglob("*") if path.is_file())
    path.write_bytes(b"oversized")
    with pytest.raises(ArtifactIntegrityError, match="size limit"):
        store.inspect(ref.digest)
    path.unlink()
    path.mkdir()
    with pytest.raises(ArtifactIntegrityError, match="regular file"):
        store.inspect(ref.digest)
    with pytest.raises(ArtifactIntegrityError):
        store.read(ref)
