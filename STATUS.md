# 项目状态

开发档位：MVP

## 生命周期

SignalDeck 当前以本地开发调试和核心产品闭环验证为交付阶段。开发档位选择 [`CONTRIBUTING.md`](CONTRIBUTING.md#当前开发策略) 的静态执行默认值；核心流程与验收由 [`产品说明`](docs/产品说明.md) 定义，不构成对生产运行的承诺。

`demo/` 仅存放示例工作流，不属于平台组件；除说明性文档外，平台源码、测试、构建、启动、分发和验证工具不得依赖或引用其内容。当前边界以[产品解耦原则](docs/产品说明.md#工作流与平台解耦原则)为准。下方历史记录中的示例场景、文件、hash 和验证命令只说明当时的实现与证据，不构成现行平台回归要求。

## 已完成迭代

**SD-TARGET-001 已实现并完成本地闭环验收**，实现与修复提交为 `7285cecd274f2ac5416aa5d9d963517e845867ce`。2026-09-08 最终回归覆盖 C1–C19 的 20 个必需用例，综合完成检查通过，无豁免；后端 518 项、前端 169 项单元测试、13 项浏览器 E2E，以及适用静态检查、镜像构建和实际 Compose 集成均通过。

已实现的产品范围与 A01–A18 验收合同归入 [`产品说明`](docs/产品说明.md#验收标准)，模块、执行和数据边界归入 [`架构说明`](docs/架构说明.md)，实现约束归入 [`开发规范`](docs/开发规范.md)。后续维护以这些当前规范为准；原迭代目标文档完成职责后从当前文档包移除。

历史基线保留在 Git：原冻结提交 `bca05dcd666e96561426224b89b0e06aed186a22`，Temporal 定案及切换期数据处置授权补充提交 `afe9e1efebb992170cd52cb3341c0ad7b83f20ac`。需要审计原目标时读取固定版本：

```bash
git show afe9e1efebb992170cd52cb3341c0ad7b83f20ac:docs/迭代目标.md
```

验收使用本地受控模型与业务端点、隔离源码副本和专用测试资源，验证了实际 Worker 中断与固定制品恢复、插件升级、并发写入/未知结果、重复取消与终态证据、定时执行和关闭执行服务后的历史读取。该结果不代表生产部署或真实外部服务可用性；当前实例与数据边界仍以下文为准。

### 简化操作 S1–S6（2026-09-08）

简化操作 S1–S6 的实现及独立验收修复已收录于提交 `6ca0e8e83c70c564cb1042ddc2027153bab35560`，覆盖默认任务/结果/设置、四场景业务表单、就地连接、结果和历史查询、重跑/输入复用/常用配置、Finance 格式使用与制作、重复安排及专家制作/诊断。当前行为与体验验收由 [`产品说明`](docs/产品说明.md) 维护；23 项历史任务映射和原实现阶段证据见 [`Sprint 交付对照`](docs/planning/sprint-delivery.md)。原 A01–A18 合同保持。

实现起点为 `f7ced2f35cae20ab37e94acc9a89007a49143d10`；独立验收当时使用 `05a61151fb6239c0d222630c3e7c722e8c88c5a8` 加尚未提交的实现及修复，随后一并收录于上述提交。原实现阶段的制品摘要、源清单和测试数只标识其历史版本，最终修复及验证结果以 [`Sprint 独立验收索引`](docs/planning/sprint-verification.md) 为准，不将历史测试数作为后续变更后的新验证结果。

独立验收已通过：23/23 必需用例和综合完成检查通过，无豁免；修复后后端 547 项、前端 218 项、Core E2E 19 项、独立 Finance 4 项、实际双离线专项 1 项及适用静态/构建/四档视觉检查通过。修复与版本入口为 [`Sprint 独立验收索引`](docs/planning/sprint-verification.md)，本机闭环报告为 `.steward/goals/sd-ux-all-sprints/verification/report.md`。本机原始截图、日志和闭环附件不进入 Git，新检出通过独立验收索引读取精简结论及复现入口。

用户已明确将 C8 调整为执行者安排 Playwright，无需人员参与；验收范围是自动化体验验证及问题修复复验，不是真实用户无讲解观察，也不证明外部付费供应商或生产部署可用。原实现阶段验证使用隔离 PostgreSQL、Temporal、独立插件和受控 provider，未处置现有实例数据，也未推送或部署。

### 工作流解耦（2026-09-09）

工作流解耦已通过提交 `1db791c54e9e6d3f4ccdf52432daefcc8ef98dfd` 合入 `main` 并推送：所有保存的 Workflow 自动进入任务目录；schema/2 默认值注解、presentation/1 静态输入提示及标题/结果选择、resultLink/1 插件链接均为闭合公开合同；可选工作流 YAML 在 Core 可执行 closure 外通过原子 missing-only 导入。原包解析、编译、Launch、Temporal DAG/Agent 与独立插件执行边界保持，没有新增执行根、场景注册表或逐工作流前端扩展。

实现阶段以 `a3f5158eba369acda563f6eb73b7975b9b2a6785` 为基线在独立 worktree 完成全量回归；集成阶段核对完整补丁与该工作树一致，再在本会话的 `main` 复验重点后端合同、全部前端单元测试、两端静态检查和前端构建。D01–D06、受影响 A01–A18、四场景及实际双离线读取的原验收见[解耦验证记录](docs/工作流解耦方案.md#验证记录)，本次复验见[main 集成验证](docs/工作流解耦方案.md#main-集成验证)。两阶段证据分别记录，不把原全量测试记成本次重跑。

无展示声明的历史记录保留通用确认值、产物与证据，不再按业务字段推测专用正文、标题或报告深链接。大产物选择可延后到附件阅读，不能解释为业务缺失。旧 hash、运行快照和历史 Core/插件清单不改写；实现和集成都没有部署、切换现有实例或处置其数据。

### 三项实测优化（2026-09-11）

在 `a518c65e` 基线上的当前工作区完成三项限定优化：冻结的 provider 输出上限字段与响应校验、只读结果/写入效果不确定性统一投影、Notes 1.2.0 来源引用与显式检索过滤。复用已交付个人使用 S1–S6，没有重建六 Sprint 或纳入 `pu-later-*`。

两份 GOAL 的后续独立闭环复验均为 COMPLETE：个人使用26项、三项实测优化9项必需用例全部通过。固定 Core 为 `a00475e79f99069e9b28a17e9d9923c2c92437a5e438e2e43085ec4c100ecf83`；工作区746项后端、293项前端单元测试、24项浏览器全流程、1项双离线专项、4项Finance专项及适用静态/构建检查通过。最终16个真实Run验证来源集合2→2→2→3、关闭浏览器后的自然定时、读写故障及双离线读取/导出。

实际版本、C1–C11/C1–C8证据及复现入口见[独立闭环复验](docs/planning/observed-gaps-verification.md#独立闭环复验2026-09-11)。本轮provider对 `max_tokens=16` 按16截断，但 `max_completion_tokens=16` 实际报告501个输出token，被系统拒绝并保留用量；此前不同调用的观测保留在历史记录。没有发布或部署，未切换或处置原实例数据；独立测试存储改动未纳入本次提交。

### 通用用量与时间限制（2026-09-16）

累计模型用量和单次输出策略已独立配置，普通任务、专家制作和重复安排复用预算控件；草稿、常用配置、准备核对、启动幂等、历史复用及重跑贯通同一覆盖合同。运行单独冻结覆盖和有效预算，不改原包 hash 或历史快照；常用配置通过新增附属表保存预算，无需修改旧表。达到累计停止线后阻止后续模型和工具调用，缺失必要计量、明确截断及预算耗尽保留证据并停止自动重试。当前合同见[产品说明](docs/产品说明.md)、[开发规范](docs/开发规范.md)和[数据模型](docs/data-model.md)。

本轮覆盖 A03、A07、A10、A12、A15、A17 及任务/复用/自动执行/专家制作体验：后端全量 `uv run pytest` 877 项、前端全量 `pnpm test:run` 428 项通过；Ruff、Black、isort、mypy、ESLint、TypeScript、前端 build 和 `git diff --check` 通过。浏览器全量 27 项中 26 项直接通过；四场景用例先同步已有工作流的新标签，后遇一次 MCP 传输中断，再次隔离复验通过，未定位到具体网络原因。预算专项验证包含草稿刷新恢复、独立快照、预算失败后的调整入口及 375/768/1024/1440 四档布局；后端验证包含三个输出字段的真实省略、额度恰好耗尽、未知计量、截断、恢复和旧快照重投。

回归入口为 `backend/tests/test_execution_budgets.py`、`test_model_budget_failures.py`、`test_model_budget_contract.py`、`test_durable_runtime_budgets.py`、前端预算控件测试及 `frontend/e2e/model-usage.spec.ts`。测试使用隔离 PostgreSQL/Temporal、独立插件和受控模型；没有提交、部署、切换或处置现有实例。超过 300 行的受影响行为文件已按职责规则复核，无未通过项；新增预算输入、摘要及解析分别保留在所属模块。

### 插件统一入口（2026-09-16）

Finance 1.1.0、Notes 1.3.0 通过可选 `pluginUi/1` 声明接入主站常驻布局，业务页面、API 和数据仍由独立插件拥有。主站按只读发布目录生成导航，保留已打开页面、编辑内存及来源结果，支持深链接、前进后退与刷新；旧发布、旧快照和旧链接不改写。部署登记精确绑定制品，组合及拆分网关使用同一生成器，默认取消 Finance/Notes 宿主机端口。合同、模块归属及运行说明分别见[插件接入](docs/writing-extensions.md#统一插件页面)、[架构说明](docs/架构说明.md)和[快速开始](README.md#快速开始)。

验证覆盖 A01、A02、A10、A14、A18 与 D06 的受影响路径。前端 `pnpm test:run --maxWorkers=2` 443 项通过，随后新增/调整的宿主 9 项和共享 UI 9 项专项通过，ESLint、TypeScript、build 通过；默认并发首轮出现 12 项等待/执行超时，降低测试进程并发后全部通过，没有放宽超时或断言。最终集成浏览器 7 项、壳层回归 5 项、Finance 专项 5 项及格式编辑保真检查通过；实际 Notes 确认结果的站内跳转、前进后退、刷新和来源返回均验证，第三个独立页面无需 Core 业务分支。375/768/1024/1440 四档截图保存在本机 `output/playwright/integrated-plugins/`，已检查布局和横向溢出。

后端全量首轮 881 项通过、4 项失败：3 项为新发布后旧测试夹具的版本/UI 字段假设，同步夹具后 Notes 与独立发布相关 15 项通过；另一项为真实 Temporal 测试未在五秒内进入重试，构建负载降低后原测试单独通过（8.68 秒），未修改执行逻辑或测试时间阈值。Ruff、Black、isort、mypy 与 `git diff --check` 通过。页面目录/省略序列化回归在 `backend/tests/test_plugin_pages.py`，宿主、共享桥接、集成入口在 `frontend/src/features/plugin-host/`、`frontend/src/plugin-ui/` 和 `frontend/playwright.integrated.config.ts`；网关及启动脚本回归见 `frontend/gateway/test_generate.py`、`docker/test_plugin_gateway.py`、`docker/test_prepare_plugin_mounts.py` 和 `docker/test_start.py`。

实际 Nginx 门禁、凭据剥离、编码路径、内部接口拒绝、离线上游隔离通过，6 项网关/注册表/启动器单元回归通过。最终组合镜像 `7558fda3c8cb` 与拆分前端镜像 `8e075f5eb24e` 构建通过，拆分入口 `nginx -t` 通过。独立 Compose 在 28188 端口验证真实 Core、Finance、Notes 页面及 API，空插件启动仍可读取主站；保持相同 app 镜像、仅变更注册表摘要也会重新创建 app 并载入新路由。该轻量 Compose 验证未启动 dispatcher、worker 或 Temporal，真实持久执行由上述隔离 E2E 的 Notes Run 覆盖。测试容器、网络、数据和临时配置已清理，未切换原有 8080 实例。

超过 300 行的受影响行为文件已复核：`frontend/src/components/layout.tsx` 保持应用布局职责，插件状态和协议在独立 feature 内；E2E 启动脚本只编排隔离测试服务，`tool_contracts.py` 保持发布/工具合同归属，无未通过项。验证使用独立数据库、进程及 Compose 项目，没有提交、部署到现有实例或改写其数据；旧服务的持续保留须由部署方为原挂载配置独立上游，本地启动器不会自动迁移旧发布。

### 投研升级实施准备（2026-09-16）

本轮清理三批投研升级前的现有数据适配问题：Reddit RSS 日期与修订截止、Yahoo 未注明日期新闻、Treasury 平均利率语义与取样、Form 4 原始 XML/非衍生交易边界、Oracle 凭据配置提示及 Kalshi 定点数据。保留现有插件职责、闭合工具字段和冻结制品边界；不改 Core、前端、YAML 或现有实例数据。来源行为见[插件说明](plugins/README.md#research-source-boundaries)，具体修复与验证见[投研升级记录](docs/planning/research-upgrade-readiness.md)。

三批的时间/证据、真实财务与原文、可选信号和显式监测合同已整理，当前未发现阻止第一批编码与受控验证的访问或配置缺口。11 个外部端点的有限只读探测均返回有效非空样本；这只代表当次连通性，不替代真实财务提取、模型研究或跨日监测验收。准备阶段尚未实施三批新能力；后续实现见下一节。准备阶段未提交、发布或部署。SEC 工具说明修正会改变新进程的契约摘要，实际安装须使用新不可变制品并保留旧端点，不能覆盖冻结 Run 的绑定。

### 投研升级三批主流程（2026-09-17）

当前 worktree 已同步 main `6f972043`（包含 `80ac19ef` 无需访问口令变更），完成 SEC 财务与原文章节、结构化证据/数值/阈值校验、可选社交/内部人/精确预测事件、原有 FRED 宏观来源及显式研究监测。业务实现属于 Finance/Oracle，研究与定时监测拓扑在同一独立 YAML 包，未修改 Core 或前端业务代码。完整证据用于校验/存储，模型只读取有界投影；非法单条论断被拒绝并披露，旧修订不能冒充当前值。报告保存与下载使用同一规范正文。

后端主体回归 1090 项通过，真实 Temporal/MCP/PostgreSQL 专项通过 research、两次自然定时、无效/变化分支与报告一致性；后续修正另有针对性复验。镜像构建、隔离 Compose、新监测表及操作幂等验证通过。真实模型基础报告生成成功；社交对照取得新增样本，但两阶段输出截断，按失败分支保留缺口，未证明增强质量改善。期权、付费共识和全面宏观源扩展仍未启用。详细命令、版本和实际限制见[实施验证](docs/planning/research-upgrade-readiness.md#实施验证)。

实现已通过提交 `2d0b49b8` 合入 `main` 并推送，随 v0.2.0 发布；实例部署情况见[部署与使用](#部署与使用)。实现过程未处置既有实例数据。新工具/字段改变插件契约与制品摘要，实际安装仍须使用新不可变发布与端点，保留旧 Run 的绑定。新增 Finance 监测表仅由新插件 `create_all` 初始化，不回写历史报告。

### K 线事件识别（2026-09-19）

Finance 1.3.0 新增只读工具 `price_events_lookup`：对至多 5 个已授权美股证券的已完成纽约交易日，按 17 条闭合规则识别收盘新高/新低、突破、缺口、大幅涨跌、缺口回补、岛形反转、均线/MACD/RSI/布林带信号、窄幅整理、内包线、放量、连涨连跌和相对强弱，并给出最新价格状态。范围限定为美股日线和 `allowedSymbols` 内的自选证券；结果只描述历史价格，不含回测、事件后收益统计或交易建议。`MarketDataService` 的指标序列计算抽到 `indicator_series.py` 供两条路径共用，`indicators_lookup` 输出与重构前逐字一致。未修改 Core、前端或插件存储；合同见[插件接入](docs/writing-extensions.md#finance-k-线事件合同)。

新增 24 项测试覆盖各条规则、交易日完成时点、合同与授权拒绝、截断及真实 MCP 往返；连同 Finance、研究与独立插件相关回归共 536 项通过，后端 ruff/black/isort 通过。Finance 镜像构建通过，镜像内发布描述为 1.3.0。真实 Yahoo 日线的 4 只证券加基准扫描输出符合发布 schema；实测确认日线已按拆股调整、未按分红调整，除息低开可能被识别为向下缺口。规则没有用真实行情评估准确率。

实现已通过提交 `3532add8` 合入 `main` 并推送，随 v0.2.0 发布；capy 实例的插件升级见[部署与使用](#部署与使用)。新工具改变 Finance 合同与制品摘要，实例启用须登记新的不可变发布和 endpoint，并保留旧 Run 的原绑定。

### K 线事件复权与降噪（2026-09-19）

Finance 1.4.0 的 `price_events_lookup` 改为按分红复权价格识别事件：复权因子取 provider 复权收盘价与收盘价之比，以最后一个完成交易日为基准，同一分红区段内的浮点噪声不拆分因子；每个事件增加 provider 原始收盘价 `rawClose`，每只证券标明 `priceBasis`，缺少复权收盘价时退回拆股调整价格并告警。新增 `near_high_low`、`drawdown`、`failed_breakout`、`window_move`、`spike_reversal`、`engulfing`、`pin_bar` 七条规则；`new_high_low`、`breakout`、`relative_strength` 增加 `minBaseSessions`，默认不过滤。范围仍是美股日线和 `allowedSymbols` 内的自选证券，不含回测或事件后收益统计；定时扫描、研究证据和监测接入尚未实施。未修改 Core、前端或插件存储；合同见[插件接入](docs/writing-extensions.md#finance-k-线事件合同)。

新增 11 项、调整 4 项规则与工具测试；Finance、研究与插件相关回归共 482 项通过，改动文件的 ruff/black/isort 通过。真实 Yahoo 日线复核（28 只美股、近 250 个交易日、默认参数）：除息日被识别的向下缺口从 9 个降到 2 个；每只每年约有 `window_move` 2.1、`spike_reversal` 0.8、`near_high_low` 6.7、`engulfing` 9.0、`failed_breakout` 10.6、`pin_bar` 11.6、`drawdown`（10%）15.4 个事件；`minBaseSessions=20` 使 60 日新高/新低从 34.2 个降到 3.8 个，相对强弱从 34.1 个降到 3.3 个。规则没有用真实行情评估预测准确率。

实现已通过提交 `792ac294` 合入 `main` 并推送，随 v0.2.1 发布；capy 实例的插件升级见[部署与使用](#部署与使用)。新规则和字段改变 Finance 合同与制品摘要，实际启用须登记新的不可变发布和 endpoint，并保留旧 Run 的原绑定。

### 自选股定时扫描（2026-09-19）

Finance 1.5.0 的 `price_events_lookup` 可以省略 `symbols`，扫描 `finance-market-data` 连接 `allowedSymbols` 中的全部证券（至多 50 只），只返回有事件的证券，并给出实际扫描的 `scannedSymbols` 和最新已完成交易日 `latestSession`；`includeDigest` 生成中文 Markdown 摘要。该工具发布的超时由默认 30 秒改为 120 秒。新增示例工作流包 `demo/watchlist_price_events.yaml`（任务名“自选股 K 线扫描”）：用确定性步骤调用扫描工具，固定 5 条低频规则；只有最新已完成交易日就是扫描当天、且事件数达到 `minEvents` 时，才用 `reports_create` 把摘要保存为 Finance 报告，不调用模型。定时由平台的重复安排配置，建议纽约时间工作日 16:45。未修改 Core 或前端；合同见[插件接入](docs/writing-extensions.md#finance-k-线事件合同)，用法见[示例工作流](demo/README.md#watchlist-k-line-scan)。

新增 4 项、调整 2 项工具测试；Finance、研究与插件相关回归共 486 项通过，改动文件的 ruff/black/isort 通过。工作流包经 Core 解析器编译，并按新 Finance 发布描述通过确定性工具合同校验。另用不入库的临时端到端用例，在真实 Temporal 开发服务器、PlatformStore 和 MCP 插件调用下执行三次：周五收盘后有事件时保存报告；周六，以及 `minEvents=3` 时只扫描不保存；报告正文与摘要一致。真实 Yahoo 日线下，50 只证券的自选股扫描约 12 秒完成；按近 120 个交易日计算，这组规则约为每只每年 12.9 个事件，即每只每个交易日约 0.05 个。

Core 编译条件时原先按精确类型识别字面量，而 YAML 导入的整数是 ruamel 的 `ScalarInt`，所以条件里直接写数字会被判为类型不兼容。随后的 Core 修复改为按 `isinstance` 识别字面量，并先判断布尔值；回归用例在 `backend/tests/test_dag_compiler.py`。修复随 v0.2.2 发布，并已部署到 capy。更早版本的 Core 仍会拒绝 YAML 条件里的数字字面量，所以工作流继续使用 `minEvents` 输入，新旧 Core 都能编译。

实现已通过提交 `9ca82a8a` 合入 `main` 并推送，随 v0.2.2 发布并已部署到 capy，见[部署与使用](#部署与使用)。新字段和超时改变 Finance 合同与制品摘要，实际启用须登记新的不可变发布和 endpoint，并保留旧 Run 的原绑定。

### 确定性工具调用的心跳超时修复（2026-09-19）

capy 第一次执行工作流时失败：自选股 K 线扫描手动触发的运行 `0ce3c129`，扫描节点三次尝试都在开始 3 秒后因 `activity Heartbeat timeout` 失败，此时还没有调用插件。原因是确定性 Agent 活动在第一次 await 之前，会同步构造运行冻结的工具目录。在 capy 的 ARM 主机上，Finance 1.5.0 发布（19 个工具）的 `PluginRelease` 校验和 `ToolCatalog` 构造合计约 3.05 秒，期间事件循环被占住，每秒一次的心跳任务无法运行，而该活动的心跳超时是 3 秒。其余同步步骤都在 0.2 秒以内。修复后，`durable_worker.invoke` 在线程中构造工具目录。回归用例在 `backend/tests/test_durable_runtime.py`，它把目录构造人为延长到 3.5 秒：修复前失败，修复后通过。持久执行、工具网关和 Agent 相关的 95 项测试，以及 ruff/black/isort/mypy，全部通过。

实现已通过提交 `19a72de8` 合入 `main` 并推送，随 v0.2.3 发布并部署到 capy，见[部署与使用](#部署与使用)。

### 定时任务跟随 Core 升级（2026-09-19）

v0.2.3 上线后发现，已有定时任务不会跟随 Core 升级。定时任务写入 Temporal 时，action 固定在当时 Core 的任务队列上；而同步只在修订号变化时才重新写入。旧 Core 的 Worker 又会一直保留，所以升级后的触发仍由旧 Core 执行，建立的 Run 也冻结在旧 Core 上。修复后，新增附属表 `platform_schedule_targets`，记录每个定时任务最近写入引擎时的修订和任务队列。API 同步和 dispatcher 每轮对账时，如果记录缺失，或与已同步修订、当前 Core 不一致，就按原修订重新写入；用户可见的修订号和同步状态不变。已经启动的触发及其 Run 仍在原任务队列和冻结 Core 上执行到结束。回归用例在 `backend/tests/test_target_schedules.py`，覆盖以下情况：旧 Core 上已启动的触发，切换后仍由原 Worker 完成；切换后的手动触发改由新 Core 执行；重新写入失败时状态保持“已同步”，下一轮重试；没有目标记录的旧定时任务也会迁移一次。关闭重新写入后，该用例失败。定时任务、schema 兼容、平台 API 等 82 项测试，以及 ruff/black/isort/mypy，全部通过。新表在启动时由 `create_all` 创建，不修改已有表，符合发布前的 schema 兼容检查。

实现已通过提交 `0eda6935` 合入 `main` 并推送，随 v0.2.4 发布并部署到 capy，见[部署与使用](#部署与使用)。

## 部署与使用

当前部署边界是本地内网，使用对象是个人和单一操作者。项目优先保持本地启动、调试、观察和日常使用便利；这项偏好不取消现有的正确性、数据完整性、密钥保护和必要验证边界。

应用、Core API 和经网关公开的插件业务 API 无需访问口令，浏览器直接进入应用，不保存或请求平台访问口令。资源和模型凭据继续加密保存并安全投影；工具授权、插件业务 scope 和内部接口隔离保持不变。

经本轮用户明确授权，根 Dockerfile 改为正式应用镜像 `ghcr.io/coachpo/signaldeck`，前端静态资源、Nginx 和 Core API 合并发布；dispatcher、worker 共用该镜像并独立运行。正式部署入口为 `docker/compose.production.yml`，PostgreSQL、Temporal 和业务插件继续独立运行，保留数据库隔离、插件独立升级及历史制品约束。根 Compose 和 `start.sh` 仍是源码本地/演示入口，使用 local 模式与开发 Temporal。这项镜像边界调整不改变单用户、可信内网范围，也不授权发布或切换现有实例。

2026-09-19 起按版本发布：`release.sh` 统一版本号并打 `vX.Y.Z` 标签，发布提交的 CI 全部通过后才发布 `linux/arm64` 镜像；实例经运维 skill 备份后部署并固定到镜像 digest，命令见[贡献指南](CONTRIBUTING.md#发布)。

capy 实例（部署仓库 `coachpo/curse` 的 `signaldeck` Compose 项目，局域网 `192.168.1.222:8089`）于 2026-09-19 10:28 UTC 按该流程部署并核验：应用镜像为 `ghcr.io/coachpo/signaldeck:v0.2.0@sha256:ff80ebb3f036492d145ba3b22eda4315ef406864700bf66d1ac492bcd4ca35ce`（发布提交 `b10785f8`），由 `signaldeck/backend.env` 的 `SIGNALDECK_VERSION` 固定，此前该文件固定的 cc49642a 与实际运行的 84c3ec46 不一致的问题已消除。切换前完成静默备份（`backups/signaldeck/20260919T102154Z-managed`，一次性容器恢复演练通过）和 schema 兼容检查（20 张 Core 表全部兼容）；切换后 `/health` 报告 0.2.0，应用各角色运行该 digest，其余服务镜像不变，持久表行数未减少，7 个只读 API 和 6 个插件页面挂载返回 200，300 秒观察期内无重启。同日 12:00 UTC 按插件升级流程把 Finance 1.3.0 与 Oracle 升级到 v0.2.0 发布：新服务 `finance-b10785f8`、`digital-oracle-b10785f8` 运行 `sha-b10785f8…` 镜像并在 `backend.env` 固定 digest，插件目录当前发布分别指向新端点（Finance 制品摘要 `1a533a79…`，Oracle `1886ae2b…`）；被取代的 `finance-cc49642a`、`digital-oracle` 及更早的历史服务保留在 `legacy-plugins`，7 个页面挂载全部返回 200；Notes 1.3.0（84c3ec46）不变。升级前静默备份为 `backups/signaldeck/20260919T115316Z-managed`，恢复演练通过。同日约 12:45 UTC 发布 v0.2.1（发布提交 `c48995c0`），并按同一流程把 Finance 升级到 1.4.0：新服务 `finance-c48995c0` 运行 `sha-c48995c0…` 镜像并在 `backend.env` 固定 digest，插件目录当前发布指向该端点（制品摘要 `f40dcfff…`），1.3.0 的 `finance-b10785f8` 移入 `legacy-plugins`，8 个页面挂载全部返回 200；升级前静默备份为 `backups/signaldeck/20260919T124108Z-managed`，恢复演练通过。同日 13:20 UTC 应用镜像按门禁流程从 v0.2.0 上线到 v0.2.1（`ghcr.io/coachpo/signaldeck:v0.2.1@sha256:abe57d25…`，其应用代码与 v0.2.0 相比只有版本号不同）：切换前静默备份 `backups/signaldeck/20260919T131302Z-managed`，schema 兼容、部署后检查和 300 秒观察通过。同日约 13:55 UTC 发布 v0.2.2（发布提交 `bb73a798`，包含 Finance 1.5.0 自选股扫描和 Core 条件字面量修复，发布提交的 CI 与镜像工作流全部通过）；14:03 UTC 应用按同一门禁流程上线到 `ghcr.io/coachpo/signaldeck:v0.2.2@sha256:87ba51cdd98304f5560fe144ace4c481d49fbebc3a9ba38af737c1fd79d0b270`：切换前静默备份 `backups/signaldeck/20260919T135639Z-managed`，20 张 Core 表 schema 兼容；部署后 7 个只读 API 和 8 个插件页面挂载返回 200，持久表行数未减少；`backend.env` 固定到该 digest，302 秒观察期内无重启。随后约 14:07 UTC 按插件升级流程把 Finance 升级到 1.5.0：新服务 `finance-bb73a798` 运行 `sha-bb73a798…` 镜像，并在 `backend.env` 固定 digest（`sha256:13dd1a0b…`）；插件目录当前发布指向该端点（制品摘要 `7397fd44…`）；1.4.0 的 `finance-c48995c0` 移入 `legacy-plugins`；9 个页面挂载全部返回 200。升级前静默备份为 `backups/signaldeck/20260919T140508Z-managed`，两份新备份的恢复演练均通过；部署仓库记录为 `2e029eb`。17:15 UTC 复查运维检查无异常，应用和新 Finance 服务自启动后无重启。经用户授权，约 17:30 UTC 导入示例工作流包 `watchlist_price_events`，并创建定时任务 `watchlist-price-events-weekday-1645`（`45 16 * * 1-5`，America/New_York，首次触发 2026-09-21）；自选股沿用 `finance-market-data` 现有的 MSFT、AAPL。当时手动触发的运行 `0ce3c129` 因确定性工具调用的心跳超时而失败，见上方迭代记录。随后发布 v0.2.3（发布提交 `63d4db33`，发布提交的 CI 与镜像工作流全部通过），并在 18:29–18:38 UTC 按门禁流程把应用上线到 `ghcr.io/coachpo/signaldeck:v0.2.3@sha256:42821a8e864aa72b0246179b53556bb4d86469637e1b18adb42e1620a4461e03`：切换前静默备份 `backups/signaldeck/20260919T183044Z-managed`；schema 兼容；插件比对三个当前插件均未变化；部署后 7 个只读 API 和 9 个插件页面挂载返回 200；`backend.env` 固定到该 digest；302 秒观察期内无重启。定时任务在同步时会固定当时 Core 制品的任务队列，所以 Core 升级后，已有定时任务仍由旧 Core 执行。按原定义重新保存一次（修订 2）后，它改用 v0.2.3，之后手动触发的运行 `7719e70b` 成功：扫描了 MSFT、AAPL；当天是周六，没有完成的交易日，保存报告按条件跳过。18:40 UTC 复查运维检查无异常。约 19:24 UTC 发布 v0.2.4（发布提交 `3c862377`，包含定时任务跟随 Core 升级的修复 `0eda6935`；发布提交的 CI 与镜像工作流全部通过），并在 19:40–19:49 UTC 按门禁流程把应用上线到 `ghcr.io/coachpo/signaldeck:v0.2.4@sha256:9411dfd17d334ca009e549f15f4afc41cf8b6b058b79411e0e2d4d18a414f3e4`：切换前静默备份 `backups/signaldeck/20260919T194136Z-managed`，恢复演练通过；schema 兼容，新表 `platform_schedule_targets` 在启动时创建；插件比对三个当前插件均未变化；部署后 7 个只读 API 和 9 个插件页面挂载返回 200；`backend.env` 固定到该 digest；302 秒观察期内无重启。上线后 dispatcher 第一轮对账就把定时任务 `watchlist-price-events-weekday-1645` 从 v0.2.3 Core 的任务队列 `sd-core-902de78b…` 改到 v0.2.4 Core 的 `sd-core-e8e718f6…`；修订号仍为 2，下次触发时间不变，不需要再手动重新保存。部署仓库的 `signaldeck/README.md` 同步记录为 v0.2.4（`80a61af`）。19:50 UTC 复查运维检查无异常。观测时 Core 中有 3 个 Run（2 个失败、1 个成功）、1 个工作流包、1 个定时任务、2 条资源。以上是观测时事实，不代表持续健康。

仓库配置不能证明实际实例的部署、外部用户或数据状态；当前未核实“没有外部用户”或“没有不可丢弃数据”。MVP 档位不替代这些事实，也不授予数据重置权限。

## 数据与兼容性

Core 配置和运行证据由 PostgreSQL 持久化，Temporal 保留执行历史，内容寻址目录保存产物与固定 Core 制品。Finance 和 Notes 使用各自数据库及角色。Core 与插件的表通过 SQLAlchemy `create_all` 初始化，独立 Temporal 数据库通过其固定版本官方 schema 工具初始化；可选工作流目录另经通用 missing-only 导入；执行恢复由 Temporal 驱动。Core 没有 Alembic 或旧数据自动迁移路径，`create_all` 不会升级已有表。当前没有 Core 运行历史自动清理入口；Temporal 已完成执行历史的保留时间见部署说明，数据结构和不可变边界见 [`数据模型`](docs/data-model.md)。

当前没有单独声明的长期外部 API、配置或数据库 schema 兼容承诺；修改仍须遵守产品范围、架构边界和适用质量检查，不能因为本地便利而泄露 secret、破坏运行快照或绕过数据完整性校验。

当前 v2 实现已替换旧 API、YAML、数据结构和静态插件路径，没有保留旧实现兼容层。后续变更仍需遵守当前产品合同和数据完整性约束；实际数据处置按以下用户授权执行，并明确具体影响。

2026-09-08，用户授权现有实例在实际切换新实现时的数据处置。届时根据具体实例和数据情况确定保留、迁移或重建方式；当前继续隔离开发与测试，不因此立即变更现有实例数据。这项授权仅覆盖本项目切换所需的实例和数据，不表示现有数据已被核实为可丢弃，也不扩展到无关实例或数据。

## 允许与禁止的变更

允许在当前本地内网边界内改进开发启动、调试观察、工作流编辑和个人使用路径，并复用已有组件和依赖。涉及本地数据库重建、数据删除或兼容行为变化时，仍需在变更范围内明确影响并通过适用验证。

允许维护和扩展现有声明式 DAG、独立 Agent、Temporal 持久执行、进程外插件、资源配置和运行检查闭环。功能范围及回归合同以产品说明为准；三候选比较及原探针限制保留在 [`执行引擎比较`](docs/执行引擎比较.md)。

本地实施、所需依赖及隔离测试资源创建/清理已有相应任务授权。实际实例切换按上述限定的数据处置授权执行；其他提交、推送、发布、部署和外部写入仍按当前任务的明确授权判断，不将一次验收视为通用外部操作授权。

不得将根 Compose 的开发 Temporal 拓扑当作正式部署入口，或把独立 PostgreSQL、Temporal、业务插件并入应用镜像；不得把单用户产品扩展为认证/RBAC、多租户、插件市场或其他未重划范围的产品面；不得移除 secret 加密与脱敏、工作流包解析安全、确定性编译、运行不可变快照或仓库必需检查。

如果部署转为公网或生产环境，或确认存在外部用户、真实/不可丢弃数据、明确的兼容承诺和安全验收，必须重新评估本状态、开发档位及相关架构边界。
