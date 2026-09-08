# SignalDeck

SignalDeck 是供可信单用户使用的自托管 Agent 工作流平台：用 YAML 定义可复用 Agent 和声明式 DAG，通过 Temporal 手动或定时执行，并检查运行证据、产物及独立插件提供的业务结果。

## 当前状态

当前开发档位为 **MVP**，围绕本地内网个人使用验证工作流的端到端闭环，并保持现有数据、密钥与运行快照约束。此处只是派生摘要，完整状态以 [`STATUS.md`](STATUS.md) 为准。

**SD-TARGET-001 已实现并完成本地闭环验收**，详见 [`STATUS.md`](STATUS.md#已完成迭代)。当前产品合同和技术边界已融入正式文档；本地验收不代表生产部署验证。

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

首次打开应用后，在 **Resources** 创建模型资源，资源 ID 与包内 `modelRef` 一致（预置示例使用 `research-model`），填入模型配置并单独写入凭据。在 **Plugins** 确认所需插件和工具可用，然后在 **Workflow Packages** 打开示例包，选择 workflow、填写输入并启动。**Runs** 展示运行图、调用证据、状态与产物。预置包首次启动时写入；可直接编辑，后续启动不会覆盖同名包。示例说明与 YAML 见 [`demo/`](demo/)。

默认启用 Finance、Digital Oracle 和 Notes 三个独立插件进程；Finance 的模板/报告页面位于 `http://localhost:8091`，也可从 **Plugins** 的页面入口进入。可通过 `SIGNALDECK_PLUGINS` 指定逗号分隔的插件集合，例如：

```bash
SIGNALDECK_PLUGINS=notes ./start.sh --detach
```

空值只启动通用平台。启动时 bootstrap 注册缺失的本地插件描述与默认资源，保留已有配置；插件不可用时可在修复服务后运行 `./start.sh refresh-plugins` 刷新已选插件的 release。使用自定义环境变量时，后续状态、刷新和停止命令也应使用相同设置。插件使用说明见 [`plugins/README.md`](plugins/README.md)。

栈中的 API、命令 dispatcher、固定制品 worker 和 Temporal 分别运行；浏览器关闭不停止后台执行。根 `Dockerfile` 仅将前端 Nginx 和 API 合并为本地/演示镜像，Temporal 使用持久 SQLite 的 `start-dev` 服务。拆分镜像配置示例见 [`docker/compose.production.example.yml`](docker/compose.production.example.yml)，需要另行提供 PostgreSQL 和 Temporal 服务；本地组合栈不代表生产部署验收。

## 主要能力

- Workflow Package：用同一份结构化定义或 YAML 编辑独立 Agent 和声明式 DAG，检查控制、输入映射和条件依赖。
- Resources 与 Plugins：配置模型连接、限定工具资源和进程外插件；凭据只写入，读取不返回密钥值。
- Runs：从不可变定义和资源绑定快照启动，查看节点状态、调用归属、依赖关系与内容寻址产物，支持取消和新 Run 重跑。
- Scheduled Tasks：使用 cron、IANA 时区、重叠策略和错过窗口配置定时触发，并查看每次触发及其运行来源。
- Finance：通过独立插件提供市场数据工具、Templates 与 Reports，核心平台通过工具契约和页面链接访问。

## 文档

- [`docs/README.md`](docs/README.md)：文档索引与权威边界。
- [`docs/产品说明.md`](docs/产品说明.md)：产品范围、流程、需求和验收。
- [`docs/架构说明.md`](docs/架构说明.md)：当前组件、数据流、部署边界和架构例外。
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：开发环境、启动、检查、测试、工作流和完成定义。
- [`docs/开发规范.md`](docs/开发规范.md)：项目特有的技术和实现规则。
- [`docs/源代码规模与职责规则.md`](docs/源代码规模与职责规则.md)：通用的规模与职责规则。
