"""Static mapping assignability against the supported contract dialect."""

from __future__ import annotations

from typing import Any

from app.domain.mappings import mapping_references, resolve_mapping
from app.domain.schema_contract import reject, validate_value


def reference_schema(
    reference: str, namespace: dict[str, Any], path: str
) -> tuple[dict[str, Any], bool]:
    parts = reference.split(".")
    prefix_length = 3 if parts[0] == "nodes" else 2
    prefix = ".".join(parts[:prefix_length])
    if prefix not in namespace:
        reject("unknown_reference", path, "Reference does not exist in this scope")
    schema = namespace[prefix]
    optional = False
    for field in parts[prefix_length:]:
        if schema["type"] == "object" and field in schema.get("properties", {}):
            optional = optional or field not in schema.get("required", [])
            schema = schema["properties"][field]
        elif schema["type"] == "array" and field.isdigit():
            optional = optional or int(field) >= schema.get("minItems", 0)
            schema = schema["items"]
        else:
            reject(
                "unknown_reference", path, "Reference field does not exist in the declared schema"
            )
    return schema, optional


def _assignable(source: dict[str, Any], target: dict[str, Any], path: str) -> None:
    source_type, target_type = source["type"], target["type"]
    if source_type != target_type and (source_type, target_type) != ("integer", "number"):
        reject("mapping_type", path, "Source and destination types are incompatible")
    if "const" in target or "enum" in target:
        values = [source["const"]] if "const" in source else source.get("enum")
        if values is None:
            reject(
                "mapping_constraint",
                path,
                "Source does not guarantee the destination value constraint",
            )
        for value in values:
            validate_value(target, value, path)
    for minimum in ("minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties"):
        if minimum in target and (minimum not in source or source[minimum] < target[minimum]):
            reject(
                "mapping_constraint", path, "Source does not guarantee the destination lower bound"
            )
    for maximum in ("maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties"):
        if maximum in target and (maximum not in source or source[maximum] > target[maximum]):
            reject(
                "mapping_constraint", path, "Source does not guarantee the destination upper bound"
            )
    if "multipleOf" in target and source.get("multipleOf") != target["multipleOf"]:
        reject("mapping_constraint", path, "Source does not guarantee the destination multipleOf")
    if target.get("uniqueItems") and not source.get("uniqueItems"):
        reject("mapping_constraint", path, "Source does not guarantee unique items")
    if target_type == "object":
        source_fields, target_fields = source.get("properties", {}), target.get("properties", {})
        if set(source_fields) - set(target_fields):
            reject(
                "mapping_type", path, "Source contains fields outside the closed destination schema"
            )
        if set(target.get("required", [])) - set(source.get("required", [])):
            reject("mapping_type", path, "Source does not guarantee required destination fields")
        for name in source_fields:
            _assignable(source_fields[name], target_fields[name], f"{path}.{name}")
    if target_type == "array":
        _assignable(source["items"], target["items"], path + ".items")


def check_mapping(
    mapping: dict[str, Any], target: dict[str, Any], namespace: dict[str, Any], path: str = "$"
) -> None:
    if "value" in mapping:
        validate_value(target, mapping["value"], path + ".value")
        return
    if "ref" in mapping:
        source, optional = reference_schema(mapping["ref"], namespace, path + ".ref")
        _assignable(source, target, path + ".ref")
        if optional and "onMissing" not in mapping:
            reject("missing_mapping", path, "Optional source requires explicit onMissing mapping")
        if "onMissing" in mapping:
            check_mapping(mapping["onMissing"], target, namespace, path + ".onMissing")
        return
    if not mapping_references(mapping):
        validate_value(target, resolve_mapping(mapping, {}), path)
        return
    if "const" in target or "enum" in target:
        reject("mapping_constraint", path, "Dynamic composition cannot guarantee enum or const")
    if "object" in mapping:
        if target["type"] != "object":
            reject("mapping_type", path, "Object mapping requires object destination")
        fields = mapping["object"]
        properties = target.get("properties", {})
        if set(fields) - set(properties):
            reject("mapping_type", path, "Object mapping has unknown destination fields")
        if set(target.get("required", [])) - set(fields):
            reject("missing_mapping", path, "Required destination fields are not mapped")
        for name, child in fields.items():
            check_mapping(child, properties[name], namespace, f"{path}.object.{name}")
        for bound, check in (
            ("minProperties", len(fields) < target.get("minProperties", 0)),
            ("maxProperties", len(fields) > target.get("maxProperties", len(fields))),
        ):
            if check:
                reject("mapping_constraint", path, f"Object mapping violates {bound}")
        return
    if target["type"] != "array":
        reject("mapping_type", path, "Array mapping requires array destination")
    values = mapping["array"]
    if len(values) < target.get("minItems", 0) or len(values) > target.get("maxItems", len(values)):
        reject("mapping_constraint", path, "Array mapping violates length constraints")
    for index, child in enumerate(values):
        check_mapping(child, target["items"], namespace, f"{path}.array.{index}")
    if target.get("uniqueItems"):
        if not all("value" in child for child in values):
            reject("mapping_constraint", path, "Dynamic array mapping cannot guarantee uniqueItems")
        validate_value(target, [child["value"] for child in values], path)


def check_mapping_availability(
    mapping: dict[str, Any],
    namespace: dict[str, Any],
    path: str,
    missing_nodes: set[str] | None = None,
) -> None:
    """Require explicit handling wherever the declared source can be absent."""
    missing_nodes = missing_nodes or set()
    if "ref" in mapping:
        reference = mapping["ref"]
        _, optional = reference_schema(reference, namespace, path + ".ref")
        upstream_can_be_absent = (
            reference.startswith("nodes.") and reference.split(".")[1] in missing_nodes
        )
        if (optional or upstream_can_be_absent) and "onMissing" not in mapping:
            reject(
                "missing_mapping", path, "Potentially missing source requires explicit onMissing"
            )
        if "onMissing" in mapping:
            check_mapping_availability(
                mapping["onMissing"], namespace, path + ".onMissing", missing_nodes
            )
    elif "object" in mapping:
        for key, child in mapping["object"].items():
            check_mapping_availability(child, namespace, f"{path}.object.{key}", missing_nodes)
    elif "array" in mapping:
        for index, child in enumerate(mapping["array"]):
            check_mapping_availability(child, namespace, f"{path}.array.{index}", missing_nodes)
