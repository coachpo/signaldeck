# Digital Oracle Extension Guide

`signaldeck.digital_oracle` contributes tool declarations and runtime specs only. It has no API router, browser navigation, or extension-level provider factory.

- Keep provider orchestration in `service.py`, with family-specific clients, argument parsers, and payload normalization in the existing `runtime_*` modules. Extend the relevant family rather than adding a cross-family normalization switch.
- `settings.py` owns feature flags, item limits, and timeouts. Resolve `fred_api_key` and `edgar_contact_email` through `RuntimeToolContext.resolve_secret_value` in the relevant executor and pass `DigitalOracleProviderSecrets` to `factory.py`; they are not environment settings fields.
- Keep provider failures scoped to their source when bounded partial data is available. Preserve empty, unavailable, partial, stale, and truncated-result warnings alongside source metadata; return no invented coverage.
- Build public warnings through `warnings.py` so sensitive detail keys and credential-like message values are filtered before runtime serialization. Do not include raw request headers or stack traces.
- Keep `yfinance` optional and missing-dependency failures scoped to options. The current implementation does not require vendoring `digital-oracle`.
- Changes to provider coverage or result shapes should exercise the corresponding cases in `backend/tests/test_runtime_tools.py` and catalog/alias assertions in `backend/tests/test_tool_catalog_api.py`.
