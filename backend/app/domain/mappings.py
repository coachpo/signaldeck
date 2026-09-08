"""Finite declarative value resolution, without code execution or I/O."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from app.domain.schema_contract import reject

_REFERENCE = re.compile(
    r"^(?:workflow\.input|nodes\.[a-z][a-z0-9_-]*\.output|agent\.input|tool\.output)"
    r"(?:\.[A-Za-z_][A-Za-z0-9_-]*|\.[0-9]+)*$"
)
MISSING = object()


def validate_mapping(mapping: Any, path: str = "$") -> None:
    if not isinstance(mapping, dict):
        reject("invalid_mapping", path, "Mapping must be an expression object")
    kinds = set(mapping) & {"ref", "value", "object", "array"}
    if len(kinds) != 1:
        reject("invalid_mapping", path, "Exactly one mapping expression is required")
    kind = next(iter(kinds))
    if set(mapping) - {kind, *({"onMissing"} if kind == "ref" else set())}:
        reject("invalid_mapping", path, "Unknown mapping fields")
    if kind == "value":
        try:
            json.dumps(mapping["value"], allow_nan=False)
        except (TypeError, ValueError):
            reject("invalid_mapping", path, "Constants must contain finite JSON values")
    if kind == "ref":
        if not isinstance(mapping[kind], str) or not _REFERENCE.fullmatch(mapping[kind]):
            reject("invalid_reference", path + ".ref", "Unsupported reference syntax")
        if "onMissing" in mapping:
            validate_mapping(mapping["onMissing"], path + ".onMissing")
    elif kind == "object":
        if not isinstance(mapping[kind], dict):
            reject("invalid_mapping", path, "Object mapping fields must be an object")
        for key, value in mapping[kind].items():
            if not isinstance(key, str):
                reject("invalid_mapping", path, "Object field names must be strings")
            validate_mapping(value, f"{path}.object.{key}")
    elif kind == "array":
        if not isinstance(mapping[kind], list):
            reject("invalid_mapping", path, "Array mapping items must be an array")
        for index, value in enumerate(mapping[kind]):
            validate_mapping(value, f"{path}.array.{index}")


def mapping_references(mapping: dict[str, Any], path: str = "$") -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if "ref" in mapping:
        result.append((mapping["ref"], path + ".ref"))
        if "onMissing" in mapping:
            result.extend(mapping_references(mapping["onMissing"], path + ".onMissing"))
    elif "object" in mapping:
        for key, child in mapping["object"].items():
            result.extend(mapping_references(child, f"{path}.object.{key}"))
    elif "array" in mapping:
        for index, child in enumerate(mapping["array"]):
            result.extend(mapping_references(child, f"{path}.array.{index}"))
    return result


def resolve_reference(reference: str, namespace: dict[str, Any]) -> Any:
    value: Any = namespace
    for part in reference.split("."):
        if isinstance(value, dict):
            value = value.get(part, MISSING)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return MISSING
        if value is MISSING:
            return MISSING
    return value


def resolve_mapping(mapping: dict[str, Any], namespace: dict[str, Any], path: str = "$") -> Any:
    validate_mapping(mapping, path)
    if "value" in mapping:
        return copy.deepcopy(mapping["value"])
    if "ref" in mapping:
        result = resolve_reference(mapping["ref"], namespace)
        if result is not MISSING:
            return copy.deepcopy(result)
        if "onMissing" in mapping:
            return resolve_mapping(mapping["onMissing"], namespace, path + ".onMissing")
        reject(
            "missing_output", path, "Referenced value is unavailable; explicit onMissing required"
        )
    if "object" in mapping:
        return {
            key: resolve_mapping(child, namespace, f"{path}.object.{key}")
            for key, child in mapping["object"].items()
        }
    return [
        resolve_mapping(child, namespace, f"{path}.array.{index}")
        for index, child in enumerate(mapping["array"])
    ]


def validate_condition(condition: Any, path: str = "$") -> None:
    if not isinstance(condition, dict) or set(condition) != {"op", "args"}:
        reject("invalid_condition", path, "Condition requires op and args")
    op, args = condition["op"], condition["args"]
    if (
        not isinstance(args, list)
        or not isinstance(op, str)
        or op
        not in {
            "eq",
            "ne",
            "lt",
            "lte",
            "gt",
            "gte",
            "exists",
            "all",
            "any",
            "not",
        }
    ):
        reject("invalid_condition", path, "Unsupported condition operator or arguments")
    arity = 1 if op in {"exists", "not"} else 2
    if op not in {"all", "any"} and len(args) != arity:
        reject("invalid_condition", path, "Incorrect condition argument count")
    if op in {"all", "any"} and not args:
        reject("invalid_condition", path, "Boolean group must not be empty")
    for index, arg in enumerate(args):
        validator = validate_condition if op in {"all", "any", "not"} else validate_mapping
        validator(arg, f"{path}.args.{index}")


def condition_references(condition: dict[str, Any], path: str = "$") -> list[tuple[str, str]]:
    collect = (
        condition_references if condition["op"] in {"all", "any", "not"} else mapping_references
    )
    return [
        reference
        for index, arg in enumerate(condition["args"])
        for reference in collect(arg, f"{path}.args.{index}")
    ]


def evaluate_condition(condition: dict[str, Any], namespace: dict[str, Any]) -> bool:
    validate_condition(condition)
    op, args = condition["op"], condition["args"]
    if op == "all":
        return all(evaluate_condition(arg, namespace) for arg in args)
    if op == "any":
        return any(evaluate_condition(arg, namespace) for arg in args)
    if op == "not":
        return not evaluate_condition(args[0], namespace)
    if op == "exists":
        try:
            resolve_mapping(args[0], namespace)
        except ValueError:
            return False
        return True
    left, right = (resolve_mapping(arg, namespace) for arg in args)
    if op in {"eq", "ne"}:
        equal = _equal(left, right)
        return equal if op == "eq" else not equal
    if isinstance(left, str) and isinstance(right, str):
        comparison = (left > right) - (left < right)
    elif (
        isinstance(left, (int, float))
        and isinstance(right, (int, float))
        and type(left) is not bool
        and type(right) is not bool
    ):
        comparison = (left > right) - (left < right)
    else:
        reject("invalid_condition", "$", "Ordered comparison requires compatible scalar values")
    return {
        "lt": comparison < 0,
        "lte": comparison <= 0,
        "gt": comparison > 0,
        "gte": comparison >= 0,
    }[op]


def _equal(left: Any, right: Any) -> bool:
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return bool(left == right)
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _equal(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_equal(left[key], right[key]) for key in left)
    return bool(left == right)
