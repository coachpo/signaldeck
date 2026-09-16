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
elif kind == "generic":
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from plugin_runtime.server import release

    app = FastAPI()
    binding = release(
        "example/field-journal", "1.0.0", os.environ["PLUGIN_ENDPOINT"], [],
        [Path(__file__).parent], page_url=os.environ["PLUGIN_PAGE_URL"],
        ui={"version": "signaldeck.pluginUi/1", "title": "观察记录"},
    )

    @app.get("/release")
    def fixture_release():
        return binding

    @app.get("/")
    def fixture_page():
        return HTMLResponse("""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
        <main><h1>观察记录</h1><label>记录内容<input aria-label="记录内容"></label></main>
        <script>
        addEventListener('message', event => {
          if (event.origin !== location.origin || event.source !== parent) return;
          const message = event.data;
          if (message.protocol === 'signaldeck.pluginUi/1' && message.type === 'location') {
            document.querySelector('h1').textContent = message.path === '/detail' ? '观察详情' : '观察记录';
          }
        });
        parent.postMessage({protocol:'signaldeck.pluginUi/1',type:'ready'},location.origin)</script>
        </html>""")
else:
    from oracle_plugin import runtime_market_sentiment
    from oracle_plugin.main import create_app

    runtime_market_sentiment._HttpxFearGreedJsonClient.get_json = lambda *a, **kw: {
        "fear_and_greed": {"score": 42, "rating": "fear", "timestamp": 1704067200000}
    }
    app = create_app()

uvicorn.run(app, host="127.0.0.1", port=int(port), access_log=False)
