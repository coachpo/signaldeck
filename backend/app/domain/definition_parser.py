"""Safe YAML source ingestion with source-located definition diagnostics."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.events import AliasEvent

from app.domain.compiler import compile_package
from app.domain.definitions import CompiledPackage
from app.domain.schema_contract import Diagnostic, DomainValidationError, reject


def parse_package_source(source: str) -> CompiledPackage:
    if len(source.encode("utf-8")) > 2_000_000:
        reject("source_limit", "$", "Package source exceeds 2 MB")
    yaml = YAML(typ="rt")
    yaml.allow_duplicate_keys = False
    data: Any = None
    try:
        for event in yaml.parse(source):
            if isinstance(event, AliasEvent) or getattr(event, "anchor", None):
                mark = event.start_mark
                raise DomainValidationError(
                    [
                        Diagnostic(
                            "unsafe_yaml",
                            "$",
                            "YAML anchors and aliases are not supported",
                            mark.line + 1,
                            mark.column + 1,
                        )
                    ]
                )
            if getattr(event, "tag", None):
                reject("unsafe_yaml", "$", "Explicit YAML tags are not supported")
        data = yaml.load(source)
        json.dumps(data, allow_nan=False)
        if not isinstance(data, dict):
            reject("invalid_definition", "$", "Package source must be an object")
        return compile_package(data)
    except DomainValidationError as error:
        raise DomainValidationError([_locate(item, data) for item in error.diagnostics]) from None
    except MarkedYAMLError as error:
        mark = error.problem_mark
        raise DomainValidationError(
            [
                Diagnostic(
                    "invalid_yaml",
                    "$",
                    "Malformed YAML or duplicate key",
                    mark.line + 1 if mark else None,
                    mark.column + 1 if mark else None,
                )
            ]
        ) from None
    except (YAMLError, TypeError, ValueError, RecursionError):
        reject("invalid_yaml", "$", "Source must contain finite JSON-compatible YAML values")
    raise AssertionError("unreachable")


def _locate(diagnostic: Diagnostic, data: Any) -> Diagnostic:
    if diagnostic.line is not None:
        return diagnostic
    current = data
    location: tuple[int, int] | None = None
    for part in diagnostic.path.removeprefix("$.").split("."):
        try:
            if isinstance(current, dict):
                location = current.lc.key(part) if hasattr(current, "lc") else location
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                location = current.lc.item(index) if hasattr(current, "lc") else location
                current = current[index]
            else:
                break
        except (KeyError, IndexError, TypeError, AttributeError):
            break
    return (
        replace(diagnostic, line=location[0] + 1, column=location[1] + 1)
        if location
        else diagnostic
    )
