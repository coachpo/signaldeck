"""Isolate invalid model assertions while keeping the source/outer contract strict."""

from typing import Annotated

from finance_plugin.research_evidence import (
    ResearchClaim,
    ResearchReportInput,
    ResearchThreshold,
)
from pydantic import TypeAdapter, ValidationError


def parse_report_input(arguments: dict) -> tuple[ResearchReportInput, list[str]]:
    if not isinstance(arguments, dict):
        return ResearchReportInput.model_validate(arguments), []
    # Validate all source records and outer fields before considering assertions.
    # Only the model-authored item collections have recoverable business errors.
    request = ResearchReportInput.model_validate({**arguments, "claims": [], "thresholds": []})
    gaps = []
    for name, item_model in (("claims", ResearchClaim), ("thresholds", ResearchThreshold)):
        field = ResearchReportInput.model_fields[name]
        collection_type = Annotated[list[object], *field.metadata]
        items = TypeAdapter(collection_type).validate_python(arguments.get(name, []), strict=True)
        accepted = []
        for index, item in enumerate(items, start=1):
            try:
                accepted.append(item_model.model_validate(item))
            except ValidationError as error:
                # Never echo rejected values, arbitrary unknown keys or validator
                # exception text into reports. Known field names aid correction.
                known_fields = {
                    field.alias or key for key, field in item_model.model_fields.items()
                }
                fields = sorted(
                    {
                        str(part)
                        for detail in error.errors(include_input=False, include_context=False)
                        for part in detail["loc"]
                        if str(part) in known_fields
                    }
                )
                detail = f" ({', '.join(fields)})" if fields else ""
                gaps.append(f"{name}[{index}]: invalid structured item{detail}")
        setattr(request, name, accepted)
    return request, gaps
