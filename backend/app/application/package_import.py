"""Independent source import using the ordinary immutable definition contract."""

from dataclasses import asdict
from typing import Any, Protocol

from app.application.definitions import canonical_source
from app.domain.definition_parser import parse_package_source
from app.domain.execution import ApplicationError
from app.domain.schema_contract import DomainValidationError


class ImportStore(Protocol):
    def import_package(
        self,
        package_key: str,
        source: str,
        definition: dict[str, Any],
        plan: dict[str, Any],
        package_hash: str,
        *,
        missing_only: bool,
    ) -> str: ...


def import_source(store: ImportStore, source: str, *, missing_only: bool) -> dict[str, Any]:
    """A rejected item does not prevent other sources from being imported."""
    try:
        compiled = parse_package_source(source)
        definition = compiled.package.model_dump(mode="json", by_alias=True)
        key = compiled.package.metadata.key
        outcome = store.import_package(
            key,
            canonical_source(definition),
            definition,
            {
                name: plan.model_dump(mode="json", by_alias=True)
                for name, plan in compiled.plans.items()
            },
            compiled.content_hash,
            missing_only=missing_only,
        )
        return {"packageKey": key, "status": outcome}
    except DomainValidationError as exc:
        return {"status": "error", "diagnostics": [asdict(item) for item in exc.diagnostics]}
    except ApplicationError as exc:
        return {
            "status": "error",
            "diagnostics": [{"code": exc.code, "path": "$", "message": exc.message}],
        }
