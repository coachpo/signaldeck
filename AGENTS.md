# SignalDeck Agent Guide

SignalDeck is a trusted single-user, self-hosted Agent workflow platform: YAML Workflow Packages define reusable Agents and declarative DAGs, manual or scheduled launches create durable Temporal runs, and the operator reads results and execution evidence.

## Change Routing

| Change | Start here |
| --- | --- |
| Backend API, definitions, persistence, execution, workers and schedules | [backend/app/AGENTS.md](backend/app/AGENTS.md). |
| Backend tests | [backend/tests/AGENTS.md](backend/tests/AGENTS.md). |
| Frontend | [frontend/AGENTS.md](frontend/AGENTS.md). |
| Independent plugins, providers, Templates and Reports | [Plugin contract](docs/writing-extensions.md) and [plugin artifacts](plugins/README.md); Finance owns Templates and Reports under `plugins/finance/`. |
| Workflow Package examples | [demo/AGENTS.md](demo/AGENTS.md). |
| Product behavior, architecture, cross-boundary rules and other documentation | [Product specification](docs/产品说明.md), [architecture](docs/架构说明.md) and [development rules](docs/开发规范.md); the [document index](docs/README.md) lists every document and [docs/AGENTS.md](docs/AGENTS.md) holds the authoring rules. Keep `backend/README.md`: the root `Dockerfile` and `backend/pyproject.toml` reference it. |
| Local stack and images | `start.sh` and root `docker-compose.yml` for the local/demo stack; root `Dockerfile`, `docker/compose.production.yml` and `.github/workflows/docker-images.yml` for the application and plugin images; operation in [deployment](docker/deployment.md). |
| Releases and deployed instances | `release.sh` and the [release commands](CONTRIBUTING.md#发布); operator skills under `.agents/skills/` (linked into `.claude/skills/`): `signaldeck-ops-inspect` read-only, `signaldeck-backup-restore` and `signaldeck-release-deploy` only with explicit authorization. |

## Invariants

- Workflows are package data. Core and frontend code never dispatch on or infer business meaning from package/workflow keys or business field names; business logic, persistence and pages live in independent plugins that Core never imports and reaches only through the [plugin contract](docs/writing-extensions.md); workflow data couples to the platform only through the versioned contracts in [工作流解耦方案](docs/工作流解耦方案.md) ([principle](docs/产品说明.md#工作流与平台解耦原则)).
- `demo/` holds standalone examples, not platform components or fixtures: platform code, tests, verification scripts, builds and startup configuration never reference it, and changing an example never requires a platform change.
- Do not add auth/RBAC, multi-tenancy, a plugin marketplace, Studio, Tryout, memory, fork, portfolio, simulation or backtest surfaces, compatibility shims or legacy execution paths unless the scope is explicitly changed ([product scope](docs/产品说明.md#产品范围)).
- Secret values never appear in reads, exports, run details, logs, diagnostics, API error details or metadata; reuse the existing encryption and safe-projection boundaries ([credential rules](docs/开发规范.md#外部合同与凭据)).
- Package schemas stay closed: never introduce `additionalProperties`, `allowAdditionalProperties` or `patternProperties`, and reject unsupported constraints instead of dropping them ([schema subset](docs/writing-extensions.md#固定协议与-schema-子集)). Runs and reruns execute from immutable snapshots; preserve launch, schedule and run provenance.
- Persistence grows by new tables: `create_all` only creates missing tables and there is no migration framework, so a column added to an existing table's model, even a nullable one, breaks existing databases. For Core models, the read-only `python -m app.infrastructure.schema_compatibility` gate, run from the new image before switching, rejects changes that existing databases cannot satisfy ([schema evolution](docs/data-model.md#初始化与-schema-演进), [data policy](STATUS.md#数据与兼容性)).
- Every file under a plugin's directory, READMEs included, and under the shared `plugins/runtime/` is part of the plugin artifact digest; the Finance and Notes images also bundle the UI built from `frontend/src/plugin-ui` with the shared frontend modules it imports. Any such edit creates a new plugin release identity ([release identity](docs/writing-extensions.md#发布描述)): rebuild the local stack with `./start.sh --detach`, then run `./start.sh refresh-plugins` to register the rebuilt release ([local stack](README.md#快速开始)); deployed instances keep the old release until a plugin upgrade.

## Working Copy, Runtime and Checks

- Other sessions may work in the same checkout: do not revert, overwrite or stage changes you did not make.
- The app, Core API and plugin business APIs take no access token, so keep them inside the trusted network ([deployment boundary](STATUS.md#部署与使用)).
- In a worktree or second checkout, run `./start.sh` only with its own `COMPOSE_PROJECT_NAME`, `SIGNALDECK_DATA_DIR`, `APP_PORT`, `TEMPORAL_UI_PORT` and `SIGNALDECK_LOCAL_IMAGE_PREFIX` ([local instances](README.md#快速开始)): the default project `signaldeck-target-local` and its `:local` images belong to the user's running stack.
- Follow [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks and completion and the nearest subtree guide for focused checks.
- `release.sh` owns the six version surfaces; plugin versions are independent. `docker-images.yml` publishes the four `linux/arm64` images from `v*` tags only after CI passed on the tagged commit, and manual runs publish only `manual-<sha>` tags. Never publish from `main`, split frontend and backend images, or prune untagged image versions.
- Keep FastAPI below 0.137, including in Dependabot updates, until the unlock conditions and regressions in [CONTRIBUTING](CONTRIBUTING.md#开发环境与依赖) pass. The Node 26 Dockerfiles install the pinned pnpm with `npm install -g`; do not use `corepack enable`.

<!-- write-project-docs:document-navigation:start -->
## 项目文档导航

执行任务前，从[文档索引](docs/README.md)找到相关事实、约束和验收标准的权威文档，只读取所需章节；开发档位、部署边界和数据政策见 [`STATUS.md`](STATUS.md)。

使用档位默认值或豁免前，确认[当前开发策略](CONTRIBUTING.md#当前开发策略)适用于本次任务，并遵守其中的[不可越过的边界](CONTRIBUTING.md#不可越过的边界)。

## 项目文档内容边界

本项目不需要为完善文档而引入流程或行政管理。

- 除非用户明确要求并提供可验证依据，不新增审批、汇报、会议、排期、人员治理、发布治理、提交管理、业务 KPI/SLO 或类似内容。
- 不为上述主题创建文档、章节、占位符或“待确认”项。
- 已有且经验证的开发、测试、构建和部署命令仍按对应权威文档记录；本区块不改变产品、架构或工程事实。
- 文档只描述当前状态：迭代记录、单次运行的证据与计数、提交和部署进度以及本地证据路径不写入文档，历史由 Git 保留。
<!-- write-project-docs:document-navigation:end -->
