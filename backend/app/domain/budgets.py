"""Per-Agent execution overrides, independent of immutable package definitions."""

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field, field_validator

from app.domain.definitions import Budget, Key, PackageDefinition
from app.schemas.common import CamelModel

if TYPE_CHECKING:
    from app.domain.execution import ResolvedRunSpec

PositiveInteger = Annotated[int, Field(strict=True, ge=1)]


class BudgetOverride(CamelModel):
    max_model_requests: Annotated[int, Field(strict=True, ge=1, le=1000)] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    max_tool_calls: Annotated[int, Field(strict=True, ge=1, le=10000)] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    max_tokens: PositiveInteger | Literal["unlimited"] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    max_output_tokens: PositiveInteger | Literal["auto", "provider_default"] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    deadline_seconds: Annotated[int, Field(strict=True, ge=1, le=86400)] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
    max_parallel_tools: Annotated[int, Field(strict=True, ge=1, le=128)] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )

    @field_validator("*", mode="before")
    @classmethod
    def reject_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Budget overrides must be omitted rather than null")
        return value


class ExecutionOptions(CamelModel):
    agent_budgets: dict[Key, BudgetOverride] = Field(default_factory=dict)


def resolve_agent_budgets(
    package: PackageDefinition,
    workflow_key: str,
    execution_options: ExecutionOptions,
) -> dict[str, Budget]:
    from app.domain.execution import ApplicationError

    agent_keys = {node.uses for node in package.workflows[workflow_key].nodes.values()}
    if set(execution_options.agent_budgets) - agent_keys:
        raise ApplicationError(
            "budget_agent_unavailable", "Budget overrides reference an unavailable task Agent"
        )
    result = {}
    for key in sorted(agent_keys):
        values = package.agents[key].budget.model_dump(mode="json", by_alias=True)
        values.setdefault("maxOutputTokens", "auto")
        override = execution_options.agent_budgets.get(key)
        if override is not None:
            values.update(override.model_dump(mode="json", by_alias=True))
        result[key] = Budget.model_validate(values)
    return result


def effective_execution_options(spec: "ResolvedRunSpec") -> ExecutionOptions:
    """Copy the frozen effective limits when reusing or rerunning a Run."""
    budgets = spec.effective_agent_budgets or resolve_agent_budgets(
        PackageDefinition.model_validate(spec.definition), spec.workflow_key, spec.execution_options
    )
    return ExecutionOptions(
        agent_budgets={
            key: BudgetOverride.model_validate(budget.model_dump(mode="json", by_alias=True))
            for key, budget in budgets.items()
        }
    )
