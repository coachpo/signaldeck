"""Controlled upstreams for real research DAG, MCP, SQL and schedule execution."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Request

from tests.fake_openai_provider import _prompted_schema, _schema_output
from tests.test_durable_runtime_support import serve_app

ROOT = Path(__file__).resolve().parents[2]
for directory in ("finance", "runtime", "digital_oracle"):
    sys.path.insert(0, str(ROOT / "plugins" / directory))

from finance_plugin import research_tools  # noqa: E402
from finance_plugin.config import FinanceSettings  # noqa: E402
from finance_plugin.main import create_app as finance_app  # noqa: E402
from finance_plugin.models.report import Report  # noqa: E402, F401
from finance_plugin.models.research_monitor import ResearchSnapshot  # noqa: E402, F401
from finance_plugin.research_collection import ResearchCollectionOutput  # noqa: E402
from oracle_plugin import main as oracle  # noqa: E402


@asynccontextmanager
async def plugins(database_url, monkeypatch, source):
    # Only upstream collection is controlled. Merge, validation, compilation, report
    # persistence and monitor transitions execute the production plugin handlers.
    def market(arguments, context):
        cutoff = datetime.fromisoformat(arguments["cutoffAt"].replace("Z", "+00:00"))
        now = datetime.now(UTC)
        evidence = dict(
            evidenceId="revenue",
            sourceId="filing",
            kind="fact",
            title="Revenue",
            url="https://www.sec.gov/Archives/revenue.htm",
            locator="Revenue table",
            retrievedAt=now,
            publishedAt=cutoff - timedelta(days=1),
            verified=True,
            sourceType="sec",
            symbol="NVDA",
            metric="revenue",
            value=source["value"],
            unit="USD",
        )
        # Publication is immutable across repeated observations, unlike retrieval.
        evidence["publishedAt"] = "2026-01-01T00:00:00Z"
        return ResearchCollectionOutput.model_validate(
            dict(
                evidence=[evidence],
                gaps=[],
                cutoffAt=cutoff,
                coverage=[
                    dict(
                        sourceId="sec",
                        complete=source["complete"],
                        observedAt=now,
                        evidenceIds=["revenue"],
                    )
                ],
            )
        )

    monkeypatch.setattr(research_tools, "execute_market", market)
    monkeypatch.setattr(
        oracle,
        "lookup_documents",
        lambda args: oracle.DocumentsResult(
            cutoff_at=args["cutoffAt"],
            documents=[],
            gaps=["Controlled document upstream unavailable"],
        ),
    )
    monkeypatch.setattr(
        oracle,
        "lookup_macro_evidence",
        lambda args: oracle.MacroEvidenceResult(
            cutoff_at=args["cutoffAt"],
            available_by_date=args["asOfDate"],
            gaps=["Controlled macro upstream unavailable"],
        ),
    )
    finance = finance_app(
        database_url, settings=FinanceSettings(quote_provider_backend="deterministic")
    )
    oracle_app = oracle.create_app()
    try:
        async with (
            finance.router.lifespan_context(finance),
            oracle_app.router.lifespan_context(oracle_app),
        ):
            async with serve_app(finance) as finance_url, serve_app(oracle_app) as oracle_url:
                async with httpx.AsyncClient() as client:
                    releases = []
                    for url in (finance_url, oracle_url):
                        release = (await client.get(url + "/release")).json()
                        release["endpoint"] = url + "/mcp/"
                        releases.append(release)
                yield finance, finance_url, releases
    finally:
        finance.state.engine.dispose()


@asynccontextmanager
async def models(calls):
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completion(request: Request):
        body = await request.json()
        calls.append(body)
        output = _schema_output(_prompted_schema(body), "Controlled qualitative analysis")
        prompt = json.loads(next(m["content"] for m in body["messages"] if m["role"] == "user"))
        for field in ("symbol", "asOfDate", "horizonMonths"):
            if field in output:
                output[field] = prompt["input"][field]
        if "claims" in output:
            evidence = next(
                item
                for item in prompt["input"]["evidence"]
                if item.get("metric") == "revenue" and item.get("value") is not None
            )
            output["claims"] = [
                dict(
                    claimId="revenue",
                    kind="fact",
                    metric="revenue",
                    formula="identity",
                    evidenceIds=[evidence["evidenceId"]],
                    value=evidence["value"],
                    unit="USD",
                )
            ]
            output["thresholds"] = []
        return dict(
            id="research",
            object="chat.completion",
            created=0,
            model="research",
            choices=[
                dict(
                    index=0,
                    message=dict(role="assistant", content=json.dumps(output)),
                    finish_reason="stop",
                )
            ],
            usage=dict(prompt_tokens=8, completion_tokens=8, total_tokens=16),
        )

    async with serve_app(app) as url:
        yield url + "/v1"


async def until(predicate, timeout=60):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.1)
