# SignalDeck

SignalDeck 是供可信单用户使用的自托管 Agent 工作流平台：选择任务、填写业务信息、通过 Temporal 执行并阅读结果，也可保存常用配置或设置重复执行。专家使用同一份 YAML 制作可复用 Agent 和声明式 DAG，并检查完整调用证据。

## 快速开始

启动需要 Docker 和 Docker Compose v2；执行含模型策略 Agent 的工作流还需要可用的模型资源。

```bash
git clone https://github.com/coachpo/signaldeck.git
cd signaldeck
./start.sh
```

`./start.sh` 构建镜像并在前台运行本地栈，按 `Ctrl+C` 停止。应用默认地址为 `http://localhost:8080`（`APP_PORT`），无需访问口令；Temporal UI 为 `http://localhost:8233`（`TEMPORAL_UI_PORT`）。两者只绑定 `127.0.0.1`。其他生命周期命令使用同一脚本：

```bash
./start.sh --detach      # 后台启动
./start.sh status
./start.sh logs worker   # 跟随指定服务的日志；省略服务名时跟随全部
./start.sh stop          # 停止服务
./start.sh down          # 删除本栈容器与网络
```

默认 Compose 项目名为 `signaldeck-target-local`，数据库、Temporal 历史、产物和固定 Core 执行环境以 bind mount 保存在仓库下被 Git 忽略的 `.signaldeck-target/`。`stop`、`down` 以及 `docker compose down -v` 都不会清除这些目录，不能用来重置数据。另起一套空白实例时，指定新的 `COMPOSE_PROJECT_NAME`、`SIGNALDECK_DATA_DIR` 和不冲突的 `APP_PORT`、`TEMPORAL_UI_PORT`；从另一份检出启动时还要设置不同的 `SIGNALDECK_LOCAL_IMAGE_PREFIX`，否则会覆盖同名的 `:local` 镜像。使用自定义环境变量时，后续 `status`、`logs`、`refresh-plugins`、`stop` 和 `down` 也须带同样设置。清理这样的实例时先运行 `./start.sh down`，再删除它的数据目录和带自定义前缀的 `:local` 镜像；数据目录中的 Core 制品是只读的（文件 0444、目录 0555），删除前先恢复写权限（如 `chmod -R u+w <数据目录>`）。

新实例没有工作流：可在专家模式中制作，或按 [`demo/README.md`](demo/README.md) 通过 `POST /api/workflow-packages/import` 手工导入示例；`demo/` 不是平台组件，见[工作流与平台解耦原则](docs/产品说明.md#工作流与平台解耦原则)。

默认启用 Finance、Digital Oracle 和 Notes 三个独立插件；`SIGNALDECK_PLUGINS` 以逗号分隔选择插件，空值只启动通用平台：

```bash
SIGNALDECK_PLUGINS=notes ./start.sh --detach
```

插件是同一本地镜像的独立角色，不发布宿主机端口，页面经应用端口访问。每次启动都按本次构建生成数据目录中的 `plugin-mounts.json`，只读挂载给 Core 与 Nginx；bootstrap 只登记缺失的插件和默认资源，已登记插件保持原发布。插件代码或打包文件变化后，先用同样的环境变量重新运行 `./start.sh --detach`，重建那一个镜像并替换插件服务；再在本栈运行时执行 `./start.sh refresh-plugins`，它从运行中插件的 `/release` 重新登记所选插件的当前发布并保留启用状态（会重新创建应用容器）。只重建不刷新时 Core 仍登记原发布，调用该插件的运行会以 `plugin_release_unavailable` 失败。

本地重建会原地替换插件服务，旧发布的页面随之不可用；需要保留旧发布时，须为其单独运行服务，并用 `SIGNALDECK_PLUGIN_MOUNTS_FILE=/absolute/path/mounts.json` 提供包含旧挂载的登记（脚本不改写显式指定的文件），格式见[统一插件页面](docs/writing-extensions.md#统一插件页面)。Finance 与 Oracle 访问 SEC 所需的 `EDGAR_CONTACT_EMAIL` 以及 Oracle 的 `FRED_API_KEY` 从 shell 或仓库根目录被 Git 忽略的 `.env` 读取，其他插件配置见 [`plugins/README.md`](plugins/README.md)。

普通模式的连接选择默认读取 [`docker/connection-presets.local.json`](docker/connection-presets.local.json)（Notes 保存到 `research`，Finance 只允许 `MSFT`、`AAPL`，不含模型）；替换时用 `SIGNALDECK_CONNECTION_PRESETS_FILE=/absolute/path/connections.json ./start.sh --detach` 指向一个已存在的文件，格式见[普通模式的连接选择](docs/writing-extensions.md#普通模式的连接选择)。

本地栈使用 local 模式和开发版 Temporal，只用于源码本地运行；服务器部署使用已发布的应用镜像和 [`docker/compose.production.yml`](docker/compose.production.yml)，见[部署说明](docker/deployment.md)。

## 文档

- [`docs/README.md`](docs/README.md)：文档索引与各文档的权威范围。
- [`STATUS.md`](STATUS.md)：开发档位、部署与数据边界。
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：开发环境、检查测试与发布。
- [`docker/deployment.md`](docker/deployment.md)：服务器部署。
