"""Read saved releases and explicit deployment bindings without plugin I/O."""

import os
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Response

from app.api.platform_dependencies import get_platform_store
from app.domain.execution import ApplicationError
from app.domain.plugin_pages import PluginMountRegistry, PluginPage
from app.domain.tool_contracts import PluginRelease
from app.infrastructure.platform_store import PlatformStore

router = APIRouter(tags=["plugins"])
Store = Annotated[PlatformStore, Depends(get_platform_store)]


@router.get("/plugin-auth", status_code=204, include_in_schema=False)
def plugin_auth() -> Response:
    """Nginx auth_request shares the ordinary Core bearer-token middleware."""
    return Response(status_code=204)


@router.get("/plugin-pages", response_model=list[PluginPage])
def plugin_pages(store: Store) -> list[PluginPage]:
    path = os.environ.get("SIGNALDECK_PLUGIN_MOUNTS_FILE")
    if not path:
        return []
    try:
        registry = PluginMountRegistry.model_validate_json(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise ApplicationError(
            "plugin_mounts_unavailable", "Plugin pages are unavailable", status=503
        ) from exc
    current = {
        (item["pluginId"], item["release"]["artifactDigest"]): item["enabled"]
        for item in store.list_plugins()
    }
    pages: list[PluginPage] = []
    for mount in registry.mounts:
        saved = store.get_plugin_release(mount.plugin_id, mount.artifact_digest)
        if saved is None:
            continue
        release = PluginRelease.model_validate(saved)
        page_url = f"/apps/{mount.mount_key}/"
        if release.ui is None or not release.page_url:
            continue
        if urlsplit(release.page_url).path != page_url:
            continue
        pages.append(
            PluginPage(
                mount_key=mount.mount_key,
                plugin_id=mount.plugin_id,
                artifact_digest=mount.artifact_digest,
                title=release.ui.title,
                page_url=page_url,
                enabled=bool(current.get((mount.plugin_id, mount.artifact_digest), False)),
            )
        )
    return pages
