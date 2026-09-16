"""Compose Finance research tools without adding business behavior to Core."""

import hashlib
from datetime import UTC, date, datetime

from plugin_runtime.common import CamelModel
from plugin_runtime.serialization import model_wire_schema, project
from plugin_runtime.server import tool
from pydantic import Field

from . import research_monitor
from .models.report import Report
from .research_collection import ResearchCollectionOutput, ResearchMergeInput, merge_evidence
from .research_evidence import ResearchReportInput, ResearchReportOutput
from .research_market import ResearchMarketInput, execute_market
from .research_report import compile_research_report
from .research_report_validation import NY, day_end
from .schemas.report import ReportRead

PREFIX = "signaldeck/finance/"


class ResearchScopeInput(CamelModel):
    symbol: str = Field(min_length=1, max_length=30)
    as_of_date: date


class ResearchScopeOutput(ResearchScopeInput):
    cutoff_at: datetime


class ResearchReportSave(CamelModel):
    name: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1)
    snapshot_id: str | None = Field(default=None, min_length=1, max_length=36)


READ_MODELS = {
    "research_scope_freeze": (ResearchScopeInput, ResearchScopeOutput, "冻结本次研究截止时间"),
    "research_market_evidence": (
        ResearchMarketInput,
        ResearchCollectionOutput,
        "采集行情与新闻证据",
    ),
    "research_evidence_merge": (ResearchMergeInput, ResearchCollectionOutput, "汇总来源与资料缺口"),
    "research_report_compile": (
        ResearchReportInput,
        ResearchReportOutput,
        "核对证据并生成研究报告",
    ),
}


def definitions():
    result = [
        tool(
            "signaldeck/finance",
            name,
            {**model_wire_schema(input_model), "title": title},
            model_wire_schema(output_model),
            title,
            resources=("finance-market-data",) if name == "research_market_evidence" else (),
        )
        for name, (input_model, output_model, title) in READ_MODELS.items()
    ]
    result.append(
        tool(
            "signaldeck/finance",
            "research_reports_create",
            {**model_wire_schema(ResearchReportSave), "title": "保存本次研究报告"},
            model_wire_schema(ReportRead),
            "Persist the canonical research body, optionally bound to an exact observation.",
            write=True,
            result_links=[
                {
                    "version": "signaldeck.resultLink/1",
                    "key": "report",
                    "label": "打开报告",
                    "path": "",
                    "query": {"reportId": "tool.output.id"},
                }
            ],
        )
    )
    return result + research_monitor.definitions()


def handles(name):
    short = name.removeprefix(PREFIX)
    return (
        short in READ_MODELS
        or short in research_monitor.CONTRACTS
        or short == "research_reports_create"
    )


def execute(name, arguments, invocation, context, journal):
    short = name.removeprefix(PREFIX)
    if short in research_monitor.CONTRACTS:
        return research_monitor.execute(name, arguments, invocation, journal)
    if short == "research_reports_create":
        return save_report(name, arguments, invocation, journal)
    if short == "research_report_compile":
        return compile_research_report(arguments)
    payload = READ_MODELS[short][0].model_validate(arguments)
    if short == "research_scope_freeze":
        now = datetime.now(UTC)
        if payload.as_of_date > now.astimezone(NY).date():
            raise ValueError("research_date_is_in_the_future")
        result = ResearchScopeOutput(
            symbol=payload.symbol.upper(),
            as_of_date=payload.as_of_date,
            cutoff_at=min(day_end(payload.as_of_date), now),
        )
    elif short == "research_market_evidence":
        binding = invocation.get("resourceBindings", {}).get("finance-market-data", {})
        allowed = binding.get("allowedSymbols", [])
        if (
            "finance-market-data" not in invocation.get("resourceGrants", [])
            or payload.symbol.upper() not in allowed
        ):
            raise ValueError("finance_symbol_not_granted")
        result = execute_market(arguments, context)
    elif short == "research_evidence_merge":
        result = merge_evidence(payload)
    return project(result.model_dump(mode="json", by_alias=True))


def save_report(name, arguments, invocation, journal):
    payload = ResearchReportSave.model_validate(arguments)

    def effect(session):
        if payload.snapshot_id:
            research_monitor.validate_report_snapshot(session, payload.snapshot_id, invocation)
        identity = hashlib.sha256(invocation["operationId"].encode()).hexdigest()[:32]
        metadata = {
            "createdBy": {
                "type": "agent",
                **{
                    key: invocation[key]
                    for key in ("runId", "nodeId", "invocationId", "operationId")
                },
            }
        }
        if payload.snapshot_id:
            metadata["researchSnapshotId"] = payload.snapshot_id
        record = Report(
            name=payload.name + "_" + identity,
            slug="agent_" + identity,
            source="agent",
            content=payload.content,
            metadata_=metadata,
        )
        session.add(record)
        session.flush()
        return project(ReportRead.model_validate(record).model_dump(mode="json", by_alias=True))

    return journal.write(
        invocation["operationId"],
        name,
        arguments,
        effect,
        scope=invocation.get("resourceBindings", {}),
    )
