# Backend Services Guide

## Runtime Ownership

- `run_service.py` coordinates launch, planned evidence rows, execution and cancellation. Put historical read shaping in `run_read_projection.py`, rerun preparation in `run_rerun.py`, and queue leases in `run_queue_service.py`.
- Rebuild execution/rerun plans from `RunWorkflowPackageSnapshot`, including the frozen non-secret Model Connection profile. `agent_execution_service.py` looks up the live connection only for its current API key; HTTP operations and extension tools resolve current package secrets at execution time.
- Under the current scheduler, a lost lease fails the run and active child rows, skips pending rows, and never requeues it. This describes current behavior; its replacement follows [the target's durable execution contract](../../../docs/迭代目标.md). Preserve claim ownership checks before committing results and cancellation checks while maintaining this scheduler.
- `workflow_package_schedule_service.py` owns CRUD, previews and run-now; `workflow_package_schedule_materializer.py` owns due fires. Reuse recurrence, input rendering and launch helpers so overlap/misfire and fire idempotency semantics agree.
- Schedule deletion detaches live refs while preserving run-owned provenance; package deletion removes owned runs. Keep these paths distinct.

## Artifact and Provider Boundaries

- Keep YAML source safety and graph semantics in `workflow_package_manifest_parser.py`; deterministic compiled artifacts in `workflow_package_manifest_compiler.py`; browser diagnostics and distinct validation/launch/strict-readiness levels in `workflow_package_preflight.py`.
- `workflow_package_export.py` owns manifest hydration/export redaction. Do not treat stored compiled plans as public response payloads.
- `model_gateway.py` dispatches the supported OpenAI-compatible protocols; `model_gateway_openai.py` and `model_gateway_openai_responses.py` own protocol-specific execution. Keep bounded provider/tool correction retry evidence in the existing result metadata.
- `http_operation_execution_service.py` owns URL/method/network/size/redirect restrictions and request/response evidence sanitization. Test the affected boundary with `httpx.MockTransport` and explicit secret fixtures.
- Relevant regression coverage is in `tests/test_workflow_package_run_contracts.py`, `test_runtime_repositories.py`, `test_run_cancel.py`, `test_db_bootstrap.py` and the parser/compiler/HTTP tests; command authority is [CONTRIBUTING](../../../CONTRIBUTING.md).
