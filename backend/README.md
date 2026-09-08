# SignalDeck Backend

SignalDeck 的 FastAPI backend，提供 Workflow Package 定义、资源与插件配置、启动命令、定时配置及运行证据 API。声明式 DAG 由 Temporal 执行；Finance 的 Templates/Reports 属于独立插件。

安装与普通启动见根 [`README.md`](../README.md)；开发环境、各进程启动和全部验证命令集中在 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。项目开发档位与部署事实以 [`STATUS.md`](../STATUS.md) 为准。

## 入口与运行前提

- API 入口为 `app.main:app`；启动时初始化核心表、补充缺失示例包，并发布当前 Core 制品。
- `app.workers.command_dispatcher` 投递持久启动命令、同步定时配置，并更新执行事实的读取投影。`app.workers.artifact_worker --serve` 为保留的 Core 制品启动固定依赖环境的 worker；Temporal 负责执行与定时调度。仅启动 API 不会执行已入队的 Run。
- API、dispatcher 和 worker 共享 Core PostgreSQL、`AGENT_PLATFORM_ENCRYPTION_KEY`、产物目录和 Core 制品目录；dispatcher 与 worker 还需要相同的 `TEMPORAL_ADDRESS`。插件使用独立进程，Finance 和 Notes 数据保存在各自数据库，核心不挂载 Finance 业务路由。
- `/health` 仅检查 API 进程存活；`/ready` 检查数据库连接，不验证 Temporal、worker、模型或插件。
- 本地组合栈由根 `start.sh` 启动；目标数据使用独立目录，不接管旧实例。拆分配置中的 dispatcher 和 worker 复用 backend 镜像，不发布 HTTP 端口。

## API 与模块导航

| 入口 | 实现责任 |
| --- | --- |
| `/api/workflow-packages` | 定义创建/修改、YAML 验证与编译；`/{packageKey}/prepare` 返回只读准备与绑定核对，`/{packageKey}/launches` 保存不可变快照和启动命令。 |
| `/api/resources` | 模型及工具资源配置、加密凭据写入和安全读取。 |
| `/api/plugins` | 插件 release 契约注册、启停配置及描述读取。 |
| `/api/runs` | 全历史查询/计数/分页、详情、cancel、rerun、调用证据和来源；`/{runId}/result` 是只读业务结果，`/{runId}/reuse` 提供原修订输入及新运行入口。 |
| `/api/task-presets` | 命名输入配置和收藏/置顶 CRUD，按包版本与闭合 schema 验证，不创建运行或计划。 |
| `/api/connection-presets` | 读取部署声明的非敏感连接选择；不探测外部服务、不返回凭据。 |
| `/api/artifacts/{digest}` | 按内容摘要读取运行产物。 |
| `/api/schedules` | cron/时区/重叠/错过策略配置、同步状态、`/preview` 和 `/{scheduleId}/preview` 的 Temporal 时间预览、`/{scheduleId}/trigger` 与 fire history。 |

HTTP 组合入口为 [`app/api/platform_router.py`](app/api/platform_router.py)，请求与响应模型在相应路由文件及其导入的领域模型中。定义和 DAG 契约位于 `app/domain/`，应用编排位于 `app/application/`，存储、Gateway 与 Temporal 适配位于 `app/infrastructure/`。详见 [`架构说明`](../docs/架构说明.md)、[`数据模型`](../docs/data-model.md) 和 [`插件说明`](../plugins/README.md)。

部署可通过 `SIGNALDECK_CONNECTION_PRESETS_FILE` 指定连接选择 JSON 文件；数据遵循 [`ConnectionPresetList`](app/schemas/connection_presets.py)，包含资源标识、非敏感配置和需要用户填写的凭据字段描述。文件中不提供凭据值；未提供选择时，普通页面不猜测 provider、模型或业务范围。实际服务部署仍是独立前提。

准备返回 `bindingToken`，启动、rerun 和 reuse 可以携带它核对已检查的绑定。客户端必须在不确定响应下复用同一个 `launchId`；已接受的重试返回原 Run，不因后续配置变化创建新运行。历史分页携带返回的 `snapshotAt` 可排除翻页期间新创建的运行；它不是冻结所有运行状态的数据库事务快照。

## Scheduled Task 请求契约

创建可提供稳定 `requestId`；响应不确定或初次同步失败时以同一身份和定义重试，返回同一安排，不同定义返回 `schedule_identity_conflict`。创建和修改使用 `name`、`packageKey`、`workflowKey`、`parameters`、`cron`、`timeZone`、`overlapPolicy`、`catchupWindowSeconds` 和 `paused`；参数必须符合所选 workflow 的输入 schema。`overlapPolicy` 接受 `skip`、`buffer_one` 或 `allow`；时区单独指定，不嵌入 cron 字符串。

`POST /api/schedules/{scheduleId}/trigger` 接收 `triggerId` 并返回投递回执；实际 fire 和 Run 通过 `GET /api/schedules/{scheduleId}/fires` 检查。配置同步状态与执行状态分开，删除定时配置保留既有 fire/Run 来源。完整契约见 [`app/domain/schedules.py`](app/domain/schedules.py) 和 [`app/api/platform_schedules.py`](app/api/platform_schedules.py)。

## 测试环境

[`tests/conftest.py`](tests/conftest.py) 使用真实 PostgreSQL 和 UUID 隔离的临时数据库；模型路径使用 mock 或本地 fake server。Playwright 还启动独立 Temporal dev server、dispatcher 和固定制品 worker。环境变量优先级、Temporal 版本、数据库权限和命令统一见 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。
