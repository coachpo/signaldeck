"""Optional external Workflow Package data; no definitions are embedded in Core."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.application.package_import import ImportStore, import_source
from app.domain.definition_parser import parse_package_source
from app.domain.definitions import CompiledPackage


@dataclass(frozen=True)
class SeedPackage:
    source: str
    compiled: CompiledPackage


def load_seed_packages(directory: str | Path | None = None) -> tuple[SeedPackage, ...]:
    """Explicit directory reader for data contract tooling; never infer a checkout."""
    if not directory:
        return ()
    return tuple(
        SeedPackage(source, parse_package_source(source))
        for path in _paths(directory)
        for source in [path.read_text(encoding="utf-8")]
    )


def _paths(directory: str | Path) -> list[Path]:
    root = Path(directory)
    return sorted({*root.glob("*.yaml"), *root.glob("*.yml")})


def seed_packages(store: ImportStore, directory: str | Path | None = None) -> list[dict[str, Any]]:
    """Import each optional source independently, atomically preserving existing keys."""
    if not directory:
        return []
    try:
        paths = _paths(directory)
    except OSError:
        return [
            {
                "status": "error",
                "diagnostics": [
                    {
                        "code": "data_directory_unreadable",
                        "path": "$",
                        "message": "Workflow data directory is unavailable",
                    }
                ],
            }
        ]
    results = []
    for path in paths:
        try:
            result = import_source(store, path.read_text(encoding="utf-8"), missing_only=True)
        except (OSError, UnicodeError):
            result = {
                "status": "error",
                "diagnostics": [
                    {
                        "code": "data_source_unreadable",
                        "path": "$",
                        "message": "Workflow data source is unavailable",
                    }
                ],
            }
        results.append({"name": path.name, **result})
    return results
