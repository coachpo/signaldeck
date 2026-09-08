# Backend API Guide

- `platform_router.py` assembles the `/api` platform routes. Finance serves Templates and Reports in its independent plugin process; do not mount plugin business routers in the core API.
- Return explicit response schemas; raw service or ORM objects must not bypass secret-safe read projection.
- Keep literal package `/validate-manifest` before `/{package_key}`. Preserve diagnostic paths and source locations from the shared compiler instead of adding a second HTTP validator.
- `platform_resources.py` installs release descriptors and toggles plugins through `/plugins`; catalog and health reads use stored metadata. Explicit launch admission resolves only the selected workflow's enabled plugin bindings.
- Resource credentials are write-only; `ResourceRead` exposes presence and revision, never values. Run and schedule reads must remain available without initializing the execution engine; only schedule mutations depend on `get_schedule_service`.
- Manual launch, rerun and schedule-trigger requests carry stable caller identities. An uncertain response must be retried with the same identity; a trigger receipt or cancellation request is not a completed Run.
- API route-presence tests inspect `app.openapi()["paths"]`, avoiding private FastAPI include-router internals. For response behavior, use `TestClient` and `test_platform_api.py`, `test_core_api.py` or `test_target_schedules.py` in `backend/tests/`.
