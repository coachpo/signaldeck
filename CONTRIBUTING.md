# 贡献指南

本文件是本地开发、验证和完成定义的入口。项目事实分别由 [`STATUS.md`](STATUS.md)、[`docs/产品说明.md`](docs/产品说明.md) 和 [`docs/架构说明.md`](docs/架构说明.md) 维护；项目特有技术规则由 [`docs/开发规范.md`](docs/开发规范.md) 维护。

## 开发环境与依赖

- Backend：`backend/pyproject.toml` 要求 Python >=3.13；CI、根镜像、backend 镜像及固定 Core 执行环境使用 Python 3.13.13，CI 与镜像使用 uv 0.11.7。
- Frontend：`frontend/package.json` 要求 Node >=24，并固定 pnpm 10.30.1；CI 使用 Node 24，镜像构建使用 Node 26。
- 依赖以 `backend/uv.lock` 和 `frontend/pnpm-lock.yaml` 为准；按现有锁文件安装，不在普通环境准备中升级依赖。
- 完整本地栈需要 Docker Compose v2，使用 PostgreSQL 16 和 Temporal；普通安装与启动见 [`README.md`](README.md#快速开始)。

安装依赖：

```bash
(cd backend && uv sync --frozen)
(cd frontend && pnpm install --frozen-lockfile)
```

## 开发启动

完整本地/演示栈使用 [`start.sh`](start.sh)，启动、插件选择和停止命令见 [`README.md`](README.md#快速开始)。默认目标数据放在 `.signaldeck-target/`，独立于旧实例。Compose 不向宿主机发布 PostgreSQL 或 Temporal RPC 端口，不能直接将 `db:5432` 或 `temporal:7233` 用于宿主机进程。

需要热更新时，准备独立且可从宿主机访问的 PostgreSQL，以及 Temporal CLI **1.8.3（内含 Server 1.31.2）**。API、dispatcher 和 worker 的终端必须设置相同的 `DATABASE_URL`、`AGENT_PLATFORM_ENCRYPTION_KEY`、`TEMPORAL_ADDRESS` 和下列绝对目录；worker 还需可用的 uv 和 Python 3.13.13。目录应属于本次开发实例，不指向旧版或不可丢弃数据。

```bash
export SIGNALDECK_RUNTIME_MODE=local
export TEMPORAL_ADDRESS=127.0.0.1:7233
export SIGNALDECK_ARTIFACT_DIR="$PWD/.signaldeck-dev/artifacts"
export SIGNALDECK_CORE_ARTIFACT_DIR="$PWD/.signaldeck-dev/core"
export SIGNALDECK_CORE_ENV_DIR="$PWD/.signaldeck-dev/core-environments"
export SIGNALDECK_CORE_PYTHON_VERSION=3.13.13
mkdir -p "$PWD/.signaldeck-dev/temporal"
```

在仓库根目录分别打开终端执行（Temporal 已在运行时复用其地址）：

```bash
temporal server start-dev --ip 127.0.0.1 --port 7233 --db-filename "$PWD/.signaldeck-dev/temporal/target.db"
(cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000)
(cd backend && uv run python -m app.workers.command_dispatcher)
(cd backend && uv run python -m app.workers.artifact_worker --serve)
(cd frontend && pnpm dev --host 127.0.0.1)
```

Vite 默认使用 5173 端口，开发 API client 默认访问 `http://127.0.0.1:8000/api`；改用其他 backend 地址时设置 `VITE_API_BASE_URL`。API 原子保存 Run、快照和启动命令，dispatcher 投递命令并同步投影，Temporal 与固定制品 worker 执行工作流。API 重载发布新 Core 制品，已有运行继续使用其绑定制品；保留的制品和产物目录是恢复所需数据，不应随源码更新清空。

根镜像运行 Nginx 和 FastAPI；本地 Compose 另启 dispatcher、worker、Temporal 和可选插件。拆分部署的 dispatcher/worker 复用 backend 镜像；环境变量与边界见 [`docs/架构说明.md`](docs/架构说明.md) 和 [`docker/compose.production.example.yml`](docker/compose.production.example.yml)。插件应使用从对应调用进程可达的 endpoint；宿主机开发不会自动注册 Compose 内网地址的插件。

### 测试数据库与 E2E 环境

Backend pytest 的数据库 fixture 优先使用 `TEST_DATABASE_URL`，其次使用 `DATABASE_URL`。两者均未设置时，fixture 会启动或复用 `signaldeck-target-test-postgres` 容器，默认分配宿主机随机端口，可通过 `LOCAL_POSTGRES_PORT` 指定端口。容器使用 `pgvector/pgvector:pg16`，数据库文件默认保存在 `backend/.data/test-postgres/`，可通过 `SIGNALDECK_TEST_POSTGRES_DIR` 改写。它与根 Compose 的数据库是不同的启动路径。

测试连接需要有权限访问 `postgres` 管理库并创建、删除临时 database；每个数据库 fixture 创建独立的 `signaldeck_test_*` 库并在结束时删除。自动创建的本地容器和数据目录会保留，测试不把应用数据库当作临时库清空。

Playwright 使用 `DATABASE_URL`（不读取 `TEST_DATABASE_URL`，缺省为 backend 的本地 25432 地址），要求 PostgreSQL 已可连接并具备同样的建库/删库权限。还需安装上述固定版本的 Temporal CLI；可通过 `TEMPORAL_CLI` 指定可执行文件，否则启动器依次查找 `/tmp/sd-temporal-bin/temporal` 和 PATH 中的 `temporal`，版本不匹配会拒绝启动。

E2E 启动器创建独立的 `signaldeck_e2e_*` 库和临时目录，启动 Temporal（默认 RPC 17233）、fake OpenAI-compatible provider（18081）、dispatcher、固定制品 worker、backend（8001）和 frontend preview（4173）。`SIGNALDECK_E2E_TEMPORAL_PORT` 与 `SIGNALDECK_FAKE_PROVIDER_PORT` 可改写前两者端口。测试使用 fake provider，不需要真实 LLM key；结束时清理所拥有的进程、临时目录和临时库，不复用已有 web server。测试约束见 [`backend/tests/AGENTS.md`](backend/tests/AGENTS.md)，三引擎比较的范围和复现入口见 [`docs/执行引擎比较.md`](docs/执行引擎比较.md)。

### 本地数据保留

普通停止和容器移除使用 `./start.sh stop` 或 `./start.sh down`；两者均保留目标数据。当前 Compose 使用宿主机 bind mount，`docker compose down -v` 不会清除这些目录，不能作为目标数据重置命令。需要一套空白实例时，指定新的 `COMPOSE_PROJECT_NAME`、`SIGNALDECK_DATA_DIR` 及不冲突端口；旧数据的删除、重置或迁移须另行明确授权。数据与兼容政策以 [`STATUS.md`](STATUS.md) 为准。

## 检查、测试与构建

以下质量门禁与 [CI](.github/workflows/ci.yml) 对齐，按受影响范围运行；文档变更只需相关文档校验和差异检查。Backend：

```bash
(cd backend && uv run ruff check app tests)
(cd backend && uv run black --check app tests)
(cd backend && uv run isort --check-only app tests)
(cd backend && uv run mypy app)
(cd backend && uv run pytest)
```

Frontend：

```bash
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium)
(cd frontend && pnpm test:e2e)
```

若变更了根 Dockerfile，补充运行：

```bash
docker build .
```

所有变更最后运行：

```bash
git diff --check
```

## 开发工作流

1. 先读取与任务相关的 `STATUS.md`、下方当前开发策略、产品说明、架构说明、开发规范和适用的子目录 `AGENTS.md`。面向目标的迭代还须按 [`STATUS.md`](STATUS.md#冻结迭代目标) 定位冻结提交，读取该版本的 [`迭代目标`](docs/迭代目标.md) 及状态文档列明的用户补充决定，明确本次对应的目标与验收编号。开发档位只选择执行默认值，不改变产品范围和已有硬约束。
2. 搜索已有实现、接口和测试，确认变更所属模块、当前差距及目标允许的依赖方向。SD-TARGET-001 已接受的目标边界用于指导相应替换；不要因当前结构或兼容便利而降低目标，也不要把待验证选型当成已确定依赖。
3. 先运行与改动直接相关的最小检查；完成后按影响范围运行 backend/frontend 质量门禁，并保持 demo、API contract、snapshot/provenance 和文档同步。
4. 修改 secret、错误详情、包导出、运行读取或日志路径时，检查现有加密、脱敏和安全投影约束。
5. 检查精确 diff、未纳入无关文件，并按下方共享完成定义交付。目标迭代报告所引用的冻结提交 SHA、覆盖的验收编号、验证结果与仍未实现的差距；只把已验证完成的行为写入当前产品和架构说明。

## 项目文档

规范文档的索引和权威边界见 [`docs/README.md`](docs/README.md)。数据表见 [`docs/data-model.md`](docs/data-model.md)，扩展编写见 [`docs/writing-extensions.md`](docs/writing-extensions.md)，依赖遗留事项见 [`docs/handover-deps-follow-up.md`](docs/handover-deps-follow-up.md)。

<!-- write-project-docs:shared-contributing:start -->
## 当前开发策略

**开发档位：`MVP`**

围绕 [`docs/产品说明.md`](docs/产品说明.md) 已确认的核心价值、范围、非目标、验收与退出条件，完成最小可观察的端到端闭环。本档位永久豁免安全、隐私、数据、密钥与凭据管理、兼容、审计/监控/SLO 和法规合规要求的主动投入。

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

在满足已确认的功能范围、架构边界、质量属性、安全性、兼容性和运行约束的前提下，按以下顺序选择设计方案：

1. 项目中已有、经验证且仍适用的设计、模式、接口或组件；
2. 适用的正式标准、标准协议，以及平台或框架的官方推荐方案；
3. 在相似场景中被广泛采用、持续维护且有可靠实践证据的成熟行业方案；
4. 只有上述方案不能满足已核实约束时，才采用满足当前需求的最小定制设计。

“广泛使用”只是候选信号，不是充分的采用理由。采用前按风险核对需求适配、安全与兼容、主要失败模式、维护与迁移成本；不得为套用惯例引入当前范围不需要的能力、抽象或依赖。

涉及架构边界、依赖方向、数据责任、安全边界或长期依赖的重要设计选择，应在设计结果中记录适用依据、主要权衡和验证方式。采用定制设计时，同时说明成熟方案不适用的已核实约束。高风险且证据不足时，先定义可观察的成功、失败和退出条件，再执行当前权限允许的最小可逆验证；不得把未接受或未实现的候选写成当前架构事实。

## 通用实现原则

在满足功能范围、架构边界、正确性、安全性和可验证性的前提下，按以下顺序选择实现方式：

1. 项目中已有的实现；
2. 语言标准库；
3. 平台原生能力；
4. 项目已安装且适合当前场景的依赖；
5. 适合当前环境、成熟、活跃并被广泛使用的第三方库；
6. 满足当前需求的最小自定义实现。

新增代码前先搜索已有实现。不要为小功能引入大型依赖；不要为假设中的未来需求创建抽象层、扩展层或兼容层；保持自定义实现局部、简单且可测试。

实现必须遵守 [`docs/架构说明.md`](docs/架构说明.md) 的项目架构事实、[`docs/开发规范.md`](docs/开发规范.md) 的项目/技术专属规则，以及 [`docs/源代码规模与职责规则.md`](docs/源代码规模与职责规则.md) 的统一规模与职责规则。

## 完成定义

一项变更只有在以下条件全部满足时才算完成：

- 实现符合已确认的功能范围和验收条件；
- 重要设计选择已验证成熟方案的适用性；采用定制方案时，已记录不适用约束、主要权衡和验证方式；
- 保持既有架构边界和依赖方向，没有加入无关职责或顺手改动；
- 已满足适用的项目/技术专属开发规范；
- 相关测试、静态检查、格式检查和构建验证已经通过；
- 已按开发规范完成唯一权威文档、机器合同和验证的同步；
- 没有提交密钥、凭据、个人数据、生成产物或无关文件；
- 已按源代码规模与职责规则完成检查，并报告需要说明的长文件。
<!-- write-project-docs:shared-contributing:end -->
