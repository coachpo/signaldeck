"""Publication keeps constraints observable at the same wire validation boundary."""

import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "runtime"))

from plugin_runtime.serialization import input_contract, model_wire_schema  # noqa: E402

from app.domain.schema_contract import (  # noqa: E402
    DomainValidationError,
    validate_schema,
    validate_value,
)


class LimitedOutput(BaseModel):
    values: list[int] = Field(min_length=2, max_length=3)


def test_array_cardinality_survives_plugin_publication() -> None:
    schema = model_wire_schema(LimitedOutput)
    validate_schema(schema)
    validate_value(schema, {"values": [1, 2]})
    for value in ([], [1], [1, 2, 3, 4]):
        with pytest.raises(DomainValidationError):
            validate_value(schema, {"values": value})


def test_explicit_open_model_cannot_publish_a_false_closed_contract() -> None:
    class OpenOutput(BaseModel):
        model_config = ConfigDict(extra="allow")
        label: str

    with pytest.raises(ValueError, match="unsupported_wire_map"):
        model_wire_schema(OpenOutput)


def test_input_union_does_not_silently_select_its_first_alternative() -> None:
    with pytest.raises(ValueError, match="unsupported_input_union"):
        input_contract({"type": ["string", "number", "null"]})
    assert input_contract({"type": ["string", "null"], "maxLength": 10}) == {
        "type": "string",
        "maxLength": 10,
    }
