# Backend Tests Guide

- Database-backed tests use real PostgreSQL. `conftest.py` resolves `TEST_DATABASE_URL`, then `DATABASE_URL`, otherwise provisions or reuses a local `pgvector/pgvector:pg16` Docker container; do not substitute SQLite.
- The database fixture connects to `postgres`, creates a UUID-named database and drops it after the test. Supplied credentials need those privileges; fixtures reset DB and settings caches.
- The autouse fixture clears `SIGNALDECK_API_TOKEN`; auth tests set it explicitly and reset settings through the existing fixtures.
- Provider paths use `httpx.MockTransport`, `fixtures/fake_providers.py` or `fake_openai_provider.py`. Keep tests independent of real external provider credentials and availability.
- Use supported manifests from `fixtures/workflow_manifests.py` or grounded package fixtures. Demo and preset changes require their existing parser/compiler/export/runtime assertions and hash contracts to stay aligned.
- Serialize public API models with `model_dump(mode="json", by_alias=True)`. Test route presence through `app.openapi()["paths"]`, and observable response behavior through `TestClient`.
- Test secret absence at read/export/error boundaries. Encryption tests may inspect controlled test payloads and ciphertext envelopes to prove encryption and wrong-key failure; do not turn a no-leak assertion into a blanket ban on testing the storage contract.
- Run the narrow relevant tests and the applicable backend gates from [CONTRIBUTING](../../CONTRIBUTING.md).
