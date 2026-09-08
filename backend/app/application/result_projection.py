"""Conservative business reading of immutable run output and execution evidence."""

from typing import Any

from app.domain.definitions import DeterministicStrategy, PackageDefinition
from app.domain.execution import RunDetail
from app.schemas.task_experience import ResultAttachment, ResultRead


def run_title(spec: dict[str, Any]) -> str:
    parameters = spec.get("parameters")
    if isinstance(parameters, dict):
        for key in ("title", "question"):
            value = parameters.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
    definition = spec.get("definition", {})
    workflow = definition.get("workflows", {}).get(spec["workflowKey"], {})
    return str(
        workflow.get("name") or definition.get("metadata", {}).get("name") or spec["workflowKey"]
    )


def project_result(run: RunDetail) -> ResultRead:
    result = ResultRead(
        run_id=run.id,
        title=run.title or run_title(run.spec.model_dump(by_alias=True)),
        status=run.status,
        content_status="not_available",
        created_at=run.created_at,
        finished_at=run.finished_at,
        cancel_requested_at=run.cancel_requested_at,
        origin=run.origin,
        error_code=run.error_code,
    )
    values: list[tuple[Any, str | None, str | None]] = [(run.output, None, None)]
    package = PackageDefinition.model_validate(run.spec.definition)
    workflow = package.workflows[run.workflow_key]
    # Node output is the confirmed application-level contract. Model text is not
    # promoted while its containing node is unfinished or failed.
    for evidence in sorted(
        run.evidence, key=lambda item: (item.finished_at or run.created_at, item.id), reverse=True
    ):
        if evidence.status == "unknown" and evidence.kind != "attempt":
            result.unknown_evidence_ids.append(evidence.id)
        if evidence.kind == "node" and evidence.status in {
            "failed",
            "blocked",
            "skipped",
            "timed_out",
            "cancelled",
        }:
            result.missing.append(f"{evidence.node_id}: {evidence.status}")
        if evidence.status == "succeeded" and evidence.kind in {"node", "tool"}:
            owner = evidence.tool_id
            identity = evidence.id
            node = workflow.nodes.get(evidence.node_id)
            if evidence.kind == "node" and node is not None:
                strategy = package.agents[node.uses].strategy
                if isinstance(strategy, DeterministicStrategy):
                    confirmed = next(
                        (
                            item
                            for item in run.evidence
                            if item.kind == "tool"
                            and item.node_id == evidence.node_id
                            and item.tool_id == strategy.tool_id
                            and item.status == "succeeded"
                        ),
                        None,
                    )
                    if confirmed is not None:
                        # The frozen deterministic mapping owns the public node receipt,
                        # including renamed IDs or a large tool result retained as an artifact.
                        owner, identity = confirmed.tool_id, confirmed.id
            values.append((evidence.output, identity, owner))
        cache = evidence.metadata.get("cacheProvenance")
        if cache is not None and cache not in result.freshness:
            result.freshness.append(cache)
    seen: set[str] = set()
    for value, evidence_id, tool_id in values:
        if not isinstance(value, dict):
            if isinstance(value, str) and result.body is None:
                result.body = value
            continue
        if "$artifact" in value and len(value) == 1:
            identity = str(value["$artifact"])
            if identity not in seen:
                seen.add(identity)
                result.attachments.append(
                    ResultAttachment(
                        kind="artifact",
                        label="执行产物",
                        reference=value["$artifact"],
                        evidence_id=evidence_id,
                    )
                )
            continue
        for key in ("content", "text", "markdown"):
            if result.body is None and isinstance(value.get(key), str):
                result.body = value[key]
        if result.data_time is None:
            for key in ("dataTime", "asOf", "observedAt", "fetchedAt"):
                if isinstance(value.get(key), str):
                    result.data_time = value[key]
                    break
        for key in ("sources", "quotes"):
            if isinstance(value.get(key), list):
                for source in value[key]:
                    if source not in result.sources:
                        result.sources.append(source)
        for key in ("missing", "warnings"):
            if isinstance(value.get(key), list):
                for item in value[key]:
                    message = item.get("message") if isinstance(item, dict) else item
                    if isinstance(message, str) and message not in result.missing:
                        result.missing.append(message)
        if tool_id:
            for attachment in result.attachments:
                reference = attachment.reference
                if isinstance(reference, dict) and (
                    (
                        attachment.kind == "report"
                        and "reportId" in value
                        and reference.get("reportId") == value["reportId"]
                    )
                    or (
                        attachment.kind == "note"
                        and "collection" in value
                        and reference.get("id") == value.get("id")
                    )
                ):
                    attachment.plugin_id = tool_id.rsplit("/", 1)[0]
                    attachment.evidence_id = evidence_id
                    attachment.reference = {**reference, **value}
        if "reportId" in value:
            identity = "report:" + str(value["reportId"])
            if identity not in seen:
                seen.add(identity)
                result.attachments.append(
                    ResultAttachment(
                        kind="report",
                        label=str(value.get("name") or "报告"),
                        reference=value,
                        evidence_id=evidence_id,
                        plugin_id=tool_id.rsplit("/", 1)[0] if tool_id else None,
                    )
                )
                if result.receipt is None:
                    result.receipt = value
        if "collection" in value and "id" in value:
            identity = "note:" + str(value["id"])
            if identity not in seen:
                seen.add(identity)
                result.attachments.append(
                    ResultAttachment(
                        kind="note",
                        label=str(value.get("title") or "笔记"),
                        reference=value,
                        evidence_id=evidence_id,
                        plugin_id=tool_id.rsplit("/", 1)[0] if tool_id else None,
                    )
                )
                if result.receipt is None:
                    result.receipt = value
    parameters = run.spec.parameters
    if isinstance(parameters, dict) and parameters.get("includeRisk") is False:
        result.missing.append("本次未启用风险分析")
    if result.unknown_evidence_ids:
        result.content_status = "unknown"
        result.missing.append("部分操作的实际效果尚未确认，请先核实再决定是否重新执行")
    elif result.body is not None or result.attachments or result.receipt is not None:
        result.content_status = (
            "partial" if result.missing or run.status != "succeeded" else "available"
        )
    return result
