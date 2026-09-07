# SignalDeck Agent Guide

SignalDeck is a trusted single-user workflow runner: YAML Workflow Packages define agent pipelines, manual or scheduled launches enqueue runs, and operators inspect execution evidence and outputs. Product scope and the development tier are owned by [STATUS.md](STATUS.md) and the [product specification](docs/产品说明.md).

## Communication

- Do not send optional progress commentary; report required results, blockers, and final status.
- Do not revert, overwrite, or stage user changes you did not make.

## Change Routing

| Change | Start here |
| --- | --- |
| Backend APIs, schemas, persistence, and runtime | [backend/app/AGENTS.md](backend/app/AGENTS.md); HTTP composition starts in `backend/app/main.py`, execution in `backend/app/services/`, scheduler in `backend/app/workers/run_scheduler.py`. |
| Static tools, providers, Templates, and Reports | [backend/app/extensions/AGENTS.md](backend/app/extensions/AGENTS.md); `backend/app/extensions/registry.py` is the composition root. |
| Backend regression coverage | [backend/tests/AGENTS.md](backend/tests/AGENTS.md). |
| Frontend routes, authoring, and run inspection | [frontend/AGENTS.md](frontend/AGENTS.md); route ownership starts in `frontend/src/routes.ts`, with local guides under affected features and E2E. |
| Workflow Package examples | [demo/AGENTS.md](demo/AGENTS.md); check corresponding bundled seeds and package contract tests. |
| Documentation | [docs/AGENTS.md](docs/AGENTS.md) and the canonical navigation below. |
| Iteration toward the accepted target | Resolve the frozen baseline through [STATUS.md](STATUS.md#冻结迭代目标), then read [the target design](docs/迭代目标.md) at that commit and the current architecture's remaining gaps. |
| Local launch and container images | `start.sh`, root Compose/Dockerfile for local/demo; `backend/Dockerfile`, `frontend/Dockerfile`, and `.github/workflows/docker-images.yml` for split images. |

## Cross-Cutting Boundaries

- Use current architecture for maintenance; use the accepted frozen target for goal-directed replacement. Read its target and acceptance identifiers before implementation and report the covered criteria. Current static extension and scheduler wiring are implementation facts, not permanent target constraints. Do not add compatibility shims or legacy paths to constrain the target; Workflow Packages remain the executable workflow authoring root.
- DAG execution, Agent Runtime redesign and independently deployed plugins are within the accepted target. Do not add auth/RBAC product surfaces, multi-tenant accounts, a plugin marketplace, Studio, Tryout, memory, fork, portfolio, simulations, backtests or restore historical orchestration/runtime-v2 product entry points unless explicitly re-scoped. Preserve Finance ownership of Templates and Reports.
- Preserve external camelCase through `CamelModel`, API-owned `{code, message, details[]}` errors, and string serialization for money, quantities, and market values. Apply [development rules](docs/开发规范.md) across both API producers and browser consumers; authentication middleware has its own documented 401 response.
- Secret values must never appear in reads, exports, run details, logs, diagnostics, API error details, or metadata. Use existing encryption and safe projection boundaries; internal runtime payloads are not browser response models.
- Keep YAML source safety and graph semantics in the manifest parser, deterministic ordering and hashes in the compiler, and distinct validation/launch/strict-readiness diagnostics in preflight. Package schemas stay closed; do not introduce `additionalProperties`, `allowAdditionalProperties`, or `patternProperties`.
- Execute and rerun from immutable package snapshots. Preserve queue, schedule, and run provenance when changing the corresponding flows.
- PostgreSQL initialization uses `create_all`, bundled seeds, and startup recovery. There is no migration framework; follow the [data and rebuild policy](STATUS.md) for schema changes.
- Frontend data access uses feature hooks and `queryKeys`; shared components remain presentational. Follow [frontend/DESIGN.md](frontend/DESIGN.md) for visual changes.
- Demo YAML is contract material. Review affected parser/compiler/preflight tests, locked hashes, and seeds when changing it.

## Validation and Local Runtime

Use the verified setup, checks, and completion rules in [CONTRIBUTING.md](CONTRIBUTING.md), then run `git diff --check`. Follow the nearest subtree guide for focused checks.

`./start.sh` is the local/demo launcher; the default application URL is `http://localhost:${APP_PORT:-8080}`. The root combined image is local/demo only; production image wiring uses the split backend and frontend images. A root Dockerfile change requires local `docker build .` validation because the image workflow builds only the split images. Before exposing SignalDeck outside a trusted network, configure the API token on the backend or use an authenticated reverse proxy.

For dependency changes, inspect the manifests, lockfiles, and [dependency follow-up](docs/handover-deps-follow-up.md). Do not lift FastAPI `<0.137` until Logfire allows `opentelemetry-sdk>=1.43` and FastAPI instrumentation resolves to `>=0.64b0`. Node 26 Dockerfiles use pinned global pnpm installation; do not reintroduce `corepack enable`.

<!-- write-project-docs:document-navigation:start -->
## 项目文档导航

执行相关任务前，只读取确认相关事实、约束和验收标准所需的章节：

- [项目状态](STATUS.md)
- [文档索引](docs/README.md)
- [产品说明](docs/产品说明.md)
- [架构说明](docs/架构说明.md)
- [开发规范](docs/开发规范.md)
- [源代码规模与职责规则](docs/源代码规模与职责规则.md)
- [贡献指南](CONTRIBUTING.md)

需要确认相关事实、约束或交付意图时，查阅 `STATUS.md` 和产品说明。使用档位默认值或豁免前，确认[当前开发策略](CONTRIBUTING.md#当前开发策略)存在、有效且适用于本次任务，并读取其中相关的要求、边界和切换条件。档位默认值不替代事实、不扩大用户授权，也不覆盖用户要求、项目硬性规则及必需检查。

本轮任务中已核实的信息，在来源未变化且仍适用时可复用；事实、档位、范围或要求变化，或出现冲突证据时，重新核实受影响的信息。

## 项目文档内容边界

本项目不需要为完善文档而引入流程或行政管理。

- 除非用户明确要求并提供可验证依据，不新增审批、汇报、会议、排期、人员治理、发布治理、提交管理、业务 KPI/SLO 或类似内容。
- 不为上述主题创建文档、章节、占位符或“待确认”项。
- 已有且经验证的开发、测试、构建和部署命令仍按对应权威文档记录；本区块不改变产品、架构或工程事实。
<!-- write-project-docs:document-navigation:end -->
