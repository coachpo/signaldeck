# 贡献指南

## 开发环境与依赖

- Backend：`backend/pyproject.toml` 要求 Python >=3.13；CI、应用镜像和固定 Core 执行环境使用 Python 3.13.13，CI 与应用镜像使用 uv 0.11.7。worker 用 uv 按 Python 3.13.13 为每个 Core 制品建立执行环境，热更新开发、E2E 和部分 backend 测试都需要 uv 能提供该版本（可先运行 `uv python install 3.13.13`）。
- Frontend：`frontend/package.json` 要求 Node >=24 并固定 pnpm 10.30.1；CI 使用 Node 24，镜像中的前端构建阶段使用 Node 26。
- 应用与三个插件共用同一个镜像，因此共用根 `Dockerfile` 固定的 Python 3.13.13、uv 0.11.7 和 Node 26 构建阶段；各插件仍有自己的 `pyproject.toml`、冻结锁文件和独立虚拟环境，Core 升级依赖不代表插件同步升级。
- 依赖以 `backend/uv.lock` 和 `frontend/pnpm-lock.yaml` 为准，按锁文件安装，普通环境准备不升级依赖。
- 本地栈、未指定数据库时的测试容器和镜像检查需要 Docker；热更新开发、真实 Temporal 的 backend 测试、E2E 和 ablation 需要 [Temporal CLI 1.8.3](#temporal-cli)。

```bash
(cd backend && uv sync --frozen)
(cd frontend && pnpm install --frozen-lockfile)
```

### FastAPI 版本上限

`backend/pyproject.toml` 把 FastAPI 限制在 `>=0.136.3,<0.137`：FastAPI 0.137 把 `include_router` 的路由嵌套为私有的 `_IncludedRouter`，使 0.64b0 之前的 `opentelemetry-instrumentation-fastapi` 在部分路由匹配（例如 405）时崩溃；0.64b0 需要 `opentelemetry-sdk>=1.43`，而锁定的 Logfire 版本把 SDK 限制在 1.43 以下。解除前先核对目标 Logfire 版本的依赖元数据允许 `opentelemetry-sdk>=1.43`，并确认整个依赖集合能同时解析出 `opentelemetry-instrumentation-fastapi>=0.64b0`；只看到 SDK 上限放宽不够。满足后修改 FastAPI 约束，在 `backend/` 中重新锁定并打印实际解析版本：

```bash
uv lock --upgrade-package fastapi --upgrade-package logfire \
  --upgrade-package opentelemetry-instrumentation-fastapi
uv run --frozen python - <<'PY'
from pathlib import Path
import tomllib

names = {"fastapi", "logfire", "opentelemetry-sdk", "opentelemetry-instrumentation-fastapi"}
for package in tomllib.loads(Path("uv.lock").read_text())["package"]:
    if package["name"] in names:
        print(f'{package["name"]}: {package["version"]}')
PY
```

核对完整锁文件 diff，再在同一目录对候选依赖组合运行以下回归（数据库准备见 [Backend 测试数据库](#backend-测试数据库)），它们依次覆盖 Core 包编辑、Finance 业务 HTTP、Logfire instrumentation 注册，以及经过 instrumentation 的 `/api/runs` 的 GET-only/405 行为。这些回归和适用的后端门禁全部通过后，才移除上限及其注释，并删除 [`.github/dependabot.yml`](.github/dependabot.yml) 中的 `fastapi` ignore 规则。

```bash
uv run pytest \
  tests/test_platform_api.py::test_definition_editor_uses_canonical_immutable_source \
  tests/test_independent_plugins.py::test_finance_owned_crud_compile_upload_and_immutable_agent_reports \
  tests/test_runtime_config_health.py::test_create_app_instruments_fastapi_with_logfire \
  tests/test_core_api.py::test_run_catalog_is_get_only_with_logfire_instrumentation
```

## 开发启动

完整本地栈由 [`start.sh`](start.sh) 以 Docker Compose 运行，启动、插件选择、停止和本地数据保留见 [`README.md`](README.md#快速开始)；正式镜像与生产 Compose 的配置见[部署说明](docker/deployment.md)。本地栈不向宿主机发布 PostgreSQL 和 Temporal RPC 端口，宿主机进程不能使用 `db:5432` 或 `temporal:7233`。

热更新开发在宿主机运行各进程，需要一个宿主机可访问、只属于本次开发实例的 PostgreSQL 16 和 [Temporal CLI](#temporal-cli)。在仓库根目录为 API、dispatcher 和 worker 的每个终端设置相同的 `DATABASE_URL`、`AGENT_PLATFORM_ENCRYPTION_KEY` 和以下变量，使三者读写同一组绝对目录：

```bash
export SIGNALDECK_RUNTIME_MODE=local
export TEMPORAL_ADDRESS=127.0.0.1:7233
export SIGNALDECK_ARTIFACT_DIR="$PWD/.signaldeck-dev/artifacts"
export SIGNALDECK_CORE_ARTIFACT_DIR="$PWD/.signaldeck-dev/core"
export SIGNALDECK_CORE_ENV_DIR="$PWD/.signaldeck-dev/core-environments"
mkdir -p "$PWD/.signaldeck-dev/temporal"
```

然后在各终端分别运行（已有 Temporal 时复用其地址，跳过第一条）：

```bash
"${TEMPORAL_CLI:-/tmp/sd-temporal-bin/temporal}" server start-dev --ip 127.0.0.1 --port 7233 --db-filename "$PWD/.signaldeck-dev/temporal/target.db"
(cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000)
(cd backend && uv run python -m app.workers.command_dispatcher)
(cd backend && uv run python -m app.workers.artifact_worker --serve)
(cd frontend && pnpm dev --host 127.0.0.1)
```

API、dispatcher 和 worker 缺一不可，职责见 [`backend/README.md`](backend/README.md)。Vite 默认端口为 5173，开发构建的 API client 默认访问 `http://127.0.0.1:8000/api`，改用其他 backend 时设置 `VITE_API_BASE_URL`；backend 默认只接受 5173 和 4173 端口上 `127.0.0.1`、`localhost` 的跨域请求，前端改用其他地址时设置 `CORS_ALLOWED_ORIGINS`（逗号分隔）。API 每次重载时若 Core 源码有变化就发布新的 Core 制品，worker 为它建立新的执行环境；已有 Run 继续使用其绑定的制品，所以 `.signaldeck-dev/` 下的制品和产物是恢复所需数据，不随源码更新清空。

平台默认不安装工作流；需要启动时导入时，把 `SIGNALDECK_WORKFLOW_DATA_DIR` 设为自备工作流目录的绝对路径，导入语义见[独立数据导入与分发](docs/工作流解耦方案.md#独立数据导入与分发)。宿主机开发不会自动登记插件：插件按 [`plugins/README.md`](plugins/README.md#build-and-run) 单独运行，登记的 endpoint 必须能从 worker 进程访问。

## 测试数据库与 E2E 环境

### Temporal CLI

Temporal CLI 1.8.3（内含 Server 1.31.2）的默认路径为 `/tmp/sd-temporal-bin/temporal`。在 macOS arm64 上安装：

```bash
curl -fsSL https://github.com/temporalio/cli/releases/download/v1.8.3/temporal_cli_1.8.3_darwin_arm64.tar.gz \
  -o /tmp/sd-temporal-cli.tar.gz
mkdir -p /tmp/sd-temporal-bin
tar -xzf /tmp/sd-temporal-cli.tar.gz -C /tmp/sd-temporal-bin
/tmp/sd-temporal-bin/temporal --version
```

其他平台下载同一版本对应的发布包；CI 用 [`install-temporal-cli.sh`](.github/scripts/install-temporal-cli.sh) 安装并校验 Linux x86_64 版本。backend 测试和 ablation 只读取 `TEMPORAL_CLI`，缺省为上述路径；E2E 启动器依次使用 `TEMPORAL_CLI`、上述路径和 PATH 中的 `temporal`，版本不是 1.8.3（Server 1.31.2）时拒绝启动。

### Backend 测试数据库

Backend pytest 的数据库 fixture 依次使用 `TEST_DATABASE_URL`、`DATABASE_URL`。两者都未设置时，fixture 通过 Docker 启动或复用容器 `signaldeck-target-test-postgres-volume`（`pgvector/pgvector:pg16`，数据在命名卷 `signaldeck-target-test-postgres-data`），它只绑定 `127.0.0.1`，宿主机端口默认随机，可用 `LOCAL_POSTGRES_PORT` 指定。设置 `SIGNALDECK_TEST_POSTGRES_DIR` 时改用该宿主机目录和容器 `signaldeck-target-test-postgres`。出现 `could not open/remove file ... Permission denied` 时，不要放宽目录权限或用 SQL GRANT 掩盖存储错误，应取消该目录设置改用默认卷，或用上述 URL 选择可用实例。

连接账户需能访问 `postgres` 管理库并创建、删除数据库：每个数据库 fixture 创建独立的 `signaldeck_test_*` 库并在结束时删除，不清空任何应用数据库。自动创建的容器和卷在测试后保留。

### Playwright E2E

`pnpm test:e2e` 以及下文的 integrated、fault 配置都由 Playwright 启动一套自有环境：Temporal dev server、fake OpenAI-compatible provider、Notes/Finance/Oracle 插件、dispatcher、固定制品 worker、backend 和前端 preview。它不复用已有服务，也不连接已有 Temporal。

- 数据库只取 `DATABASE_URL`（不读 `TEST_DATABASE_URL`），未设置时使用 backend 默认的 `signaldeck:signaldeck@localhost:25432/signaldeck`。PostgreSQL 须已可连接，账户权限同上；启动器为 Core 和每个插件创建 `signaldeck_e2e_*` 库，结束时只删除这些库。以 `LOCAL_POSTGRES_PORT=25432` 运行过 pytest 后，其自动创建的容器即满足该默认地址。
- 模型使用 fake provider，Finance 使用确定性行情，连接预设只写入临时目录，Logfire 凭据和 OTLP 导出地址被清空：不需要真实 LLM key，也不向外发送遥测。
- 前端构建与 preview 共用 `SIGNALDECK_E2E_BUILD_DIR` 指定的目录，默认 `dist`。非 integrated 配置的前端 API 地址优先取环境中的 `VITE_API_BASE_URL`，未设置时指向 E2E backend，因此不要在运行 E2E 的 shell 中导出开发用的该变量。backend CORS 只允许所配前端端口上的 `127.0.0.1` 与 `localhost`。同时运行多套 E2E 时，每套使用不同的端口和构建目录。
- 结束时停止自有进程，删除临时目录（Temporal 数据、制品、Core 包和执行环境）与自有数据库；截图和报告写入 Git 忽略的目录。

| 服务 | 默认端口 | 覆盖变量 |
| --- | --- | --- |
| backend API（fixture 的 API 请求跟随该端口） | 8001 | `SIGNALDECK_E2E_BACKEND_PORT` |
| 前端 preview | 4173 | `SIGNALDECK_E2E_FRONTEND_PORT` |
| Temporal dev server | 17233 | `SIGNALDECK_E2E_TEMPORAL_PORT` |
| fake OpenAI-compatible provider | 18081 | `SIGNALDECK_FAKE_PROVIDER_PORT`；backend 使用的完整地址可用 `SIGNALDECK_FAKE_PROVIDER_BASE_URL` 改写 |
| Notes 插件 | 18082 | `SIGNALDECK_E2E_NOTES_PORT` |
| Finance 插件 | 18083 | `SIGNALDECK_E2E_FINANCE_PORT` |
| Oracle 插件 | 18084 | `SIGNALDECK_E2E_ORACLE_PORT` |
| 通用测试插件（仅 integrated 配置） | 18085 | `SIGNALDECK_E2E_GENERIC_PORT` |

测试编写约束见 [`backend/tests/AGENTS.md`](backend/tests/AGENTS.md) 和 [`frontend/e2e/AGENTS.md`](frontend/e2e/AGENTS.md)。

## 检查、测试与构建

以下门禁与 [CI](.github/workflows/ci.yml) 一致，按受影响范围运行；只改文档时核对链接并运行 `git diff --check`。完整 backend `pytest` 需要上文的数据库与 Temporal CLI；`tests/test_notes_browser.py` 还会构建插件 UI 并用 Playwright Chromium 打开页面，因此先安装前端依赖和 Chromium。

```bash
(cd backend && uv run ruff check app tests)
(cd backend && uv run black --check app tests)
(cd backend && uv run isort --check-only app tests)
(cd backend && uv run mypy app)
(cd backend && uv run pytest)
```

```bash
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium)
(cd frontend && pnpm test:e2e)
```

机器负载高时，完整 Vitest 和真实 Temporal 测试可能超时：降低并发（如 `pnpm test:run --maxWorkers=2`）或单独重跑，不要放宽超时或断言。

部署配置、网关生成器和运维 skill 脚本的单元测试：

```bash
python3 -m unittest discover -s docker -p 'test_*.py'
python3 -m unittest discover -s frontend/gateway -p 'test_*.py'
for tests in .agents/skills/*/scripts/tests; do python3 -m unittest discover -s "$tests" -p 'test_*.py'; done
```

CI 的 job 与上述命令对应：`version-sync`（六处版本一致与这些单元测试）、`backend-quality` 与 `frontend-quality`（两组门禁中 E2E 以外的命令）、`frontend-e2e`（前三个 job 通过后运行 `pnpm test:e2e`）和 `container-images`（构建那一个镜像并运行 `docker/verify_deployment.py`，Trivy 扫描不阻断）。CI 只上传 Trivy 报告，不上传 Playwright 报告或 trace。本地单独复现一个 spec 用 `(cd frontend && pnpm exec playwright test e2e/<name>.spec.ts)`，HTML 报告写入 Git 忽略的 `frontend/playwright-report/`；trace 只在第一次重试时记录，本地默认不重试。

CI 不运行以下套件，按改动范围补充：

```bash
(cd frontend && pnpm exec playwright test --config playwright.integrated.config.ts)
(cd frontend && pnpm exec playwright test --config playwright.fault.config.ts)
python3 docker/test_plugin_gateway.py
```

- integrated 配置额外启动通用测试插件，把各插件登记为同源挂载，由 Vite preview 代理 `/api` 与 `/_plugins/<mountKey>/`，再运行 `integrated-plugins.spec.ts`（只在该配置下执行）和 `shell.spec.ts`。修改插件宿主、挂载登记或插件页面时运行。
- fault 配置串行运行 `faults.spec.ts`，在插件关闭后再停止启动器自有的 Temporal，核对历史结果和调用证据仍可读取。普通 E2E 也运行该 spec，只跳过停止 Temporal 的分支；改动涉及执行服务停止后的历史读取时运行 fault 配置。
- `docker/test_plugin_gateway.py` 需要 Docker，用自己的临时容器和网络验证实际 Nginx 的无口令访问、凭据剥离、编码路径、内部接口隔离与离线上游。修改 `docker/nginx.conf.template` 或 `frontend/gateway/` 时运行。

插件自身的测试与镜像冒烟见 [`plugins/README.md`](plugins/README.md)，Finance 页面、模板和报告的浏览器回归见 [`plugins/finance/README.md`](plugins/finance/README.md#验证)。

修改根 `Dockerfile`、插件代码或生产 Compose 时运行 `docker build .`，再按[部署说明](docker/deployment.md#健康检查与本地验证)运行 `docker/verify_deployment.py`。所有变更最后运行 `git diff --check`。

## 开发工作流

1. 读取 `STATUS.md`、下方当前开发策略、相关规范文档和适用的子目录 `AGENTS.md`；按[产品说明](docs/产品说明.md#验收标准)确认受影响的产品合同和验收编号，按[架构说明](docs/架构说明.md)确认变更所属模块和依赖方向。
2. 先运行与改动直接相关的最小检查，再按影响范围运行[质量门禁](#检查测试与构建)；修改 secret、错误详情、包导出、运行读取或日志路径时，检查现有加密、脱敏和安全投影约束。
3. 检查精确 diff，不带入无关文件，按下方[完成定义](#完成定义)交付，并说明受影响的验收编号、验证结果和实际限制。

## 发布

`./release.sh patch --dry-run` 预览一次发布：只打印将执行的修改和命令，不改文件，也跳过干净工作区与分支检查。正式发布运行 `./release.sh patch`（或 `minor`、`major`、明确的 `X.Y.Z`；`--yes` 跳过确认）。脚本要求位于干净且已包含最新 `origin/main` 的 `main`，当前六处版本一致，目标版本更高，标签在本地和远端都未被使用；随后同步 `VERSION`、`backend/VERSION`、`backend/pyproject.toml`、`backend/uv.lock` 中的项目版本、`frontend/VERSION` 与 `frontend/package.json`（插件版本各自独立），运行 `uv lock --check`、`/health` 版本测试和前端构建并确认只改动了这六处，再提交 `chore: bump version to X.Y.Z`、打 `vX.Y.Z` 标签并推送 main 与标签。脚本不部署实例；CI 的 `version-sync` job 要求六处版本一致。

`v*` 标签触发 [`Docker Images`](.github/workflows/docker-images.yml)：其 `verify-ci` job 每 30 秒查询一次发布提交上的 `ci.yml` 运行，最多约 40 分钟；只有结论为 success 才构建并推送那个 `linux/arm64` 应用镜像，失败、取消或超时都拒绝发布。推送 main 和 PR 不发布镜像；手动运行跳过 `verify-ci`，也不移动 `latest`。镜像名、完整标签（含手动运行的标签）和部署时的版本固定见[部署说明](docker/deployment.md#发布与镜像版本)。发布进行中不要再推送 main：CI 会取消同一分支上进行中的运行，包括发布提交的 CI。手动运行不再选择服务，只构建同一个镜像。[`cleanup.yml`](.github/workflows/cleanup.yml) 只删除 7 天前的工作流运行记录（至少保留 3 条），从不删除镜像版本：历史多架构镜像的各平台 manifest 没有标签，删除未打标签的版本会破坏仍在使用的固定插件和回滚镜像。

实例巡检、备份与恢复演练、发布和带门禁的部署由 `.agents/skills/` 下的三个运维 skill 执行，入口见[文档索引](docs/README.md#专项文档)。

<!-- write-project-docs:shared-contributing:start -->
## 当前开发策略

**开发档位：`MVP`**

围绕 [`docs/产品说明.md`](docs/产品说明.md) 已确认的产品范围、非目标和验收标准，完成最小可观察的端到端闭环。

### 本档位必须完成

- 跑通核心用户流程、可见结果和与核心验收直接相关的错误路径。
- 运行足以使核心结论可观察、可重复的受影响路径测试、检查和构建验证。

### 默认不投入

- 永久豁免安全、隐私、数据、密钥与凭据管理、权限体系扩建、兼容层与全量兼容回归、审计/监控/SLO、法规合规等合规要求的主动投入；不主动投入非核心功能、仓库级默认门禁、高可用和生产加固。
- 不为未验证需求添加通用化能力、抽象、依赖或非主路径业务分支。

### 不可越过的边界

- 用户明确要求、已接受 GOAL、项目硬规则/不变量、仓库必需检查和 [`STATUS.md`](STATUS.md) 明确禁止事项仍然有效，不受豁免影响；现有兼容承诺作为既有合同不被档位删除。
- 不扩大权限，不执行未授权外部写入或破坏性操作，不删除或重置现有数据，不虚构验证结果。

### 切换条件

- 当有限真实用户、真实或不可丢弃数据、外部流量或试点运维责任出现时切换到 `PILOT`。
- 当需要一般可用性、明确 SLO 或持续生产支持时切换到 `PRODUCTION`。

## 通用设计原则

优先沿用项目中已验证且仍适用的设计，其次是适用的正式标准或官方推荐方案、成熟且持续维护的行业方案；只有它们不满足已核实约束时才做最小定制设计。涉及架构边界、依赖方向、数据责任、安全边界或长期依赖的选择，记录依据、主要权衡和验证方式，定制设计还要说明成熟方案不适用的约束；未接受或未实现的候选不写成当前架构事实。

## 通用实现原则

新增代码前先搜索已有实现；依次复用项目已有实现、语言标准库、平台原生能力、已安装依赖和成熟的第三方库，最后才写局部、简单、可测试的最小实现。不为小功能引入大型依赖，不为假设需求建立抽象、扩展或兼容层。实现遵守 [`docs/架构说明.md`](docs/架构说明.md)、[`docs/开发规范.md`](docs/开发规范.md) 和 [`docs/源代码规模与职责规则.md`](docs/源代码规模与职责规则.md)。

## 完成定义

一项变更只有在以下条件全部满足时才算完成：

- 实现符合已确认的范围和验收条件，保持既有架构边界和依赖方向，没有加入无关职责或顺手改动；
- 满足适用的开发规范，重要设计选择已按通用设计原则记录依据；
- 相关测试、静态检查、格式检查和构建验证已经通过；
- 已按开发规范完成唯一权威文档（见[文档索引](docs/README.md)）、机器合同和验证的同步；
- 没有提交密钥、凭据、个人数据、生成产物或无关文件；
- 已按源代码规模与职责规则完成检查，并报告需要说明的长文件。
<!-- write-project-docs:shared-contributing:end -->
