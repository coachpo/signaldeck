"""Plugin wire projection: absent nullable fields, decimal strings and finite records."""

import dataclasses
from datetime import date, datetime
from decimal import Decimal

from .common import to_camel
from .server import obj


def project(value):
    if dataclasses.is_dataclass(value):
        return project(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {to_camel(k): project(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [project(v) for v in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def model_wire_schema(model):
    """Declare the wire representation, which intentionally omits null fields.

    Date/time fields are ISO strings validated by the provider's typed projection;
    decimal values are string fields. Dynamic warning details become key/value records.
    Unsupported model unions fail publication rather than widening the contract.
    """
    schema = model.model_json_schema(mode="validation", by_alias=False)
    definitions = schema.get("$defs", {})

    def build(node):
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            if name == "RuntimeToolWarning":
                return obj(
                    {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "details": {
                            "type": "array",
                            "items": obj(
                                {
                                    "key": {"type": "string"},
                                    "value": {"type": "string"},
                                },
                                ("key", "value"),
                            ),
                        },
                    },
                    ("code", "message", "details"),
                )
            return build(definitions[name])
        if "anyOf" in node:
            options = [p for p in node["anyOf"] if p.get("type") != "null"]
            if len(options) != 1:
                if {p.get("type") for p in options} <= {"number", "string"}:
                    return {"type": "string"}
                raise ValueError("unsupported_wire_union")
            return build(options[0])
        if node.get("type") == "object":
            if node.get("additionalProperties") is True or isinstance(
                node.get("additionalProperties"), dict
            ):
                raise ValueError("unsupported_wire_map")
            props = {
                to_camel(k): build(v) for k, v in node.get("properties", {}).items()
            }
            required = [
                k
                for k in node.get("required", [])
                if not any(
                    p.get("type") == "null"
                    for p in node["properties"][k].get("anyOf", [])
                )
            ]
            constraints = {
                key: value
                for key, value in node.items()
                if key
                not in {
                    "type",
                    "properties",
                    "required",
                    "additionalProperties",
                    "$defs",
                    "title",
                    "default",
                }
            }
            return {**obj(props, [to_camel(k) for k in required]), **constraints}
        if node.get("type") == "array":
            return {
                **{
                    key: value
                    for key, value in node.items()
                    if key not in {"items", "title", "default", "$defs"}
                },
                "items": build(node["items"]),
            }
        return {
            k: v
            for k, v in node.items()
            if k not in {"title", "default", "format", "$defs"}
        }

    return build(schema)


def input_contract(node):
    """New contract omits nullable arguments; provider parsers supply existing defaults."""
    result = {k: v for k, v in node.items() if k != "additionalProperties"}
    if isinstance(result.get("type"), list):
        alternatives = [kind for kind in result["type"] if kind != "null"]
        if len(alternatives) != 1:
            raise ValueError("unsupported_input_union")
        result["type"] = alternatives[0]
    if "enum" in result:
        result["enum"] = [v for v in result["enum"] if v is not None]
    if result.get("type") == "object":
        properties = node.get("properties", {})
        result["properties"] = {k: input_contract(v) for k, v in properties.items()}
        result["required"] = [
            k
            for k in node.get("required", [])
            if not isinstance(properties[k].get("type"), list)
        ]
        result["unevaluatedProperties"] = False
    if result.get("type") == "array":
        result["items"] = input_contract(result["items"])
    return result
