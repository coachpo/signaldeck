"""Owned E2E plugin process; real MCP/business storage with controlled market data."""

import os
import sys
from pathlib import Path

import uvicorn

root = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "finance", "digital_oracle", "notes"):
    sys.path.insert(0, str(root / directory))

kind, port = sys.argv[1:]
if kind == "finance":
    from finance_plugin.main import create_app
    from finance_plugin.providers.quote_provider import DeterministicQuoteProvider

    app = create_app(os.environ["PLUGIN_DATABASE_URL"], DeterministicQuoteProvider())
elif kind == "notes":
    from notes_plugin.main import create_app

    app = create_app()
else:
    from oracle_plugin import runtime_market_sentiment
    from oracle_plugin.main import create_app

    runtime_market_sentiment._HttpxFearGreedJsonClient.get_json = lambda *a, **kw: {
        "fear_and_greed": {"score": 42, "rating": "fear", "timestamp": 1704067200000}
    }
    app = create_app()

uvicorn.run(app, host="127.0.0.1", port=int(port), access_log=False)
