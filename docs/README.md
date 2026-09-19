# 文档索引

本项目的规范文档按唯一权威范围组织。其他位置只链接权威内容，不复制同一事实。

## 规范文档

| 文档 | 权威范围 |
| --- | --- |
| [`../README.md`](../README.md) | 项目入口、安装、普通启动和状态摘要；状态摘要以 [`STATUS.md`](../STATUS.md) 为准。 |
| [`../STATUS.md`](../STATUS.md) | 开发档位、生命周期、部署、使用对象、数据、兼容政策以及允许和禁止的变更。 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 开发环境、开发启动、检查、测试、构建、开发工作流、由开发档位选择的当前开发策略、共享原则和完成定义。 |
| [`产品说明.md`](产品说明.md) | 产品问题、用户、交付目的、范围、流程、需求、A01–A18 执行合同、简化操作体验与 D01–D06 解耦验收。 |
| [`架构说明.md`](架构说明.md) | 当前系统边界、组件职责、依赖方向、数据流、部署模型、质量属性和架构例外。 |
| [`开发规范.md`](开发规范.md) | 项目特有的代码风格、评审要求和技术实现规则。 |
| [`源代码规模与职责规则.md`](源代码规模与职责规则.md) | 与项目技术无关的源代码规模、职责自检和拆分规则。 |

`CONTRIBUTING.md` 中的[当前开发策略](../CONTRIBUTING.md#当前开发策略)由 `STATUS.md` 的精确开发档位选择，是静态执行默认值，不是新的事实权威或授权来源；共享设计原则、实现原则和完成定义也由该入口提供。开发规范负责项目特有规则，规模规则是独立专项策略。

已完成迭代的历史基线和验证范围集中在 [`STATUS.md`](../STATUS.md#已完成迭代)；当前行为由产品、架构和开发规范分别维护。

## 专项文档

- [投研升级实施合同与验证](planning/research-upgrade-readiness.md)：三批的来源修复、实现边界、实际回归、定时闭环和真实模型对照；明确外部数据与模型限制。
- [应用镜像部署](../docker/deployment.md)：正式单应用镜像与独立基础设施/插件的 Compose 配置、发布版本、拉取、启动、持久化与健康验证；部署边界仍以 `STATUS.md` 为准。
- [SignalDeck 运维巡检](../.agents/skills/signaldeck-ops-inspect/SKILL.md)：只读的仓库与部署快照、部署适配说明和证据合同，检测固定版本漂移。
- [SignalDeck 备份与恢复](../.agents/skills/signaldeck-backup-restore/SKILL.md)：静默备份、校验、保留三份、一次性恢复演练及实例切换步骤。
- [SignalDeck 发布与部署](../.agents/skills/signaldeck-release-deploy/SKILL.md)：经明确授权的发布、不可变镜像清单和带门禁的应用部署，以及插件升级步骤。

  以上运维 skill 自带参考文档和脚本，是可执行流程，不与产品或架构文档竞争；执行证据保存在忽略目录 `artifacts/evidence/`。
- [自动化测试消融与精简实测](test-ablation-2026-09-16.md)：全测试入口盘点、同故障对照、保留与精简依据、耗时及未验证范围。
- [三项实测优化交付与验证](planning/observed-gaps-verification.md)：输出上限、读写不确定性与Notes来源过滤的C1–C8映射、同版本真实流程和数据/部署边界。

- [个人使用优化实施计划](planning/personal-use-implementation-plan.md)与[Sprint Backlog](planning/personal-use-sprint-backlog.md)：PU-S1–S6 的24项主体任务、依赖及保留边界。
- [个人使用优化共同验收](planning/personal-use-verification.md)：当前工作区的C1–C11交付映射、各阶段与最终版本验证；区分继承的S1证据及本轮新增验证。
- [`planning/sprint-backlog.md`](planning/sprint-backlog.md)：已完成简化操作 S1–S6 的任务分解及 P/UX 追溯，保留当时自动化验收方式调整。
- [`planning/sprint-delivery.md`](planning/sprint-delivery.md)：原实现阶段的 23 项交付映射和历史验证记录；不替代最终独立验收或当前规范。
- [`planning/sprint-verification.md`](planning/sprint-verification.md)：简化操作的独立验收范围、修复、最终结果和复现入口；版本及后续状态以 `STATUS.md` 为准。
- [`工作流解耦方案.md`](工作流解耦方案.md)：已实施的 Workflow 输入/展示及链接选择契约、独立数据导入、历史呈现影响、原验收与 main 集成证据；原则与模块边界分别以产品说明、架构说明为准。
- [`data-model.md`](data-model.md)：Core/插件数据归属、PostgreSQL 表、不可变运行快照、凭据版本和内容寻址存储。
- [`writing-extensions.md`](writing-extensions.md)：独立进程插件的发布、MCP/工具/schema、resultLinks 页面链接、统一页面与部署挂载协议、资源/效果合同与升级方式；保留原文件路径。
- [`执行引擎比较.md`](执行引擎比较.md)：Temporal、Prefect、Hatchet 的同场景比较、实际证据范围及选型结论；不替代平台整体验收。
- [`../plugins/README.md`](../plugins/README.md)：Finance、Digital Oracle、Notes 独立制品的构建、部署配置和插件级验证。
- [`handover-deps-follow-up.md`](handover-deps-follow-up.md)：依赖升级遗留问题的当前状态、解锁条件和验证命令。
- [`../frontend/DESIGN.md`](../frontend/DESIGN.md)：前端设计系统和界面实现规则。
- [`../backend/README.md`](../backend/README.md)：backend 配置与 API 路由入口；开发命令统一见贡献指南。
- [`../demo/README.md`](../demo/README.md)：示例工作流的资源、输入与用户手工导入说明；示例不属于平台组件，也不作为平台测试或分发依赖。

[`../README_CN.md`](../README_CN.md) 保留为中文入口，安装和普通启动以根 `README.md` 为准。

`AGENTS.md` 文件是代理工作指引，不属于本规范文档集合；各子目录指引只在对应子树内生效。
