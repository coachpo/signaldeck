# Backend Extensions Guide

For the currently installed in-process extensions, read the [static extension contract](../../../docs/writing-extensions.md) before changing wiring. The independent-plugin destination is defined in [the target design](../../../docs/迭代目标.md); the current registry is not its installation contract.

- `contract.py` owns contribution fields; `registry.py` owns `INSTALLED_EXTENSIONS` and composition. Keep import-time duplicate checks for extension, catalog, runtime, and normalized package-private MCP keys.
- Keep each extension's `ownership.py`, `tool_specs.py`, and `runtime_executors.py` aligned. Native tool keys carry the extension prefix; function names replace `.` with `_`. `RuntimeToolRegistry` also rejects collisions introduced by this mapping.
- The composition root consumes the `execution_provider_bundle` factory explicitly. Other factory names need explicit consumers; merged bundles reject duplicate extension payloads.
- Dependency surfaces are safe labels consumed by `backend/app/services/extension_dependencies.py`. Update package/compiler and run provenance coverage when changing ownership or labels; they do not capture provider objects or installed code versions.
- Preserve grant checks before parameter parsing/execution in `backend/app/agents/runtime_tools/registry.py`; extension executors must not create an alternate ungranted dispatch path.
- For wiring changes, use `tests/test_extension_contract.py`, `tests/test_tool_catalog_api.py`, `tests/test_runtime_tools.py`, and `tests/test_execution_providers.py` from `backend/`, selecting the affected contracts.
