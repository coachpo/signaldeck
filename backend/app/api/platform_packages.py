"""Workflow Package authoring and launch HTTP boundaries."""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.platform_dependencies import get_launch_service, get_platform_store
from app.application.definitions import save_definition
from app.application.launch import LaunchService
from app.application.package_import import import_source
from app.application.task_preparation import prepare_task
from app.domain.definition_parser import parse_package_source
from app.domain.execution import ApplicationError, RunSummary
from app.domain.schema_contract import DomainValidationError
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.plugin_health import PluginHealthReader
from app.schemas.package_import import ImportItemRead, PackageImportRead, PackageImportRequest
from app.schemas.platform import (
    DiagnosticRead,
    LaunchRequest,
    ManifestRequest,
    PackageList,
    PackageRead,
    ValidationRead,
)
from app.schemas.task_experience import PreparationRead, PrepareRequest

router = APIRouter(prefix="/workflow-packages", tags=["workflow-packages"])
Store = Annotated[PlatformStore, Depends(get_platform_store)]


def package_read(record: dict[str, Any]) -> PackageRead:
    definition = record["definition"]
    metadata = definition["metadata"]
    return PackageRead(
        id=record["packageKey"],
        key=record["packageKey"],
        name=metadata["name"],
        description=metadata.get("description", ""),
        source=record["source"],
        definition=definition,
        plans=record["plan"],
        package_hash=record["packageHash"],
        created_at=record["createdAt"],
        updated_at=record["createdAt"],
    )


@router.get("", response_model=PackageList)
def list_packages(store: Store) -> PackageList:
    return PackageList(items=[package_read(item) for item in store.list_packages()])


@router.post("/import", response_model=PackageImportRead)
def import_packages(payload: PackageImportRequest, store: Store) -> PackageImportRead:
    return PackageImportRead(
        items=[
            ImportItemRead(
                name=source.name,
                **import_source(
                    store, source.manifest_source, missing_only=payload.mode == "missing_only"
                ),
            )
            for source in payload.sources
        ]
    )


@router.post("/validate-manifest", response_model=ValidationRead)
def validate_manifest(payload: ManifestRequest) -> ValidationRead:
    try:
        compiled = parse_package_source(payload.manifest_source)
    except DomainValidationError as exc:
        return ValidationRead(
            diagnostics=[DiagnosticRead(**asdict(item)) for item in exc.diagnostics]
        )
    return ValidationRead(
        definition=compiled.package, plans=compiled.plans, content_hash=compiled.content_hash
    )


@router.post("", response_model=PackageRead, status_code=201)
def create_package(payload: ManifestRequest, store: Store) -> PackageRead:
    return package_read(save_definition(store, payload.manifest_source))


@router.get("/{package_key}", response_model=PackageRead)
def get_package(package_key: str, store: Store) -> PackageRead:
    record = store.get_package(package_key)
    if record is None:
        raise ApplicationError("package_not_found", "Workflow Package is unavailable", status=404)
    return package_read(record)


@router.patch("/{package_key}", response_model=PackageRead)
def update_package(package_key: str, payload: ManifestRequest, store: Store) -> PackageRead:
    return package_read(save_definition(store, payload.manifest_source, expected_key=package_key))


@router.post("/{package_key}/launches", response_model=RunSummary, status_code=201)
def launch_package(
    package_key: str,
    payload: LaunchRequest,
    service: Annotated[LaunchService, Depends(get_launch_service)],
) -> RunSummary:
    return service.launch(
        package_key,
        payload.workflow_key,
        payload.parameters,
        launch_id=payload.launch_id,
        revision_hash=payload.revision_hash,
        binding_token=payload.binding_token,
    )


@router.post("/{package_key}/prepare", response_model=PreparationRead)
def prepare_package(
    package_key: str,
    payload: PrepareRequest,
    store: Store,
    service: Annotated[LaunchService, Depends(get_launch_service)],
) -> PreparationRead:
    result = prepare_task(
        service,
        package_key,
        payload.workflow_key,
        payload.parameters,
        payload.revision_hash,
        payload.source_run_id,
    )
    installed = {item["pluginId"]: item for item in store.list_plugins()}
    health = PluginHealthReader(store.session_factory)
    for requirement in result.requirements:
        if requirement.kind == "plugin" and requirement.id in installed:
            release = installed[requirement.id]["release"]
            if not isinstance(release.get("artifactDigest"), str):
                continue
            observation = health.latest(requirement.id, release["artifactDigest"])
            requirement.observation = observation.status
            requirement.observed_at = observation.observed_at
            requirement.observation_error = observation.error_code
    return result
