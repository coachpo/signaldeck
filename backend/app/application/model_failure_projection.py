"""Only attribute a safe model category to the failures responsible for a Run error."""

from collections.abc import Sequence
from typing import cast

from app.domain.execution import ExecutionEvidence
from app.domain.model_diagnostics import MODEL_ERROR_CATEGORIES, ModelErrorCategory


def project_model_failure(
    error_code: str | None, evidence: Sequence[ExecutionEvidence]
) -> ModelErrorCategory | None:
    if not error_code:
        return None
    failed_nodes = {
        (e.node_id, e.error_code) for e in evidence if e.kind == "node" and e.status == "failed"
    }
    failures = [
        e
        for e in evidence
        if e.kind == "model"
        and e.status == "failed"
        and (
            e.error_code == error_code
            or (error_code == "workflow_nodes_failed" and (e.node_id, e.error_code) in failed_nodes)
        )
    ]
    categories = {
        (
            e.metadata["errorCategory"]
            if isinstance(e.metadata.get("errorCategory"), str)
            else "unclassified"
        )
        for e in failures
    }
    if len(categories) == 1:
        category = categories.pop()
        if category in MODEL_ERROR_CATEGORIES:
            return cast(ModelErrorCategory, category)
    return None
