# SignalDeck

SignalDeck 是一个面向 LLM agent 的自托管流水线运行器：用 YAML 定义 Workflow Package，手动或按计划启动多 agent 工作流，并在统一的单用户界面中查看运行证据、输出、模板和报告。

## 当前状态

当前开发档位为 **MVP**，围绕本地内网个人使用验证工作流的端到端闭环，并保持现有数据、密钥与运行快照约束。此处只是派生摘要，完整状态以 [`STATUS.md`](STATUS.md) 为准。

## 快速开始

启动需要 Docker 和 Docker Compose v2；执行包含 agent 的工作流还需要可用的模型提供商配置。

```bash
git clone https://github.com/coachpo/signaldeck.git
cd signaldeck
./start.sh
```

启动脚本构建并运行本地/演示组合栈，默认在 `http://localhost:8080` 提供应用；可用 `APP_PORT` 覆盖端口。按 `Ctrl+C` 停止前台进程；需要停止并删除容器时运行：

```bash
docker compose down
```

首次打开应用后，在 **Model Connections** 中保存并测试模型提供商配置，再到 **Workflow Packages** 选择预置演示包、选择包内 workflow、填写输入并查看启动检查结果。满足所需模型和工具依赖后启动运行，在 **Runs** 查看证据和输出。两个预置包是只读的；需要修改时复制为自己的包，YAML 源文件位于 [`demo/`](demo/)。

根目录的 `docker-compose.yml`、根 `Dockerfile` 和 `start.sh` 仅用于本地/演示组合栈；拆分部署使用 backend、frontend 两类镜像，scheduler 复用 backend 镜像。配置示例见 [`docker/compose.production.example.yml`](docker/compose.production.example.yml)。

## 主要能力

- Workflow Package：在一个 YAML 包中声明输入、包内 agent、输出 schema、工具能力、私有 MCP、HTTP 操作和工作流图。
- Scheduled Task：按 interval、daily、weekly 或 monthly 规则和 IANA 时区将到期任务物化为普通运行。
- Run evidence：保留不可变包快照、输入、步骤、agent/HTTP 操作证据、队列进度、重试、失败信息和最终输出。
- Model Connections：保存全局模型提供商绑定；API key 只写入、不在读取接口中返回。
- Templates 与 Reports：创建和编辑模板，编译生成、编辑并下载 Markdown 报告快照。

## 文档

- [`docs/README.md`](docs/README.md)：文档索引与权威边界。
- [`docs/产品说明.md`](docs/产品说明.md)：产品范围、流程、需求和验收。
- [`docs/架构说明.md`](docs/架构说明.md)：当前组件、数据流、部署边界和架构例外。
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：开发环境、启动、检查、测试、工作流和完成定义。
- [`docs/开发规范.md`](docs/开发规范.md)：项目特有的技术和实现规则。
- [`docs/源代码规模与职责规则.md`](docs/源代码规模与职责规则.md)：通用的规模与职责规则。
