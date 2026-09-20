# 项目状态

开发档位：MVP

## 生命周期

SignalDeck 当前以本地开发调试和核心产品闭环验证为交付阶段。开发档位选择 [`CONTRIBUTING.md`](CONTRIBUTING.md#当前开发策略) 的静态执行默认值；核心流程与验收由 [`产品说明`](docs/产品说明.md) 定义，不构成对生产运行的承诺。

## 部署与使用

部署边界是本地内网，使用对象是个人和单一操作者。项目优先保持本地启动、调试、观察和日常使用的便利，但不因此放松正确性、数据完整性、密钥保护和必要验证。

应用、Core API 和经网关公开的插件业务 API 无需访问口令；资源与模型凭据加密保存，工具授权、插件业务 scope 和内部接口隔离照常生效。

2026-09-19 核验时，capy 实例（部署仓库 `coachpo/curse` 的 `signaldeck` Compose 项目，拓扑见 [capy 适配说明](.agents/skills/signaldeck-ops-inspect/references/capy.md)）运行应用镜像 `ghcr.io/coachpo/signaldeck:v0.2.5@sha256:567d812d89c42da7db1495636516116c0bb1715b425f92b7ea1e7220e476e601`，由该仓库 `signaldeck/backend.env` 的 `SIGNALDECK_VERSION` 固定。插件当前发布为 Finance 1.5.0（服务 `finance-bb73a798`，v0.2.2 构建）、Digital Oracle 1.0.0（`digital-oracle-b10785f8`，v0.2.0 构建）和 Notes 1.3.0（`84c3ec46` 构建），Finance 与 Oracle 的镜像 digest 固定在 `backend.env`；v0.2.5 的 Finance 与 Notes 制品有变化但未部署；单镜像合并后三个插件的制品摘要都会变化，下次发布的插件升级按[插件升级](.agents/skills/signaldeck-release-deploy/references/plugin-upgrade.md)对三者同时执行，待办。没有 Run 绑定被取代的插件发布，这些服务已从 Compose 中移除，`legacy-plugins` profile 不再存在；它们在目录中的历史发布记录保留，页面挂载不再可达。实例导入了示例包 `watchlist_price_events`，定时任务 `watchlist-price-events-weekday-1645` 在纽约时区工作日 16:45 扫描 `finance-market-data` 中的自选股。以上是核验时的事实，不代表持续健康。

仓库配置不能证明实际实例的部署、外部用户或数据状态；当前未核实“没有外部用户”或“没有不可丢弃数据”。MVP 档位不替代这些事实，也不授予数据重置权限。

## 数据与兼容性

Core 与插件的表由 SQLAlchemy `create_all` 初始化，它只创建缺失的表，不修改已有表；项目没有迁移框架，也没有旧数据自动迁移路径。切换应用镜像前，须用新镜像对现有数据库运行只读的 `schema_compatibility` 检查（命令见[部署说明](docker/deployment.md)）。Core 运行历史没有自动清理入口；Temporal 已完成执行的保留期见部署说明，数据归属与不可变边界见[数据模型](docs/data-model.md)。

当前没有单独声明的长期外部 API、配置或数据库 schema 兼容承诺；变更仍不得泄露 secret、破坏运行快照或绕过数据完整性校验。

## 允许与禁止的变更

涉及本地数据库重建、数据删除或兼容行为变化时，须在变更中说明影响并通过适用验证。

删除、重置或迁移现有实例数据，以及提交、推送、发布、部署和其他外部写入，都需要当前任务的明确授权；一次验收或以往任务的授权不构成通用授权。

不得把根 Compose 当作正式部署入口（正式部署见[部署说明](docker/deployment.md)），或把 PostgreSQL、Temporal 并入应用镜像；业务插件与应用共用同一个镜像，但不得因此合并它们：插件仍是独立服务、独立进程、独立虚拟环境和独立制品身份，并由与应用分开的 `SIGNALDECK_PLUGIN_IMAGE` 固定，Core 不得导入插件代码；不得在未重划范围时加入[产品范围](docs/产品说明.md#产品范围)列出的非目标，例如认证/RBAC、多租户或插件市场；不得移除 secret 加密与脱敏、工作流包解析安全、确定性编译、运行不可变快照或仓库必需检查。

部署转为公网或生产环境，或确认存在外部用户、真实或不可丢弃数据、明确的兼容承诺和安全验收时，须重新评估本状态、开发档位及相关架构边界。
