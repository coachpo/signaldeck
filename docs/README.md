# 文档索引

本项目的规范文档按唯一权威范围组织。其他位置只链接权威内容，不复制同一事实。

## 规范文档

| 文档 | 权威范围 |
| --- | --- |
| [`../README.md`](../README.md) | 项目入口、安装、普通启动和状态摘要；状态摘要以 [`STATUS.md`](../STATUS.md) 为准。 |
| [`../STATUS.md`](../STATUS.md) | 开发档位、生命周期、部署、使用对象、数据、兼容政策以及允许和禁止的变更。 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 开发环境、开发启动、检查、测试、构建、开发工作流、由开发档位选择的当前开发策略、共享原则和完成定义。 |
| [`产品说明.md`](产品说明.md) | 产品问题、用户、交付目的、范围、流程、需求和已实现的 A01–A18 验收合同。 |
| [`架构说明.md`](架构说明.md) | 当前系统边界、组件职责、依赖方向、数据流、部署模型、质量属性和架构例外。 |
| [`开发规范.md`](开发规范.md) | 项目特有的代码风格、评审要求和技术实现规则。 |
| [`源代码规模与职责规则.md`](源代码规模与职责规则.md) | 与项目技术无关的源代码规模、职责自检和拆分规则。 |

`CONTRIBUTING.md` 中的[当前开发策略](../CONTRIBUTING.md#当前开发策略)由 `STATUS.md` 的精确开发档位选择，是静态执行默认值，不是新的事实权威或授权来源；共享设计原则、实现原则和完成定义也由该入口提供。开发规范负责项目特有规则，规模规则是独立专项策略。

已完成迭代的历史基线和验证范围集中在 [`STATUS.md`](../STATUS.md#已完成迭代)；当前行为由产品、架构和开发规范分别维护。

## 专项文档

- [`planning/sprint-backlog.md`](planning/sprint-backlog.md)：简化操作 S1–S6 的稳定待办和 P/UX 追溯，末尾记录本轮自动化验收方式调整。
- [`planning/sprint-delivery.md`](planning/sprint-delivery.md)：23 项交付、实际验证和待验收范围；不替代规范文档或 SD-TARGET-001 历史。
- [`data-model.md`](data-model.md)：Core/插件数据归属、PostgreSQL 表、不可变运行快照、凭据版本和内容寻址存储。
- [`writing-extensions.md`](writing-extensions.md)：独立进程插件的发布、MCP/工具/schema、资源/效果合同与升级方式；保留原文件路径。
- [`执行引擎比较.md`](执行引擎比较.md)：Temporal、Prefect、Hatchet 的同场景比较、实际证据范围及选型结论；不替代平台整体验收。
- [`../plugins/README.md`](../plugins/README.md)：Finance、Digital Oracle、Notes 独立制品的构建、部署配置和插件级验证。
- [`handover-deps-follow-up.md`](handover-deps-follow-up.md)：依赖升级遗留问题的当前状态、解锁条件和验证命令。
- [`../frontend/DESIGN.md`](../frontend/DESIGN.md)：前端设计系统和界面实现规则。
- [`../backend/README.md`](../backend/README.md)：backend 配置与 API 路由入口；开发命令统一见贡献指南。

[`../README_CN.md`](../README_CN.md) 保留为中文入口，安装和普通启动以根 `README.md` 为准。

`AGENTS.md` 文件是代理工作指引，不属于本规范文档集合；各子目录指引只在对应子树内生效。
