"""The supported, closed JSON Schema 2020-12 contract dialect."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_SUBSET_VERSION = "signaldeck.schema/1"
_COMMON = {"$schema", "type", "title", "description", "enum", "const"}
_TYPED = {
    "object": {"properties", "required", "unevaluatedProperties", "minProperties", "maxProperties"},
    "array": {"items", "minItems", "maxItems", "uniqueItems"},
    "string": {"minLength", "maxLength"},
    "integer": {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"},
    "number": {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"},
    "boolean": set(),
    "null": set(),
}


@dataclass(frozen=True)
class Diagnostic:
    code: str
    path: str
    message: str
    line: int | None = None
    column: int | None = None


class DomainValidationError(ValueError):
    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in diagnostics))


def reject(code: str, path: str, message: str) -> NoReturn:
    raise DomainValidationError([Diagnostic(code, path, message)])


def validate_schema(schema: dict[str, Any], path: str = "$") -> None:
    """Reject unsupported keywords rather than letting validators ignore them."""
    if not isinstance(schema, dict):
        reject("invalid_schema", path, "Schema must be an object")
    if any(not isinstance(key, str) for key in schema):
        reject("invalid_schema", path, "Schema field names must be strings")
    kind = schema.get("type")
    if not isinstance(kind, str) or kind not in _TYPED:
        reject("invalid_schema", path + ".type", "A single supported type is required")
    unknown = set(schema) - _COMMON - _TYPED[kind]
    if unknown:
        reject("unsupported_schema", path + "." + sorted(unknown)[0], "Unsupported schema keyword")
    if "$schema" in schema and schema["$schema"] != DIALECT:
        reject("unsupported_schema", path + ".$schema", "Only JSON Schema 2020-12 is supported")
    try:
        json.dumps(schema, allow_nan=False)
        Draft202012Validator.check_schema(schema)
    except (SchemaError, TypeError, ValueError):
        reject("invalid_schema", path, "Invalid JSON Schema constraint")
    if kind == "object":
        if schema.get("unevaluatedProperties", False) is not False:
            reject("open_schema", path, "Object schemas are closed")
        properties = schema.get("properties", {})
        if "$artifact" in properties:
            reject(
                "reserved_schema_field",
                path + ".properties.$artifact",
                "Field is reserved for internal artifact references",
            )
        for key, child in properties.items():
            validate_schema(child, f"{path}.properties.{key}")
        if set(schema.get("required", [])) - set(properties):
            reject("invalid_schema", path + ".required", "Required fields must exist in properties")
    if kind == "array":
        if "items" not in schema:
            reject("invalid_schema", path + ".items", "Array item schema is required")
        validate_schema(schema["items"], path + ".items")


def materialize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make the dialect's implicit object closure explicit for external validators."""
    validate_schema(schema)
    result = copy.deepcopy(schema)
    if result["type"] == "object":
        result["unevaluatedProperties"] = False
        result["properties"] = {
            key: materialize_schema(value) for key, value in result.get("properties", {}).items()
        }
    elif result["type"] == "array":
        result["items"] = materialize_schema(result["items"])
    return result


def validate_value(schema: dict[str, Any], value: Any, path: str = "$") -> None:
    prepared = materialize_schema(schema)
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        reject("invalid_value", path, "Value must be finite JSON")
    errors = sorted(Draft202012Validator(prepared).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        # Validator messages include input values; expose only structural locations and rules.
        raise DomainValidationError(
            [
                Diagnostic(
                    "invalid_value",
                    path + "".join(f".{part}" for part in error.absolute_path),
                    f"Value violates {error.validator} constraint",
                )
                for error in errors
            ]
        )
