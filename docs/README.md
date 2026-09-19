# 文档索引

每个事实只在一个权威文档中维护，其他位置只链接或简要概括。

## 规范文档

| 文档 | 权威范围 |
| --- | --- |
| [`../README.md`](../README.md) | 项目简介与本地快速开始：`start.sh` 生命周期、本地数据保留、插件选择与刷新、本地连接预设。 |
| [`../STATUS.md`](../STATUS.md) | 开发档位、生命周期、部署与使用边界、当前部署实例、数据与兼容政策，以及允许和禁止的变更。 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 开发环境与依赖、热更新开发启动、测试数据库与 E2E 环境、检查测试与构建、发布，以及由开发档位选择的当前开发策略和完成定义。 |
| [`产品说明.md`](产品说明.md) | 产品范围、非目标与界面合同，工作流与平台解耦原则，任务、制作、服务、运行和重复执行的可观察行为，A01–A18 验收标准、D01–D06 解耦验收和验证边界。 |
| [`架构说明.md`](架构说明.md) | 模块职责与依赖方向、状态归属、工作流边界与已知偏差、前端与 HTTP 的连接和读取路径，以及定义编译与启动、执行恢复与取消、定时执行、Model/Tool Gateway、执行追踪、制品与安全和部署拓扑的实现机制。 |
| [`开发规范.md`](开发规范.md) | 跨边界技术规则：工作流解耦实现、预算与 provider 能力声明、外部 API 与凭据合同、前端规则。 |
| [`源代码规模与职责规则.md`](源代码规模与职责规则.md) | 与项目技术无关的源代码规模阈值、职责自检、拆分和长文件报告规则。 |

## 专项文档

- [`工作流解耦方案.md`](工作流解耦方案.md)：schema/2 默认值、presentation/1 输入与标题、结果选择器、插件链接选择和工作流包独立导入的版本化合同。
- [`执行引擎比较.md`](执行引擎比较.md)：Temporal、Prefect、Hatchet 的同场景比较、选型结论和三个探针的复现方式。
- [`data-model.md`](data-model.md)：Core 与插件的数据归属、PostgreSQL 表、写入身份与冲突代码、不可变运行快照、凭据版本、内容寻址存储，以及 schema 演进与兼容检查规则。
- [`writing-extensions.md`](writing-extensions.md)：独立插件的发布、MCP 工具与 schema、结果页面链接、统一插件页面与挂载、资源和写操作合同、Notes/Finance/Oracle 业务合同、升级方式及普通模式的连接预设。
- [`../docker/deployment.md`](../docker/deployment.md)：正式单应用镜像的 Compose 部署、镜像版本与固定、配置、持久化、更新和健康检查。
- 运维 skill：[只读巡检](../.agents/skills/signaldeck-ops-inspect/SKILL.md)（含 [capy 适配说明](../.agents/skills/signaldeck-ops-inspect/references/capy.md)）、[备份与恢复演练](../.agents/skills/signaldeck-backup-restore/SKILL.md)和[发布与带门禁的部署](../.agents/skills/signaldeck-release-deploy/SKILL.md)，各自附带参考文档和脚本。
- [`../plugins/README.md`](../plugins/README.md)：Finance、Digital Oracle、Notes 独立制品的构建运行、配置、研究来源边界和插件级验证；Finance 与 Notes 的页面和 HTTP API 分别见 [`../plugins/finance/README.md`](../plugins/finance/README.md) 和 [`../plugins/notes/README.md`](../plugins/notes/README.md)。
- [`../frontend/DESIGN.md`](../frontend/DESIGN.md)：前端视觉系统和界面实现规则。
- [`../backend/README.md`](../backend/README.md)：backend 进程与入口、运行模式和 API 路由。
- [`../backend/experiments/ablation/README.md`](../backend/experiments/ablation/README.md)：可选的后端机制消融实验的设计、复现和解释限制。
- [`../demo/README.md`](../demo/README.md)：示例工作流的资源、输入和手工导入；示例不属于平台组件。

`AGENTS.md` 文件是代理工作指引，不属于本文档集合；各子目录的指引只在对应子树内生效。
