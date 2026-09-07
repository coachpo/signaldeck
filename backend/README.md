# SignalDeck Backend

SignalDeck 的 FastAPI backend，负责 Workflow Package、Scheduled Task、Model Connection、Run evidence，以及静态扩展提供的 Templates/Reports API。

安装与普通启动见根 [`README.md`](../README.md)；开发环境、独立 API/scheduler 启动和全部验证命令集中在 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。项目开发档位与部署事实以 [`STATUS.md`](../STATUS.md) 为准。

## 入口与运行前提

- API 入口为 `app.main:app`，worker 入口为 `app.workers.run_scheduler`。API 入队后需要 scheduler 才会执行运行。
- 两个进程共享 PostgreSQL 和 `AGENT_PLATFORM_ENCRYPTION_KEY`。模型 API key 与 package secret binding 静态加密；runtime 配置默认值和生产模式约束见 [`架构说明`](../docs/架构说明.md#接口与安全边界)。
- `/health` 仅检查进程存活；`/ready` 检查数据库连接，不验证 scheduler 或 provider。
- 本地组合栈由根 `start.sh` 启动。拆分部署中的 scheduler 复用 backend 镜像，不发布 HTTP 端口。

## API 与模块导航

| 入口 | 实现责任 |
| --- | --- |
| `/api/workflow-packages` | YAML authoring、manifest validation/import/export、secret bindings、preflight 与 launch。 |
| `/api/schedules` | 计划定义、临时 preview、run-now 和 fire history。 |
| `/api/model-connections` | 全局模型绑定、connection test 和 capability probe。 |
| `/api/tools` | 只读的 server-declared tool catalog。 |
| `/api/runs` | 运行列表、详情、cancel、delete、root-parameter rerun 与 provenance。 |
| `/api/v1/templates`、`/api/v1/reports` | Finance 静态扩展挂载的模板和报告 API。 |

路由契约由 `app/api/` 和 `app/schemas/` 定义；服务、运行时及持久化责任见 [`架构说明`](../docs/架构说明.md)，表与级联关系见 [`数据模型`](../docs/data-model.md)，扩展入口见 [`扩展编写`](../docs/writing-extensions.md)。用户流程与 schedule/rerun 语义以 [`产品说明`](../docs/产品说明.md) 为准。

## Scheduled Task 请求契约

未保存 preview 使用 `POST /api/schedules/preview`，保存后的 preview 使用 `POST /api/schedules/{scheduleId}/preview`；两者只计算临时结果，不创建 fire 或 run。input template 必须是 JSON object，支持 `schedule`、`fire`、`window`、`lastRun`、`vars` 下允许的 placeholder；完整占位符保留 JSON 类型，嵌入文本的 placeholder 转为字符串，最终结果仍须通过 workflow input schema。

schedule read 省略 `inputTemplate` 和 `templateVars`，客户端需要保留显式 draft。`POST /api/schedules/{scheduleId}/run-now` 要求 `idempotencyKey` 和带时区的 `scheduledFor`，通过相同的 scheduled-run 路径创建 manual fire。请求字段以 [`schemas/schedule.py`](app/schemas/schedule.py) 为准。

## 测试数据库

[`tests/conftest.py`](tests/conftest.py) 使用真实 PostgreSQL 和 UUID 隔离的临时数据库，provider 路径使用 mock 或本地 fake server。pytest fixture 与 Playwright backend 启动器的数据库准备不同；环境变量优先级、自动 Docker 启动、数据库权限和运行命令统一见 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。
