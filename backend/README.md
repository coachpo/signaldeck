# SignalDeck Backend

SignalDeck 的 FastAPI Core：保存 Workflow Package、资源与插件发布，准备和启动 Run，管理计划，并提供历史、结果与调用证据的读取接口。Run 由 Temporal 执行；Finance、Notes 等业务插件是独立进程，其业务 API 不属于 Core 路由。本地启动见根 [`README.md`](../README.md#快速开始)，开发环境、进程命令和测试见 [`CONTRIBUTING.md`](../CONTRIBUTING.md)，模块职责见[架构说明](../docs/架构说明.md)，持久化见[数据模型](../docs/data-model.md)。

## 进程与运行模式

- API：`app.main:app`。启动时初始化 Core 表，导入 `SIGNALDECK_WORKFLOW_DATA_DIR` 中缺失的工作流（未设置时跳过），并发布当前 Core 制品。
- dispatcher：`python -m app.workers.command_dispatcher`。把启动与取消命令投递到 Temporal，重试未完成的计划同步与手动触发，投影执行终态和 fire 结果。
- worker：`python -m app.workers.artifact_worker --serve`。为 Core 制品目录中每个保留且核验通过的制品建立独立执行环境，并在该制品的任务队列 `sd-core-<hex>` 上运行一个 Temporal worker；Run 在其绑定制品的队列上执行。

API 保存配置、Run 和启动/取消命令，但不投递命令，只启动 API 不会执行已入队的 Run；计划的保存、删除、预览和手动触发则由 API 直接调用 Temporal 完成，见[计划接口](#计划接口)。三者的共享配置与启动命令见[开发启动](../CONTRIBUTING.md#开发启动)；应用镜像以 `app`、`dispatcher`、`worker` 角色运行同一镜像，见[部署说明](../docker/deployment.md)。

Run 在 worker 执行第一个 activity `prepare_run` 时才投影为 `running`；停在 `queued` 时按投递链路排查。本地栈先运行 `./start.sh status`，再运行 `./start.sh logs dispatcher worker`（服务器部署见[部署说明](../docker/deployment.md#健康检查与本地验证)）；这两个服务没有健康检查，容器在运行不代表能投递或执行。dispatcher 反复输出 `Delivery remains pending; the original commands will be retried` 表示投递到 Temporal 失败，命令保留并重试。worker 为每个制品输出 `{"coreArtifact": …, "workerState": …}`，正常为 `started`；`bootstrap_failed`（执行环境无法安装或核验，首次安装需访问锁文件中的公共包源）、`artifact_invalid`（制品核验失败）或反复的 `exited`（worker 进程退出后退避重启）时该制品的队列无人消费。之后在 Temporal UI 按 Run ID（即 Workflow ID）查看执行历史。`/ready` 不检查 Temporal、dispatcher 或 worker；读取 Run 详情和证据不会重新投递或调度。

`SIGNALDECK_RUNTIME_MODE`（[`app/core/config.py`](app/core/config.py)）取 `local`（默认）、`development`、`test`、`staging`、`production` 或 `prod`。`production`、`prod` 和 `staging` 必须显式设置 `DATABASE_URL`（不能等于本地默认值）和 `AGENT_PLATFORM_ENCRYPTION_KEY`（不能为空、开发默认值、`change-me` 或 `changeme`），否则配置校验失败，进程不启动；其他模式缺省时使用代码中的本地开发默认值。应用镜像默认 `production`，入口脚本在启动 `app`、`dispatcher` 或 `worker` 前先执行这项校验；根 Compose 的本地栈使用 `local`。

## HTTP 接口

`app/main.py` 提供 `/health`（存活状态和发布版本）与 `/ready`（只检查数据库），其余接口由 [`app/api/platform_router.py`](app/api/platform_router.py) 挂载在 `/api` 下。完整方法、路径和请求模型以 OpenAPI 为准：`app.openapi()`，或直接访问 API 进程端口上的 `/docs`、`/openapi.json`（应用镜像的 Nginx 只把 `/api/`、`/health` 和 `/ready` 转发给 API）。写入身份与冲突代码见[数据模型](../docs/data-model.md#写入身份与冲突)。

| 前缀 | 路由文件（`app/api/`） | 职责 |
| --- | --- | --- |
| `/api/workflow-packages` | `platform_packages.py` | 包的列表、创建、读取和修改；`/validate-manifest` 校验源码；`/import` 批量导入，见[独立数据导入与分发](../docs/工作流解耦方案.md#独立数据导入与分发)；`/{packageKey}/prepare` 只读准备并返回 `bindingToken`；`/{packageKey}/launches` 启动 Run。 |
| `/api/runs` | `platform_runs.py` | 历史查询与分页、详情（冻结 spec 和调用证据）、`/cancel`、`/rerun`、`/result`；`/reuse` 的 GET 读取原输入，POST 以修改后的输入启动新 Run。 |
| `/api/runs/{runId}/metadata` | `result_metadata.py` | 结果的收藏、已读和备注。 |
| `/api/runs/{runId}/usage`、`/api/model-usage` | `model_usage.py` | 按 Run，或按指定日期与 IANA 时区汇总已记录的模型用量。 |
| `/api/attention` | `attention.py` | 执行更新列表和按更新身份标记已读。 |
| `/api/task-drafts` | `task_drafts.py` | 服务器任务草稿。 |
| `/api/task-presets` | `task_presets.py` | 常用配置与任务收藏。 |
| `/api/schedules` | `platform_schedules.py` | 计划的增删改查与同步状态、`/preview`（待保存的日历）和 `/{scheduleId}/preview`、`/{scheduleId}/trigger` 手动触发、`/{scheduleId}/fires`。 |
| `/api/resources`、`/api/plugins` | `platform_resources.py` | 模型与工具资源（凭据只写）；插件发布登记、启停和列表。 |
| `/api/connection-presets` | `connection_presets.py` | 部署提供的非敏感连接选择，格式见[普通模式的连接选择](../docs/writing-extensions.md#普通模式的连接选择)。 |
| `/api/plugin-pages` | `plugin_pages.py` | 已登记的插件页面目录，见[统一插件页面](../docs/writing-extensions.md#统一插件页面)。 |
| `/api/artifacts/{digest}` | `platform_artifacts.py` | 按内容摘要下载经核验的产物。 |

## 计划接口

- 创建与 PATCH 都提交完整定义（[`ScheduleDefinition`](app/domain/schedules.py)，含 `executionOptions`）；PATCH 不是部分更新，省略的可选字段恢复默认值。
- `cron` 不能包含 `TZ=` 或换行，时区只用独立的 IANA `timeZone` 字段。
- 只有任务、输入或 `executionOptions` 变化时才按当前包校验：只改名称、日历、重叠策略、补触发窗口或暂停状态的 PATCH，以及已提交 `requestId` 的创建重试，都不读取当前包，因此原任务删除后仍能修复、暂停或确认原安排。
- 创建、修改、删除、触发和预览要求 API 进程能连接 `TEMPORAL_ADDRESS`，连接失败或超过 10 秒返回 503 `engine_unavailable`；读取不连接 Temporal。
