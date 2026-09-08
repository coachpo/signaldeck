import os
from pathlib import Path

from plugin_runtime.serialization import input_contract, model_wire_schema, project
from plugin_runtime.server import application, release, tool

from . import runtime_types
from .contracts import RuntimeToolContext
from .runtime_executors import DIGITAL_ORACLE_RUNTIME_TOOL_SPECS
from .settings import get_digital_oracle_settings

MODELS = [
    runtime_types.RuntimePredictionMarketsLookupResult,
    runtime_types.RuntimeSecFilingsLookupResult,
    runtime_types.RuntimeMarketSentimentLookupResult,
    runtime_types.RuntimeMacroRatesLookupResult,
    runtime_types.RuntimeCryptoDerivativesLookupResult,
    runtime_types.RuntimeCftcPositioningLookupResult,
    runtime_types.RuntimeOptionsLookupResult,
]


def create_app():
    tools = [
        tool(
            "signaldeck/digital-oracle",
            spec.key.rsplit("/", 1)[1],
            input_contract(spec.parameters_schema),
            model_wire_schema(model),
            spec.description,
        )
        for spec, model in zip(DIGITAL_ORACLE_RUNTIME_TOOL_SPECS, MODELS, strict=True)
    ]
    # Secrets are local deployment inputs and never part of the release or invocation context.
    secrets = {
        k: os.environ[k.upper()]
        for k in ("fred_api_key", "edgar_contact_email")
        if os.environ.get(k.upper())
    }
    context = RuntimeToolContext(secrets)
    specs = {s.key: s for s in DIGITAL_ORACLE_RUNTIME_TOOL_SPECS}

    def execute(name, arguments, invocation):
        import json

        spec = specs[name]
        return project(spec.executor(context, spec.parser(json.dumps(arguments))))

    root = Path(__file__).resolve().parents[1]
    binding = release(
        "signaldeck/digital-oracle",
        (root / "VERSION").read_text().strip(),
        os.environ.get("PLUGIN_ENDPOINT", "http://digital-oracle:8000/mcp/"),
        tools,
        [root, root.parent / "runtime"],
        configuration=get_digital_oracle_settings().model_dump(mode="json"),
    )
    return application(binding, execute, lambda *_: {"status": "not_found"})


app = create_app()
