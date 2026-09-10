"""Read frozen declarations and confirmed execution values without business inference."""

from typing import Any, Literal
from urllib.parse import urlencode, urljoin

from app.application.model_failure_projection import project_model_failure
from app.domain.definitions import DeterministicStrategy, PackageDefinition
from app.domain.execution import ExecutionEvidence, RunDetail
from app.domain.tool_contracts import PluginRelease
from app.schemas.task_experience import ResultAttachment, ResultRead, ResultSection

_MISSING = object()
_PACKED = object()


def selected(value: Any, path: list[str]) -> Any:
    for part in path:
        if isinstance(value, dict) and set(value) == {"$artifact"}:
            return _PACKED
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return _MISSING
    return value


def run_title(spec: dict[str, Any]) -> str:
    definition = spec.get("definition", {})
    workflow = definition.get("workflows", {}).get(spec["workflowKey"], {})
    title = (workflow.get("presentation") or {}).get("title")
    if title:
        value = (
            title.get("text")
            if title["kind"] == "static"
            else selected(spec.get("parameters"), title["ref"].split(".")[2:])
        )
        if isinstance(value, str) and value.strip():
            return value.strip()[:300]
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
    package = PackageDefinition.model_validate(run.spec.definition)
    workflow = package.workflows[run.workflow_key]
    evidence = sorted(
        run.evidence, key=lambda e: (e.finished_at or run.created_at, e.id), reverse=True
    )
    result.error_category = project_model_failure(run.error_code, evidence)
    confirmed = [e for e in evidence if e.status == "succeeded" and e.kind in {"node", "tool"}]

    def owner(item: ExecutionEvidence | None) -> ExecutionEvidence | None:
        if item is None or item.kind != "node":
            return item
        node = workflow.nodes.get(item.node_id)
        strategy = package.agents[node.uses].strategy if node else None
        if isinstance(strategy, DeterministicStrategy):
            return next(
                (
                    e
                    for e in confirmed
                    if e.kind == "tool"
                    and e.node_id == item.node_id
                    and e.tool_id == strategy.tool_id
                ),
                item,
            )
        return item

    def section(
        kind: Literal["markdown", "value", "receipt", "sources", "dataTime", "notice", "link"],
        label: str,
        value: Any,
        item: ExecutionEvidence | None = None,
        confirmed_owner: ExecutionEvidence | None = None,
        **kwargs: Any,
    ) -> ResultSection:
        owned = confirmed_owner or owner(item)
        return ResultSection(
            kind=kind,
            label=label,
            value=value,
            evidence_id=item.id if item else None,
            node_id=item.node_id if item else None,
            operation_id=owned.operation_id if owned else None,
            tool_evidence_id=owned.id if owned and owned.kind == "tool" else None,
            plugin_id=owned.tool_id.rsplit("/", 1)[0] if owned and owned.tool_id else None,
            **kwargs,
        )

    seen: set[tuple[str, str | None]] = set()

    def artifacts(value: Any, item: ExecutionEvidence | None = None) -> None:
        if isinstance(value, dict):
            if set(value) == {"$artifact"}:
                identity = (str(value["$artifact"]), item.id if item else None)
                if identity not in seen:
                    seen.add(identity)
                    owned = owner(item)
                    result.attachments.append(
                        ResultAttachment(
                            kind="artifact",
                            label="执行产物",
                            reference=value,
                            node_id=item.node_id if item else None,
                            operation_id=owned.operation_id if owned else None,
                            tool_evidence_id=owned.id if owned and owned.kind == "tool" else None,
                            evidence_id=item.id if item else None,
                            plugin_id=(
                                owned.tool_id.rsplit("/", 1)[0] if owned and owned.tool_id else None
                            ),
                        )
                    )
            else:
                for child in value.values():
                    artifacts(child, item)
        elif isinstance(value, list):
            for child in value:
                artifacts(child, item)

    artifacts(run.output)
    item: ExecutionEvidence | None
    for item in evidence:
        if item.status == "unknown" and item.kind != "attempt":
            result.unknown_evidence_ids.append(item.id)
        if item.kind == "node":
            if item.status == "skipped":
                result.skipped.append(item.node_id)
            elif item.status in {"failed", "blocked", "timed_out", "cancelled"}:
                result.execution_issues.append(f"{item.node_id}: {item.status}")
        cache = item.metadata.get("cacheProvenance")
        if cache is not None and cache not in result.freshness:
            result.freshness.append(cache)
    for item in confirmed:
        artifacts(item.output, item)
    presentation = workflow.model_dump(by_alias=True).get("presentation")
    if presentation:
        for declaration in presentation.get("sections", []):
            parts = declaration["ref"].split(".")
            item = None
            if parts[:2] == ["workflow", "output"]:
                value = (
                    selected(run.output, parts[2:])
                    if run.output is not None or run.status == "succeeded"
                    else _MISSING
                )
            else:
                item = next(
                    (e for e in confirmed if e.kind == "node" and e.node_id == parts[1]), None
                )
                value = selected(item.output, parts[3:]) if item else _MISSING
            href = None
            tool_evidence = None
            packed_binding = False
            if declaration["kind"] == "link":
                tool_id = declaration["toolId"]
                tool_evidence = next(
                    (
                        e
                        for e in confirmed
                        if e.kind == "tool" and e.node_id == parts[1] and e.tool_id == tool_id
                    ),
                    None,
                )
                if tool_evidence:
                    for raw in run.spec.plugin_releases:
                        release = PluginRelease.model_validate(raw)
                        tool = next((t for t in release.tools if t.tool_id == tool_id), None)
                        link = (
                            next(
                                (
                                    candidate
                                    for candidate in (tool.result_links or ())
                                    if candidate.key == declaration["linkKey"]
                                ),
                                None,
                            )
                            if tool
                            else None
                        )
                        if link and release.page_url:
                            query = {
                                key: selected(tool_evidence.output, ref.split(".")[2:])
                                for key, ref in link.query.items()
                            }
                            packed_binding = any(v is _PACKED for v in query.values())
                            if all(
                                v is not _MISSING
                                and v is not _PACKED
                                and not isinstance(v, (dict, list))
                                for v in query.values()
                            ):
                                href = urljoin(release.page_url.rstrip("/") + "/", link.path)
                                href += (
                                    (
                                        "?"
                                        + urlencode(
                                            {
                                                k: (
                                                    "null"
                                                    if v is None
                                                    else (
                                                        str(v).lower() if isinstance(v, bool) else v
                                                    )
                                                )
                                                for k, v in query.items()
                                            }
                                        )
                                    )
                                    if query
                                    else ""
                                )
                if href is None:
                    value = _PACKED if packed_binding else _MISSING
            if value is _PACKED or (isinstance(value, dict) and set(value) == {"$artifact"}):
                result.deferred_sections.append(declaration["label"])
                continue
            if value is _MISSING:
                if declaration.get("required") and run.status in {
                    "succeeded",
                    "failed",
                    "cancelled",
                }:
                    result.missing.append(declaration["label"])
                continue
            result.sections.append(
                section(
                    declaration["kind"],
                    declaration["label"],
                    value,
                    item,
                    confirmed_owner=tool_evidence,
                    href=href,
                    severity=declaration.get("severity"),
                )
            )
            if declaration["kind"] == "markdown" and result.body is None and isinstance(value, str):
                result.body = value
            elif declaration["kind"] == "receipt" and result.receipt is None:
                result.receipt = result.sections[-1].value
            elif (
                declaration["kind"] == "dataTime"
                and result.data_time is None
                and isinstance(value, str)
            ):
                result.data_time = value
            elif declaration["kind"] == "sources" and isinstance(value, list):
                result.sources.extend(value)
            if declaration["kind"] == "notice" and declaration.get("severity") == "missing":
                result.missing.extend(
                    str(v) for v in (value if isinstance(value, list) else [value])
                )
    else:
        if run.output is not None or run.status == "succeeded":
            result.sections.append(section("value", "工作流输出", run.output))
        for item in confirmed:
            result.sections.append(
                section("value", f"{item.node_id} · {item.kind}", item.output, item)
            )
    if result.unknown_evidence_ids:
        result.content_status = "unknown"
    elif result.sections or result.attachments:
        result.content_status = (
            "partial" if result.missing or run.status in {"failed", "cancelled"} else "available"
        )
    return result
