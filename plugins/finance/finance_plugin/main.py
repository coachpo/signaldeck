"""Finance composition root: its database, providers, MCP tools and business pages."""

import hashlib
import json
import os
from pathlib import Path

from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from plugin_runtime.errors import ApiError
from plugin_runtime.operations import Journal, OperationBase
from plugin_runtime.serialization import input_contract, model_wire_schema, project
from plugin_runtime.server import application, obj, release, tool
from plugin_runtime.web import mount_shared_ui
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import runtime_market_data as market
from . import runtime_types
from .api import reports, templates
from .config import FinanceSettings
from .contracts import RuntimeToolContext
from .models.base import Base
from .models.report import Report
from .provider_factory import (
    create_news_providers,
    create_quote_provider,
    create_social_sentiment_adapters,
)
from .runtime_reports import REPORT_LOOKUP_TOOL_SPEC
from .schemas.report import ReportRead


def create_app(database_url=None, quote_provider=None, *, settings: FinanceSettings | None = None):
    provider_settings = settings or FinanceSettings()
    db_url = database_url or os.environ.get("PLUGIN_DATABASE_URL")
    if not db_url:
        raise ValueError("Finance requires its own PLUGIN_DATABASE_URL")
    engine = create_engine(db_url, hide_parameters=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    journal = Journal(sessions)
    specs = [
        market.MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
        market.MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
        market.MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC,
        market.INDICATORS_LOOKUP_TOOL_SPEC,
        market.FUNDAMENTALS_LOOKUP_TOOL_SPEC,
        market.NEWS_LOOKUP_TOOL_SPEC,
        market.SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
        market.INSIDER_DATA_LOOKUP_TOOL_SPEC,
    ]
    models = [
        getattr(runtime_types, "Runtime" + name + "LookupResult")
        for name in (
            "Quote",
            "History",
            "Ohlcv",
            "Indicator",
            "Fundamentals",
            "News",
            "SocialSentiment",
            "InsiderData",
        )
    ]
    capability_titles = [
        "查询最新行情",
        "查询历史行情",
        "查询价格走势",
        "计算技术指标",
        "查询公司财务",
        "查找市场新闻",
        "了解市场讨论",
        "查询内部人交易",
    ]
    definitions = [
        tool(
            "signaldeck/finance",
            spec.key.rsplit("/", 1)[1],
            {**input_contract(spec.parameters_schema), "title": title},
            model_wire_schema(model),
            spec.description,
            resources=("finance-market-data",),
        )
        for spec, model, title in zip(specs, models, capability_titles, strict=True)
    ]
    report_schema = model_wire_schema(ReportRead)
    definitions.append(
        tool(
            "signaldeck/finance",
            "reports_lookup",
            {
                **input_contract(REPORT_LOOKUP_TOOL_SPEC.parameters_schema),
                "title": "查找已有报告",
            },
            obj(
                {
                    "count": {"type": "integer"},
                    "reports": {"type": "array", "items": report_schema},
                },
                ("count", "reports"),
            ),
            REPORT_LOOKUP_TOOL_SPEC.description,
        )
    )
    definitions.append(
        tool(
            "signaldeck/finance",
            "reports_create",
            obj(
                {
                    "name": {"type": "string", "minLength": 1, "maxLength": 160},
                    "content": {"type": "string", "minLength": 1},
                },
                ("name", "content"),
            ),
            report_schema,
            "Persist a Finance report with immutable Agent invocation provenance.",
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
    definitions[-1]["inputSchema"]["title"] = "保存报告"
    context = RuntimeToolContext(
        sessions,
        (
            quote_provider
            if quote_provider is not None
            else create_quote_provider(provider_settings)
        ),
        create_news_providers(provider_settings),
        create_social_sentiment_adapters(provider_settings),
    )
    handlers = {s.key: s for s in specs + [REPORT_LOOKUP_TOOL_SPEC]}

    def execute(name, arguments, invocation):
        if name == "signaldeck/finance/reports_create":

            def effect(session):
                identity = hashlib.sha256(invocation["operationId"].encode()).hexdigest()[:32]
                record = Report(
                    name=arguments["name"] + "_" + identity,
                    slug="agent_" + identity,
                    source="agent",
                    content=arguments["content"],
                    metadata_={
                        "createdBy": {
                            "type": "agent",
                            "runId": invocation["runId"],
                            "nodeId": invocation["nodeId"],
                            "invocationId": invocation["invocationId"],
                            "operationId": invocation["operationId"],
                        }
                    },
                )
                session.add(record)
                session.flush()
                return project(
                    ReportRead.model_validate(record).model_dump(mode="json", by_alias=True)
                )

            return journal.write(invocation["operationId"], name, arguments, effect)
        if name != "signaldeck/finance/reports_lookup":
            binding = invocation.get("resourceBindings", {}).get("finance-market-data", {})
            allowed = binding.get("allowedSymbols")
            if not isinstance(allowed, list) or "finance-market-data" not in invocation.get(
                "resourceGrants", []
            ):
                raise ValueError("finance_resource_not_granted")
            requested = arguments.get(
                "symbols", [arguments["symbol"]] if "symbol" in arguments else []
            )
            if any(symbol.upper() not in allowed for symbol in requested):
                raise ValueError("finance_symbol_not_granted")
        spec = handlers[name]
        return project(spec.executor(context, spec.parser(json.dumps(arguments))))

    def startup():
        Base.metadata.create_all(engine)
        OperationBase.metadata.create_all(engine)

    root = Path(__file__).resolve().parents[1]
    configuration = provider_settings.model_dump(mode="json", by_alias=True)
    if quote_provider is not None:
        configuration["quoteProviderOverride"] = (
            type(quote_provider).__module__ + "." + type(quote_provider).__qualname__
        )
    binding = release(
        "signaldeck/finance",
        (root / "VERSION").read_text().strip(),
        os.environ.get("PLUGIN_ENDPOINT", "http://finance:8000/mcp/"),
        definitions,
        [root, root.parent / "runtime"],
        os.environ.get("PLUGIN_PAGE_URL", "http://localhost:8091/"),
        configuration=configuration,
        config_schema={
            "title": "金融服务",
            **obj(
                {
                    "allowedSymbols": {
                        "title": "允许查询的证券",
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 32},
                        "uniqueItems": True,
                    }
                },
                ("allowedSymbols",),
            ),
        },
    )
    app = application(binding, execute, journal.query, startup=startup)
    mount_shared_ui(app)
    app.state.sessions = sessions
    app.state.engine = engine
    app.state.execute = execute
    app.state.journal = journal
    app.include_router(templates.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    app.mount("/assets", StaticFiles(directory=root / "web"), name="finance-assets")

    @app.exception_handler(ApiError)
    async def business_error(request, exc):
        return JSONResponse(
            {"code": exc.code, "message": exc.message, "details": exc.details},
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(
            {
                "code": "validation_error",
                "message": "Invalid Finance request",
                "details": [],
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse(
            {
                "code": "plugin_error",
                "message": "Finance operation failed",
                "details": [],
            },
            status_code=500,
        )

    @app.get("/")
    def page():
        return FileResponse(root / "web/index.html")

    return app
