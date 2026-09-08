"""Store immutable canonical revisions of operator-authored Workflow Packages."""

import json
from io import StringIO
from typing import Any, Protocol

from ruamel.yaml import YAML

from app.domain.definition_parser import parse_package_source
from app.domain.execution import ApplicationError


class DefinitionStore(Protocol):
    def get_package(
        self, package_key: str, revision_hash: str | None = None
    ) -> dict[str, Any] | None: ...

    def save_package(
        self,
        package_key: str,
        source: str,
        definition: dict[str, Any],
        plan: dict[str, Any],
        package_hash: str,
    ) -> dict[str, Any]: ...


def save_definition(
    store: DefinitionStore, source: str, *, expected_key: str | None = None
) -> dict[str, Any]:
    compiled = parse_package_source(source)
    key = compiled.package.metadata.key
    if expected_key is not None:
        if key != expected_key:
            raise ApplicationError(
                "package_key_conflict", "Package key cannot change during an update"
            )
        if store.get_package(expected_key) is None:
            raise ApplicationError(
                "package_not_found", "Workflow Package is unavailable", status=404
            )
    definition = compiled.package.model_dump(mode="json", by_alias=True)
    return store.save_package(
        key,
        canonical_source(definition),
        definition,
        {key: plan.model_dump(mode="json", by_alias=True) for key, plan in compiled.plans.items()},
        compiled.content_hash,
    )


def canonical_source(definition: dict[str, Any]) -> str:
    # Content identity excludes YAML layout. Equivalent edits and bundled seeds
    # must store identical source bytes for the same immutable content revision.
    stream = StringIO()
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.dump(json.loads(json.dumps(definition, sort_keys=True)), stream)
    return stream.getvalue()
