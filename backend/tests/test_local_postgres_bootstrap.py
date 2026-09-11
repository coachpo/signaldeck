"""Local test storage selection must not modify an existing bind-mounted database."""

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tests import conftest as bootstrap


@pytest.mark.parametrize("directory", [None, "explicit-data"])
def test_new_database_uses_managed_volume_unless_directory_is_explicit(
    monkeypatch, tmp_path, directory
):
    data = tmp_path / directory if directory else None
    calls = []
    monkeypatch.setattr(bootstrap, "LOCAL_POSTGRES_DATA", data)
    monkeypatch.setattr(bootstrap, "LOCAL_POSTGRES_PORT", "")
    monkeypatch.setattr(bootstrap, "_docker_container_running", lambda _: False)
    monkeypatch.setattr(bootstrap, "_docker_container_exists", lambda _: False)
    monkeypatch.setattr(bootstrap, "_docker_container_port", lambda *_: "32780")
    monkeypatch.setattr(bootstrap, "_wait_for_start_local_database", lambda: None)

    def docker(args, *, check):
        calls.append(args)
        return CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(bootstrap, "_run_docker", docker)
    assert bootstrap._ensure_start_local_database().port == 32780
    assert len(calls) == 1 and calls[0][0] == "run"
    mount = calls[0][calls[0].index("-v") + 1]
    expected = str(data) if data else bootstrap.LOCAL_POSTGRES_VOLUME
    assert mount == f"{expected}:/var/lib/postgresql/data"
    assert list(tmp_path.iterdir()) == ([Path(data)] if data else [])


def test_running_default_database_is_reused_without_mutation(monkeypatch):
    monkeypatch.setattr(bootstrap, "LOCAL_POSTGRES_PORT", "")
    monkeypatch.setattr(bootstrap, "_docker_container_running", lambda _: True)
    monkeypatch.setattr(bootstrap, "_docker_container_port", lambda *_: "32781")
    monkeypatch.setattr(bootstrap, "_wait_for_start_local_database", lambda: None)

    def unexpected(*args, **kwargs):
        pytest.fail("Reusing a running test database must not mutate Docker resources")

    monkeypatch.setattr(bootstrap, "_run_docker", unexpected)
    assert bootstrap._ensure_start_local_database().port == 32781


def test_explicit_database_url_bypasses_local_storage(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://test-db.example/owned")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused.example/unused")

    def unexpected():
        pytest.fail("An explicit test URL must not start or replace a local container")

    monkeypatch.setattr(bootstrap, "_ensure_start_local_database", unexpected)
    assert bootstrap._get_base_database_url().host == "test-db.example"
