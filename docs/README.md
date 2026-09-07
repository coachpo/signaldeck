# 文档索引

本项目的规范文档按唯一权威范围组织。其他位置只链接权威内容，不复制同一事实。

## 规范文档

| 文档 | 权威范围 |
| --- | --- |
| [`../README.md`](../README.md) | 项目入口、安装、普通启动和状态摘要；状态摘要以 [`STATUS.md`](../STATUS.md) 为准。 |
| [`../STATUS.md`](../STATUS.md) | 开发档位、生命周期、部署、使用对象、数据、兼容政策以及允许和禁止的变更。 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 开发环境、开发启动、检查、测试、构建、开发工作流、由开发档位选择的当前开发策略、共享原则和完成定义。 |
| [`产品说明.md`](产品说明.md) | 产品问题、用户、当前交付目的、范围、流程、需求和验收。 |
| [`架构说明.md`](架构说明.md) | 当前系统边界、组件职责、依赖方向、数据流、部署模型、质量属性和架构例外。 |
| [`开发规范.md`](开发规范.md) | 项目特有的代码风格、评审要求和技术实现规则。 |
| [`源代码规模与职责规则.md`](源代码规模与职责规则.md) | 与项目技术无关的源代码规模、职责自检和拆分规则。 |

`CONTRIBUTING.md` 中的[当前开发策略](../CONTRIBUTING.md#当前开发策略)由 `STATUS.md` 的精确开发档位选择，是静态执行默认值，不是新的事实权威或授权来源；共享设计原则、实现原则和完成定义也由该入口提供。开发规范负责项目特有规则，规模规则是独立专项策略。

## 专项文档

- [`迭代目标.md`](迭代目标.md)：SD-TARGET-001 已接受的终态设计、契约边界、已确定的 Temporal 选型与目标验收；冻结提交和用户补充决定的引用以 [`STATUS.md`](../STATUS.md#冻结迭代目标) 为准，当前实现仍查产品和架构文档。
- [`data-model.md`](data-model.md)：PostgreSQL 表、运行快照和数据完整性边界。
- [`writing-extensions.md`](writing-extensions.md)：静态 backend extension 的编写契约。
- [`handover-deps-follow-up.md`](handover-deps-follow-up.md)：依赖升级遗留问题的当前状态、解锁条件和验证命令。
- [`../frontend/DESIGN.md`](../frontend/DESIGN.md)：前端设计系统和界面实现规则。
- [`../backend/README.md`](../backend/README.md)：backend 配置与 API 路由入口；开发命令统一见贡献指南。

[`../README_CN.md`](../README_CN.md) 保留为中文入口，安装和普通启动以根 `README.md` 为准。

`AGENTS.md` 文件是代理工作指引，不属于本规范文档集合；各子目录指引只在对应子树内生效。
