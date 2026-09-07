# Finance Extension Guide

`signaldeck.finance` contributes Templates/Reports APIs and finance runtime tools. Its provider implementations also use the existing provider modules in `backend/app/services/`.

- Keep template/report domain changes in `services/` and their boundary adapters in `backend/app/api/templates.py` and `reports.py`; `__init__.py` contributes those routers.
- Preserve the additional `RuntimeToolGrantService` checks in report, quote, and history lookup services via `grant_policy.py`, even when callers already passed registry grant checks.
- `provider_factories.py` builds settings-driven providers; `execution_dependencies.py` owns the typed finance payload inside `ExecutionProviderBundle`. Resolve quote/news/sentiment providers through that boundary, not generic attribute access on the platform bundle.
- Yahoo is the default quote backend; deterministic providers are explicit test/fallback dependencies. Preserve provider identity and warnings in normalized results rather than presenting generated data as upstream market evidence.
- News provider order comes from `config.py`. Resolve `alpha_vantage_api_key` through runtime context when constructing news providers; the default composition does not load this credential into the bundle.
- `web_search_exa` is owned package-private MCP, not a native tool declaration.
- `ReportService` keeps `compiled`, `uploaded`, `external`, and `agent` sources distinct and rejects `createdBy` metadata for non-agent sources. Do not let external report creation forge run provenance.
