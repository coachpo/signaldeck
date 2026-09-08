"""Resource credentials have write-only HTTP fields; plugin reads stay offline."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.platform_dependencies import get_platform_store
from app.db.engine import get_session_factory
from app.domain.resources import ResourceRead, ResourceWrite, validate_resource
from app.infrastructure.platform_store import PlatformStore
from app.infrastructure.plugin_health import PluginHealthReader
from app.schemas.common import CamelModel
from app.schemas.platform import PluginEnabled, PluginList, PluginRead, PluginWrite

router = APIRouter(tags=["resources", "plugins"])
Store = Annotated[PlatformStore, Depends(get_platform_store)]


class ResourceList(CamelModel):
    items: list[ResourceRead]


@router.get("/resources", response_model=ResourceList)
def list_resources(store: Store) -> ResourceList:
    return ResourceList(
        items=[
            ResourceRead(resource_id=item["id"], **{k: v for k, v in item.items() if k != "id"})
            for item in store.list_resources()
        ]
    )


@router.post("/resources", response_model=ResourceRead)
def save_resource(payload: ResourceWrite, store: Store) -> ResourceRead:
    config = validate_resource(payload.kind, payload.config)
    result = store.save_resource(payload.resource_id, payload.kind, config, payload.credentials)
    return ResourceRead(resource_id=result["id"], **{k: v for k, v in result.items() if k != "id"})


@router.get("/plugins", response_model=PluginList)
def list_plugins(store: Store) -> PluginList:
    return PluginList(items=[_plugin_read(item) for item in store.list_plugins()])


def _plugin_read(record: dict[str, Any]) -> PluginRead:
    observation = PluginHealthReader(get_session_factory()).latest(
        record["pluginId"], record["release"].get("artifactDigest", "")
    )
    return PluginRead.model_validate({**record, "health": observation})


@router.post("/plugins", response_model=PluginRead)
def install_plugin(payload: PluginWrite, store: Store) -> PluginRead:
    return _plugin_read(
        store.install_plugin(
            payload.release.plugin_id,
            payload.release.model_dump(mode="json", by_alias=True),
            payload.enabled,
        )
    )


@router.patch("/plugins/{publisher}/{plugin}", response_model=PluginRead)
def enable_plugin(publisher: str, plugin: str, payload: PluginEnabled, store: Store) -> PluginRead:
    return _plugin_read(store.set_plugin_enabled(f"{publisher}/{plugin}", payload.enabled))
