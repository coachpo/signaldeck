# pyright: reportMissingImports=false
from fastapi import APIRouter

from app.api.connection_presets import router as connection_presets_router
from app.api.platform_artifacts import router as artifacts_router
from app.api.platform_packages import router as workflow_packages_router
from app.api.platform_resources import router as resources_router
from app.api.platform_runs import router as runs_router
from app.api.platform_schedules import router as schedules_router
from app.api.task_presets import router as task_presets_router

platform_router = APIRouter(prefix="/api")
platform_router.include_router(resources_router)
platform_router.include_router(artifacts_router)
platform_router.include_router(workflow_packages_router)
platform_router.include_router(runs_router)
platform_router.include_router(schedules_router)

platform_router.include_router(task_presets_router)

platform_router.include_router(connection_presets_router)
