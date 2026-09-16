from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY,
    DEFAULT_DATABASE_URL,
    Settings,
    reset_settings_cache,
)
from app.main import create_app

PRODUCTION_DATABASE_URL = "postgresql+psycopg://user:pass@db:5432/signaldeck"
PRODUCTION_ENCRYPTION_KEY = "real-production-secret-key"


def clear_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNALDECK_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_ENCRYPTION_KEY", raising=False)
    reset_settings_cache()


def test_local_runtime_allows_safe_development_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    settings = Settings()

    assert settings.runtime_mode == "local"
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.agent_platform_encryption_key == DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY


def test_production_runtime_requires_explicit_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setenv("SIGNALDECK_RUNTIME_MODE", "production")
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", PRODUCTION_ENCRYPTION_KEY)
    with pytest.raises(ValidationError, match="DATABASE_URL must be explicitly configured"):
        _ = Settings()


@pytest.mark.parametrize(
    "encryption_key", [DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY, "change-me", "changeme", "", "   "]
)
def test_production_runtime_rejects_placeholder_or_empty_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
    encryption_key: str,
) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setenv("SIGNALDECK_RUNTIME_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", PRODUCTION_DATABASE_URL)
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", encryption_key)
    with pytest.raises(
        ValidationError,
        match="AGENT_PLATFORM_ENCRYPTION_KEY must be explicitly configured",
    ):
        _ = Settings()


@pytest.mark.parametrize("field", ["database_url", "agent_platform_encryption_key"])
def test_runtime_validation_error_hides_sensitive_configuration(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    clear_runtime_env(monkeypatch)
    sensitive_value = "TEST_SENTINEL"
    with pytest.raises(ValidationError) as caught:
        _ = Settings(**{field: sensitive_value, "runtime_mode": "production"})

    with caplog.at_level(logging.ERROR):
        logging.getLogger(__name__).error("Startup configuration failed: %s", caught.value)

    assert sensitive_value not in str(caught.value)
    assert sensitive_value not in caplog.text


def test_production_runtime_accepts_explicit_non_placeholder_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setenv("SIGNALDECK_RUNTIME_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", PRODUCTION_DATABASE_URL)
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", PRODUCTION_ENCRYPTION_KEY)
    settings = Settings()

    assert settings.runtime_mode == "production"
    assert settings.database_url == PRODUCTION_DATABASE_URL
    assert settings.agent_platform_encryption_key == PRODUCTION_ENCRYPTION_KEY


def test_health_endpoint_is_liveness_only(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    app = create_app(init_database=False)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_app_instruments_fastapi_with_logfire(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    instrumented_apps: list[object] = []

    class FakeLogfire:
        @staticmethod
        def configure(**_: object) -> None:
            return None

        @staticmethod
        def instrument_fastapi(app: object) -> None:
            instrumented_apps.append(app)

    monkeypatch.setattr("app.core.telemetry._LOGFIRE_CONFIGURED", False)
    monkeypatch.setattr("app.core.telemetry._LOGFIRE_MODULE", None)
    monkeypatch.setattr("app.core.telemetry._get_logfire_module", lambda: FakeLogfire)

    app = create_app(init_database=False)

    assert instrumented_apps == [app]


def test_readiness_endpoint_reports_database_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setattr("app.main._database_is_ready", lambda: True)
    app = create_app(init_database=False)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_readiness_endpoint_fails_closed_when_database_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setattr("app.main._database_is_ready", lambda: False)
    app = create_app(init_database=False)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
