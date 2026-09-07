# Backend API Guide

- `platform_router.py` assembles the `/api` platform routes. `router.py` consumes statically installed extension routers under `/api/v1`; finance supplies Templates and Reports.
- Return explicit response schemas; raw service or ORM objects must not bypass secret-safe read projection.
- Keep literal actions before parameter catchalls, notably report actions before `/{slug}`, package `/validate-manifest` and `/import`, and schedule `/preview`.
- The current API exposes `/api/tools` as GET-only metadata; installed extensions currently use static wiring and have no management route. Future plugin lifecycle contracts follow [the target design](../../../docs/迭代目标.md), without implying that those endpoints already exist.
- Package and schedule preview/read handlers must use their safe schema projections. Secret bindings have write/delete endpoints and presence-only reads; schedule reads omit input templates and template vars.
- API route-presence tests inspect `app.openapi()["paths"]`, avoiding private FastAPI include-router internals. For response behavior, use `TestClient` and the relevant `tests/test_*_api.py` or package/run contract tests.
