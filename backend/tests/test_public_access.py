"""Application access stays open even when an old deployment token remains."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import reset_settings_cache
from app.infrastructure.platform_store import PlatformStore
from app.main import create_app

ALLOWED_ORIGIN = "http://frontend.test"


@pytest.fixture(params=[None, "obsolete-deployment-token"])
def access_client(
    request: pytest.FixtureRequest,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    if request.param is None:
        monkeypatch.delenv("SIGNALDECK_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("SIGNALDECK_API_TOKEN", request.param)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    reset_settings_cache()
    PlatformStore(session_factory).initialize()
    with TestClient(create_app(init_database=False)) as client:
        yield client


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer obsolete-deployment-token"},
        {"Authorization": "Bearer arbitrary-token"},
    ],
)
def test_api_reads_do_not_require_authentication(
    access_client: TestClient, headers: dict[str, str]
) -> None:
    response = access_client.get("/api/runs", headers=headers)

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert access_client.get("/api/plugin-pages", headers=headers).status_code == 200


def test_cors_still_limits_allowed_browser_origins(access_client: TestClient) -> None:
    response = access_client.get("/api/runs", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN

    response = access_client.get("/api/runs", headers={"Origin": "http://other.test"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_plugin_auth_helper_is_removed() -> None:
    with TestClient(create_app(init_database=False)) as client:
        assert client.get("/api/plugin-auth").status_code == 404
