# SignalDeck

SignalDeck 是供可信单用户使用的自托管 Agent 工作流平台：选择任务、填写业务信息、通过 Temporal 执行并阅读结果，也可保存常用配置或设置重复执行。专家使用同一份 YAML 制作可复用 Agent 和声明式 DAG，检查完整调用证据。

## 当前状态

当前开发档位为 **MVP**，围绕本地内网个人使用验证工作流的端到端闭环，并保持现有数据、密钥与运行快照约束。此处只是派生摘要，完整状态以 [`STATUS.md`](STATUS.md) 为准。

**SD-TARGET-001、简化操作 S1–S6 和工作流解耦均已完成本地闭环验收**，工作流解耦实现已合入 `main`；版本与验证范围以 [`STATUS.md`](STATUS.md#已完成迭代) 为准。所有保存的 Workflow 使用同一任务/输入/结果路径，工作流数据独立分发；原验收及集成复验见[解耦验证记录](docs/工作流解耦方案.md#验证记录)。当前产品合同和技术边界已融入正式文档；本地验收不代表生产部署验证。

## 快速开始

启动需要 Docker 和 Docker Compose v2；执行包含模型策略 Agent 的工作流还需要可用的模型资源配置。

```bash
git clone https://github.com/coachpo/signaldeck.git
cd signaldeck
./start.sh
```

启动脚本构建并运行本地/演示栈，默认应用地址为 `http://localhost:8080`，可用 `APP_PORT` 覆盖端口。后台启动、查看状态和停止使用同一脚本，以保持 Compose 项目名、数据目录和插件配置一致：

```bash
./start.sh --detach
./start.sh status
./start.sh logs worker
./start.sh stop
./start.sh down
```

`stop` 停止服务；`down` 删除本栈容器与网络，两者均保留数据。前台启动后按 `Ctrl+C` 也会停止服务。默认 Compose 项目名为 `signaldeck-target-local`，数据库、Temporal 历史、产物和固定 Core 执行环境保存在仓库下 `.signaldeck-target/`；可用 `COMPOSE_PROJECT_NAME` 和 `SIGNALDECK_DATA_DIR` 指定另一套独立实例。此栈不复用旧版数据卷，不自动迁移、重置或删除旧实例数据。

首次打开应用进入普通模式的**任务**页。选择市场研究、综合资料研究、整理笔记或保存原文，填写业务信息并检查准备情况；缺少连接时按页面提示就地配置，再开始执行。保存原文不需要模型，研究类任务需要可用模型及相关插件。**结果**展示正文、回执、来源和实际状态，可重跑、修改输入或设置重复执行。**设置**管理显示偏好和已连接服务；开启专家模式后可以制作工作流、配置完整资源与插件并检查技术证据。任务目录同时包含所有已保存的自定义 Workflow，无需改前端代码。可选示例首次导入时只创建缺失 key；可直接编辑，后续启动不会覆盖同名包。示例说明与 YAML 见 [`demo/`](demo/)。

示例 YAML 独立于 Core 可执行制品。Compose 默认只读挂载 `./demo`；可用 `SIGNALDECK_WORKFLOW_DATA_SOURCE=/absolute/path/workflows` 指定其他已有目录，或用 `SIGNALDECK_WORKFLOW_DATA_DIR='' ./start.sh --detach` 禁用示例导入。空平台仍可通过专家制作或通用 `POST /api/workflow-packages/import` 导入工作流；只改 YAML 不改变 Core digest，也无需重建前端。已有 key 的更新需要显式普通保存，重启不会自动升级。详见[独立数据导入](docs/工作流解耦方案.md#独立数据导入与分发)。

默认启用 Finance、Digital Oracle 和 Notes 三个独立插件进程；Finance 的模板/报告页面位于 `http://localhost:8091`，Notes 的只读笔记页面位于 `http://localhost:8093`（可通过 `NOTES_PORT` 改写端口），也可从**设置 → 已连接服务**或专家插件管理的页面入口进入。可通过 `SIGNALDECK_PLUGINS` 指定逗号分隔的插件集合，例如：

```bash
SIGNALDECK_PLUGINS=notes ./start.sh --detach
```

空值只启动通用平台。启动时 bootstrap 注册缺失的本地插件描述与默认资源，保留已有配置；插件不可用时可在修复服务后运行 `./start.sh refresh-plugins` 刷新已选插件的 release。使用自定义环境变量时，后续状态、刷新和停止命令也应使用相同设置。插件使用说明见 [`plugins/README.md`](plugins/README.md)。

普通连接选择由部署方提供。默认挂载 [`docker/connection-presets.local.json`](docker/connection-presets.local.json)，其中只有与本地 bootstrap 一致的 Notes 保存位置（`research`）及 Finance 查询范围（`MSFT`、`AAPL`）；它不配置模型，也不证明相关插件当前在线。研究任务使用的 `research-model` 需要部署方填入已验证的服务地址、模型及凭据字段说明，然后通过只读文件提供给 Core：

```bash
SIGNALDECK_CONNECTION_PRESETS_FILE=/absolute/path/connections.json ./start.sh --detach
```

此变量在宿主机表示文件路径；Compose 将它挂载到容器固定路径 `/etc/signaldeck/connection-presets.json`。文件只包含非敏感配置，密钥由操作者在任务页输入。预设不会自动部署、登记或替换服务；普通用户仍需选择并确认账户、范围和保存位置。文件格式及部署方配置说明见 [插件接入](docs/writing-extensions.md#普通模式的连接选择)。

栈中的 API、命令 dispatcher、固定制品 worker 和 Temporal 分别运行；浏览器关闭不停止后台执行。根 `Dockerfile` 仅将前端 Nginx 和 API 合并为本地/演示镜像，Temporal 使用持久 SQLite 的 `start-dev` 服务。拆分镜像配置示例见 [`docker/compose.production.example.yml`](docker/compose.production.example.yml)，需要另行提供 PostgreSQL 和 Temporal 服务；本地组合栈不代表生产部署验收。

## 主要能力

- 任务：从保存的 Workflow 自动发现任务，按声明生成输入；支持完整 JSON、就地连接、开始前设置核对，以及常用输入、收藏和置顶。
- 结果：正文/回执优先，保留来源、缺失、附件和真实状态；支持全历史搜索、筛选、排序、分页以及重跑和输入复用。
- 自动执行：从任务或结果继承输入，用常用频率与明确时区安排重复执行，查看 Temporal 返回的时间、同步状态和触发来源；复杂 cron 与高级策略保留。
- 专家工作区：同一 YAML 的属性编辑、编译诊断、图视口、完整资源/插件配置及运行快照与调用证据。
- Finance：独立插件提供已有格式生成报告、具体报告阅读/下载，以及专家模板制作；Core 不拥有模板或报告数据。

当前流程与验收要求见 [`产品说明`](docs/产品说明.md)，简化操作的历史验证结果与范围见 [`Sprint 独立验收索引`](docs/planning/sprint-verification.md)。

## 文档

- [三项实测优化验证](docs/planning/observed-gaps-verification.md)：输出上限、只读/写入不确定性与Notes来源过滤的本地交付记录。

- [`docs/README.md`](docs/README.md)：文档索引与权威边界。
- [`docs/产品说明.md`](docs/产品说明.md)：产品范围、流程、需求和验收。
- [`docs/架构说明.md`](docs/架构说明.md)：当前组件、数据流、部署边界和架构例外。
- [`docs/工作流解耦方案.md`](docs/工作流解耦方案.md)：已实施的工作流解耦契约、独立数据导入、历史呈现影响与验证证据。
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：开发环境、启动、检查、测试、工作流和完成定义。
- [`docs/开发规范.md`](docs/开发规范.md)：项目特有的技术和实现规则。
- [`docs/源代码规模与职责规则.md`](docs/源代码规模与职责规则.md)：通用的规模与职责规则。
