from __future__ import annotations

# pyright: reportUnusedFunction=false
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.platform_dependencies import get_core_artifacts, get_platform_store
from app.api.platform_router import platform_router
from app.api.platform_schedules import get_schedule_store
from app.core.auth import BearerTokenMiddleware
from app.core.config import get_settings
from app.core.errors import ApiError, browser_safe_error_details, request_validation_to_details
from app.core.telemetry import configure_logfire, instrument_fastapi_app
from app.db.engine import get_engine
from app.domain.execution import ApplicationError
from app.domain.schema_contract import DomainValidationError
from app.infrastructure.core_artifacts import CoreArtifactError
from app.infrastructure.package_seeds import seed_packages

READINESS_UNAVAILABLE_STATUS = status.HTTP_503_SERVICE_UNAVAILABLE


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    store = get_platform_store()
    store.initialize()
    seed_packages(store)
    get_schedule_store().initialize()
    # Publish the process's executable closure once. A later source edit must not
    # be combined with already-imported API code in a different launch snapshot.
    app.state.core_artifact_digest = get_core_artifacts().current_digest()
    yield


def _database_is_ready() -> bool:
    try:
        with get_engine().connect() as connection:
            _ = connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def create_app(*, init_database: bool = True) -> FastAPI:
    settings = get_settings()
    configure_logfire()
    app = FastAPI(
        title="SignalDeck Backend", version="0.1.0", lifespan=lifespan if init_database else None
    )
    instrument_fastapi_app(app)
    if settings.api_token:
        app.add_middleware(BearerTokenMiddleware, token=settings.api_token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": browser_safe_error_details(exc.details),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Request validation failed",
                "details": request_validation_to_details(exc),
            },
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(_: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"code": exc.code, "message": exc.message, "details": []},
        )

    @app.exception_handler(CoreArtifactError)
    async def core_artifact_error_handler(_: Request, exc: CoreArtifactError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "code": "core_artifact_unavailable",
                "message": "Core execution artifact is unavailable",
                "details": [],
            },
        )

    @app.exception_handler(DomainValidationError)
    async def definition_error_handler(_: Request, exc: DomainValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "definition_invalid",
                "message": "Definition or input does not satisfy its contract",
                "details": [
                    {
                        "code": item.code,
                        "path": item.path,
                        "message": item.message,
                        "line": item.line,
                        "column": item.column,
                    }
                    for item in exc.diagnostics
                ],
            },
        )

    @app.exception_handler(ValidationError)
    async def configuration_error_handler(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "configuration_invalid",
                "message": "Configuration does not satisfy its contract",
                "details": [
                    {"field": ".".join(map(str, item["loc"])), "issue": item["type"]}
                    for item in exc.errors(include_input=False)
                ],
            },
        )

    @app.get("/health", tags=["health"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["health"])
    def readinesscheck() -> JSONResponse:
        if not _database_is_ready():
            return JSONResponse(
                status_code=READINESS_UNAVAILABLE_STATUS,
                content={"status": "unavailable", "database": "unavailable"},
            )
        return JSONResponse(content={"status": "ok", "database": "ok"})

    app.include_router(platform_router)
    return app


app = create_app()
