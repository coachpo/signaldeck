# 简化操作 Sprint 交付对照

本记录对照 [`sprint-backlog.md`](sprint-backlog.md) 的 S1–S6、23 个稳定任务 ID，以及 P01–P07、UX01–UX08；现有执行合同始终以 [`产品说明 A01–A18`](../产品说明.md#验收标准) 为准。本轮未重新开发或重新宣告 SD-TARGET-001 完成。

## 版本与验收口径

本文保存原实现任务交付阶段的 23 项映射、检查结果及本机证据。实现起点为 `f7ced2f35cae20ab37e94acc9a89007a49143d10`；当前独立验收基线为 `05a61151fb6239c0d222630c3e7c722e8c88c5a8` 加工作区实现及验收修复。`05a61151` 的 8 文件依赖/配置修改已在当前 HEAD 中，原实现任务曾按用户要求整合其等价修改。原实现交付阶段未提交、推送或部署。

原实现任务在 2026-09-08 记录全部 6 个 Sprint、23 项待办及调整后 C1–C8 交付，并记录 19 项 E2E、独立双离线故障验证、静态检查、测试与构建通过。**这些是原交付阶段的记录，不能代替修复版本的独立验证。** 独立验收现已通过 23/23 必需用例及综合完成检查；修复、最终测试数和版本由 [`Sprint 独立验收索引`](sprint-verification.md) 汇总，本机报告为 `.steward/goals/sd-ux-all-sprints/verification/report.md`。

原交付阶段的代码/配置/测试源清单 SHA-256 为 `c0cee6010108c2ad3a53a1dfa7e6edd45cd6a820247d97b6e99dcaf8106b822f`，逐文件摘要见本机 [`source-version.json`](../../output/playwright/verification/source-version.json)，当时 Core 闭包见本机 [`core-manifest.json`](../../output/playwright/verification/core-manifest.json)。这两个标识不代表后续修复版本。源清单排除交付文档和本地生成物；`backend/README.md` 包含在当时 Core 闭包中。

本文 `output/playwright/` 下的日志、截图、下载产物和版本清单均为本机证据，该目录被 Git 忽略，新检出不包含这些文件。下文“最终”“完成”“通过”及统计数字均限定为原实现任务当时记录的结论；本轮独立验收的可复核精简记录使用上面的独立验收索引，不将缺少本机附件的新检出视为已具备全部历史证据。

2026-09-08 用户已将 C8 调整为执行者安排 Playwright 自动化体验验证，无需人员参与；见 Backlog 的[验收方式调整](sprint-backlog.md#验收方式调整2026-09-08)。原实现任务的 UX01–UX08 操作、问题修正和复验记录见下文；这些不是实际用户观察，受控模型/provider 也不证明真实外部供应商可用。

## 23 项交付矩阵

表中保留原实现任务逐项交付与验证结论，不作为本轮独立验收通过声明。该阶段的门禁、运行身份及修复复验见后文；局部测试数不与全量测试数相加。

| Sprint / 稳定 ID | 已接入实现与证据入口 | 对应要求 | 验证结论 |
| --- | --- | --- | --- |
| S1 `sd-ux-contracts` | [任务目录](../../frontend/src/pages/platform/task-catalog.ts)、[准备/结果契约](../../backend/app/schemas/task_experience.py)、[准备投影](../../backend/app/application/task_preparation.py)；业务名称映射现有包，闭合 schema 与有效设置保留 | P01/P02/P03；UX01/02/03/07；C1/C2/C3 | 完成：后端任务准备/结果合同及 539 全套通过；四场景实际执行和业务设置核对通过。 |
| S1 `sd-ux-shell` | [路由](../../frontend/src/routes.ts)、[壳层](../../frontend/src/components/layout.tsx)、[显示偏好](../../frontend/src/hooks/use-display-mode.ts)、[DESIGN](../../frontend/DESIGN.md)；任务/结果/设置默认导航，专家开关只改变展示 | P01/P05；UX07；C1/C6 | 完成：普通首页/设置/专家导航通过；4 宽度 shell 和关键操作 bounds 通过并持久保存截图。 |
| S1 `sd-ux-task-form` | [任务页面](../../frontend/src/pages/platform/tasks.tsx)、[业务输入（历史实现）](https://github.com/coachpo/signaldeck/blob/6ca0e8e83c70c564cb1042ddc2027153bab35560/frontend/src/pages/platform/task-inputs.tsx)；四场景表单、schema 不匹配提示专家输入 | P02；UX01/07；C1 | 完成：四场景实际业务表单运行；schema/默认值/无损输入回归及模式往返通过。 |
| S1 `sd-ux-capture` | [Notes 示例](../../demo/research_notes.yaml)、任务目录的 capture；确定性保存，无模型前置，结果投影保存回执 | P02/P03；UX01/03/05；A09/A12/A14；C2/C3 | 完成：实际 Notes capture 成功且无模型；接受后断网重试仍仅 1 个 Run，原文回执可读。 |
| S2 `sd-ux-readiness` | [prepare_task](../../backend/app/application/task_preparation.py)、[启动核对](../../backend/app/application/launch.py)、[有效设置](../../frontend/src/pages/platform/task-preparation.tsx)；安全配置检查、当前绑定摘要和历史比较 | P02/P03；UX02/05；A13/A14；C2/C4 | 完成：缺配置与历史观测分开；绑定变化拒绝、原设置比较及相同 launchId 重试通过。 |
| S2 `sd-ux-connections` | [就地连接](../../frontend/src/pages/platform/task-connections.tsx)、[设置](../../frontend/src/pages/platform/settings.tsx)；保留业务输入、凭据单独写入、已有连接只读安全投影 | P02/P05；UX02/07；A02/A14；C2/C6 | 完成：真实研究首次缺连接就地修复、输入保留；凭据独立写入及留空保留通过。 |
| S2 `sd-ux-result-contract` | [结果投影](../../backend/app/application/result_projection.py)、[结果 API](../../backend/app/api/platform_runs.py)；正文/回执、来源、数据时间、缺失、附件及 unknown | P03/P06；UX03/05；A08/A09/A15；C3 | 完成：真实正文/回执/报告关联及大产物边界通过；真实取消 unknown 与双离线读取通过。 |
| S2 `sd-ux-finance-link` | [Finance 页面](../../plugins/finance/web/index.html) 的 `?report=<slug>` 和独立报告下载；Core [结果页面](../../frontend/src/pages/platform/result-view.tsx) 通过插件 pageUrl 连接 | P03/P06；UX03；C3 | 完成：两份实际研究报告从 Core 直达 Finance 并下载；slug/reportId/404/刷新回归通过。 |
| S2 `sd-ux-result-view` | [结果阅读](../../frontend/src/pages/platform/result-view.tsx)、[状态标签](../../frontend/src/pages/platform/result-labels.ts)；结果正文优先，完整证据入口保留 | P02/P03/P05；UX01/03/05；A08/A09/A15；C3/C6 | 完成：结果优先与技术证据可达；真实 unknown 核实门槛、取消状态及双离线历史通过。 |
| S3 `sd-ux-history-query` | [数据库历史查询](../../backend/app/infrastructure/run_history.py)、[历史页面](../../frontend/src/pages/platform/result-history.tsx)；全历史过滤、搜索、稳定排序、总数分页和创建时间上界 | P01/P03；UX03；C4 | 完成：实际 27+1 条 Notes 历史、多页/返回/刷新、跨 UTC 本地日期筛选通过。 |
| S3 `sd-ux-repeat-input` | [rerun/reuse API](../../backend/app/api/platform_runs.py)、任务和结果页；保留原修订/输入，变更核对后创建带来源的新 Run | P03；UX05/06；A10/A11/A12/A14；C4 | 完成：实际从原结果改输入新启动；原快照不变；冻结修订、重跑来源/绑定/身份回归通过。 |
| S3 `sd-ux-presets` | [TaskPresetStore](../../backend/app/infrastructure/task_preset_store.py)、[API](../../backend/app/api/task_presets.py)、任务页；独立新表、版本校验、收藏/置顶、删除不级联 | P06；UX01/06/07；A10/A14；C4 | 完成：真实数据库 CRUD、重开/版本变化、闭合 schema/凭据拒绝/无级联通过；普通页面保存及任务目录找回通过。 |
| S3 `sd-ux-finance-use` | Finance 普通页已有格式→业务字段→预览→生成；全库搜索、业务筛选、排序分页、下载，预览变更核对 | P06；UX01/03；C4 | 完成：独立 Finance 4 项实际插件/数据库/浏览器测试通过，已有格式/预览/生成/历史/下载及原保护合同通过。 |
| S4 `sd-ux-schedule-time` | [cron 编解码](../../frontend/src/lib/schedule-frequency.ts)、[Temporal schedules](../../backend/app/infrastructure/temporal_schedules.py)；每日/每周单日/每月单日固定时刻，Temporal 可信预览 | P04；UX04/07；A17；C5 | 完成：Temporal 可信 weekly 预览及 DST 回归通过；draft/applied、暂停和同步修订有实际来源。 |
| S4 `sd-ux-schedule-form` | [计划编辑](../../frontend/src/pages/platform/schedules.tsx)、[时间控件](../../frontend/src/pages/platform/schedule-timing.tsx)；继承输入、明确时区、复杂规则保留 | P04；UX04/07；C5/C6 | 完成：输入继承、时区和复杂规则往返通过；断连后相同 requestId/输入重试、不重复建安排通过。 |
| S4 `sd-ux-schedule-manage` | [自动执行列表](../../frontend/src/pages/platform/schedule-list.tsx)、[fire 历史](../../frontend/src/pages/platform/schedule-fire-history.tsx)；同步状态、暂停/恢复/立即执行和来源 | P04/P03；UX04/05；A09/A12/A17；C5 | 完成：真实修改/同步/立即触发/暂停与失败历史通过；删除后 fire/Run 来源保留，具体身份见后文。 |
| S5 `sd-ux-expert-editor` | [对象属性](../../frontend/src/pages/platform/package-properties.tsx)、[结构编辑](../../frontend/src/pages/platform/package-structure.tsx)、[DAG 视口](../../frontend/src/pages/platform/dependency-graph.tsx)；同一 YAML AST、复杂值显式应用、导入导出 | P05；UX08；A04/A13/A15；C6 | 完成：真实属性/映射草稿/编译/导入导出及图视口通过；4 宽度持久截图可检查。 |
| S5 `sd-ux-expert-resources` | 原 [资源](../../frontend/src/pages/platform/resources.tsx)、[插件](../../frontend/src/pages/platform/plugins.tsx) 及运行技术证据入口保留，专家导航可达 | P05；UX07/08；A07/A09/A14/A15；C6 | 完成：资源/发布草稿无损往返与技术 ID 复制通过；插件及真实 Temporal 停止后调用证据仍可读。 |
| S5 `sd-ux-finance-author` | Finance 专家模板制作、输入占位符辅助、诊断/预览及草稿；普通格式使用和制作分离，Agent 报告不可变边界保留 | P05/P06；UX07/08；C6 | 完成：实际模板制作、必填/可选字段、编译/预览/生成、草稿往返及 4 宽度通过。 |
| S5 `sd-ux-mode-roundtrip` | 显示模式、当前任务内存草稿、专家 forceMount 编辑器、复杂计划和 Finance 页内草稿共同保留原值 | P01/P04/P05/P06；UX07/08；C6 | 完成：任务、未应用映射、预算、资源/插件、复杂计划和 Finance 草稿往返通过，模式切换不发写命令。 |
| S6 `sd-ux-integration` | [tasks E2E](../../frontend/e2e/tasks.spec.ts)、[E2E fixtures](../../frontend/e2e/task-fixtures.ts)、原 durable runtime/独立插件/取消/unknown 合同回归 | P07；UX01–08；受影响 A 合同；C2–C7 | 完成：最终 539 后端/208 前端/19 E2E/4 Finance，另真实双离线故障 1 项；全部适用门禁与四宽度视觉通过。 |
| S6 `sd-ux-usability` | 按用户调整后的 C8 使用 Playwright 逐项任务操作、问题修正和复验；不要求实际参与者 | P07；UX01–08；C8 | 完成：按调整后的 C8，UX01–UX08 均有 Playwright 实际操作与修复复验对照；无真人或真实供应商验收主张。 |
| S6 `sd-ux-docs-closeout` | [产品](../产品说明.md)、[架构](../架构说明.md)、[数据模型](../data-model.md)、[根入口](../../README.md)、[前端指引](../../frontend/AGENTS.md)、[索引](../README.md) 及本记录 | P07；C7 | 完成：规范、导航、数据模型和交付对照与实际一致；23 ID 精确覆盖、A01–A18 原文保留、链接及差异检查通过。 |

## 原实现任务的本机验证记录

最终主验证使用更新后的锁文件，后端 Python 3.13.13、真实隔离 PostgreSQL，前端 pnpm 10.30.1；E2E 启动实际 Core API、Temporal、dispatcher、固定制品 worker 和独立插件，模型与业务 provider 使用受控端点。以下为原实现任务记录并关联本机日志的结果；其四场景、计划和故障运行均使用 `sha256:f48df790b6c97530f001dca9aded9a3644c6a9d751a963bbd9f98e7233e4dd15`。

实际最终检查解释器为 `/tmp/signaldeck-ux-check-env/bin/python`（Python 3.13.13）；它由 `UV_PROJECT_ENVIRONMENT` 指向本轮独立环境，未改用项目中其他 Python 版本。临时环境清理后，可在仓库根按锁文件重新准备：

```bash
UV_PROJECT_ENVIRONMENT=/tmp/signaldeck-ux-check-env uv sync --project backend --frozen --python 3.13.13
(cd backend && UV_PROJECT_ENVIRONMENT=/tmp/signaldeck-ux-check-env uv run --frozen pytest)
PYTHONPATH=plugins/finance:plugins/runtime /tmp/signaldeck-ux-check-env/bin/python -m pytest plugins/finance/tests/test_finance_ux.py -q -s
```

数据库与 Temporal 前提沿用 [贡献指南](../../CONTRIBUTING.md#测试数据库与-e2e-环境)，使用本轮独立 PostgreSQL/临时数据库；环境清理不会使持久日志和版本清单消失。

| 命令（在对应项目目录运行） | 实际结果 | 覆盖与证据 |
| --- | --- | --- |
| 后端 `ruff check app tests`、`black --check app tests`、`isort --check-only app tests`、`mypy app` | 全部通过，mypy 检查 90 文件 | 更新锁及 Python 3.13.13 独立检查环境；[ruff](../../output/playwright/verification/backend-ruff.log)、[black](../../output/playwright/verification/backend-black.log)、[isort](../../output/playwright/verification/backend-isort.log)、[mypy](../../output/playwright/verification/backend-mypy.log) 日志 |
| 后端 `/tmp/signaldeck-ux-check-env/bin/python -m pytest` | **539 passed，2 warnings，189.31s** | [后端测试日志](../../output/playwright/verification/backend-pytest.log)；涵盖编译、快照、凭据、命令重投递、Temporal恢复/取消/unknown、独立插件、历史/准备/结果/预设与计划；警告为 sandbox 延后导入 `annotated_types` |
| 前端 `pnpm lint`、`pnpm typecheck` | 全部通过 | [前端 lint 日志](../../output/playwright/verification/frontend-eslint.log)、[前端类型日志](../../output/playwright/verification/frontend-typecheck.log) |
| 前端 `pnpm test:run` | **49 文件、208 tests passed**，12.84s | [前端单测日志](../../output/playwright/verification/frontend-vitest.log)；业务表单、结果/历史、专家编辑、模式/草稿、时间与身份回归 |
| 前端 `pnpm build` | 通过 | [构建日志](../../output/playwright/verification/frontend-build.log)；TypeScript 与 Vite 生产构建 |
| 前端 `pnpm test:e2e` | **19 passed，1.2m**，0 failed/flaky/skipped | [`core-e2e-summary.json`](../../output/playwright/task-experience/core-e2e-summary.json) 为本次实际报告摘要；原日志 [完整 E2E 日志](../../output/playwright/verification/playwright.log) |
| 根目录 `PYTHONPATH=plugins/finance:plugins/runtime /tmp/signaldeck-ux-check-env/bin/python -m pytest plugins/finance/tests/test_finance_ux.py -q -s` | **4 passed，3.32s** | [Finance 测试日志](../../output/playwright/verification/finance-pytest.log)；实际 PostgreSQL/HTTP/Chromium，格式使用/制作、草稿、预览/生成、深链接刷新/下载、历史/404和四档视觉 |
| 最终完整 E2E 中的 3 个 `scheduled-tasks.spec.ts` 用例 | **3 passed（已计入 19）** | [`schedule-experience`](../../output/playwright/schedule-experience/) 三份 JSON；通过实际栈固化计划、Temporal 时间和成功/失败 fire 来源 |
| 故障专项 Playwright（停止独立插件及真实 Temporal） | **1 passed，25.3s** | [`playwright-faults.log`](../../output/playwright/faults/playwright-faults.log) 和双离线证据；不伪造引擎停机 |
| Finance 变更文件按 backend pyproject 运行 ruff/black/isort | 全部通过 | [ruff](../../output/playwright/verification/finance-ruff.log)、[black](../../output/playwright/verification/finance-black.log)、[isort](../../output/playwright/verification/finance-isort.log) |
| 文档本地链接、Backlog ID 集合、A01–A18 原文对照、`git diff --check` | 通过 | 23 个稳定 ID 精确覆盖，A01–A18 逐行未变；最终新增证据链接已复核 |

早期全后端出现的 Finance 名称规范回归已修复，最终 539 项全过；没有删改断言来消除失败。曾有本地 PostgreSQL bind mount 临时库文件权限错误，改用独立测试环境后重新完成最终门禁；未处置现有实例数据。旧局部通过数不与最终统计相加。

源码规模自检已完成：保留的壳层、sidebar、启动/计划编排、平台存储和 Finance 报告服务仍各自负责单一边界；任务表单/连接、结果查询/正文、时间编解码/预览、专家属性/图和命名配置已拆入对应模块。未发现需要以本轮未完成事项记录的规模问题。详情路径由 [架构说明](../架构说明.md) 和源清单维护。

## UX 自动化体验追溯

下表是自动化体验验收，不是参与者观察。实际插件、受控 provider 和真实页面承担业务链路；失败/未知/离线状态另由故障专项覆盖。

| ID | 实际操作与通过证据 | 修正/复验结论 |
| --- | --- | --- |
| UX01 | [tasks.spec.ts](../../frontend/e2e/tasks.spec.ts)：从目录进入四场景、业务字段输入、实际执行至结果；两研究报告直达 Finance 下载 | 风险默认值因 schema 中 null 投影占位未正确启用已修复；最终市场表单 checked、保存原文无模型、四 Run succeeded |
| UX02 | 同一 tasks 实际流程先缺研究连接，选择明确部署预设、填写凭据/确认范围，保存后原文仍相同，再执行成功 | 未用静态 mock 代替服务配置；密钥不存常用配置或浏览器持久存储；最终重跑通过 |
| UX03 | [history.spec.ts](../../frontend/e2e/history.spec.ts)：27+1 条真实记录、多页/返回/刷新与跨 UTC 本地日；实际报告下载、unknown/缺失/时间显示 | 本地日边界和刷新分页重置已修复；Core、插件关闭及真实 Temporal 停止后的历史与证据读取通过 |
| UX04 | [scheduled-tasks.spec.ts](../../frontend/e2e/scheduled-tasks.spec.ts)：每周一 09:30 Helsinki、Temporal draft/applied 时间、暂停状态；复杂规则编辑和修订同步 | 明确期望/已生效时间；已保存时区与 buffer_one/catchup 不因模式切换改变；17 项 backend schedule 回归覆盖暂停恢复等真实生命周期 |
| UX05 | [runs.spec.ts](../../frontend/e2e/runs.spec.ts)、计划 E2E 及 [故障记录](../../output/playwright/faults/engine-offline-evidence.json)：分别取消运行、暂停安排、重跑与立即执行 | 接受取消不当作停止，cancelled Run 仍保留 unknown 写效果，未勾选实际核实不能直接重跑；真实外部效果不被描述为撤销 |
| UX06 | tasks 从已保存原文结果修改输入并新启动，旧 spec 逐字不变；命名输入可选保存，预设数据库验证重开/更新/删除与定义变化 | 冻结原修订与 sourceRunId；旧版本保存冲突且不丢字段；相同启动身份不创建第二次执行 |
| UX07 | [expert.spec.ts](../../frontend/e2e/expert.spec.ts)、任务/计划与独立 Finance 浏览器：输入、预算、映射、资源/发布 JSON、复杂 cron、时区和未保存模板往返 | 未应用 JSON 阻止覆盖，组件保持挂载，模式切换不产生写命令或泄漏草稿至持久浏览器存储 |
| UX08 | 专家属性/真实校验/导入导出/DAG 缩放拖动定位；原快照/调用证据深链接；Finance 制作后普通使用 | 375px 动作截断修复后 bounds 和截图复验通过；真实 unknown 操作证据与双离线读取仍可诊断，原 A 合同回归通过 |

## 运行与产物来源

以下为 2026-09-08 最终主 E2E 的实际四场景运行，完整快照与调用记录保存在 [`four-scenario-run-artifact-evidence.json`](../../output/playwright/task-experience/four-scenario-run-artifact-evidence.json)。它们均为 `origin.kind=manual`、`status=succeeded`，使用 Core `sha256:f48df790b6c97530f001dca9aded9a3644c6a9d751a963bbd9f98e7233e4dd15`。

| 场景 / 定义修订 | 实际 Run / 完成时间 UTC | 本次产物与来源 |
| --- | --- | --- |
| 保存原文：`research_notes/capture`，packageHash `436934e8731ed15b83e679e2878bfe6747ec4102b038565a17778a60a3cd38a2` | `7c560753-e662-41c6-8591-e1887a48efc7`；2026-09-08T11:27:48.565121Z | Notes `7c560753-e662-41c6-8591-e1887a48efc7:save:agent:1:tool:deterministic`；collection=`research`；无模型调用 |
| 整理笔记：`research_notes/research`，packageHash `436934e8731ed15b83e679e2878bfe6747ec4102b038565a17778a60a3cd38a2` | `7055c618-9bbb-4071-83f4-1c54dfde2f65`；2026-09-08T11:27:55.774909Z | Notes `7055c618-9bbb-4071-83f4-1c54dfde2f65:save:agent:1:tool:deterministic`；collection=`research`；经过受控模型整理 |
| 市场研究：`tradingagents_advisory_research/research`，packageHash `d102a2a32c2870059e929c8367d1fd998c425568a7f8538e95b477b28927c09e` | `1f995804-cb4c-41f3-86d9-1689eb2bddce`；2026-09-08T11:28:05.301207Z | Finance `reportId=1`；报告下载 [tradingagents_advisory_research-report.md](../../output/playwright/task-experience/tradingagents_advisory_research-report.md) |
| 综合资料研究：`digital_oracle_researcher/research`，packageHash `aaa5cb87db7e68dbeab6184beef094d64490f10411fd9c59d9f65318512d506e` | `89c26e91-078a-4d34-82f5-66864ad910f9`；2026-09-08T11:28:17.416436Z | Finance `reportId=2`；报告下载 [digital_oracle_researcher-report.md](../../output/playwright/task-experience/digital_oracle_researcher-report.md) |

本次冻结插件发布均为 `1.0.0`：Notes 制品 `sha256:fbb65ec78082861edf6a61f8f01a05a75e21355abbee1046a74ca24be4c9b578`；Finance 制品 `sha256:414caa389847e4e96de7af985f80d137842de7da5ce636b4ae27d068efc55838`；Digital Oracle 制品 `sha256:236eee3d251ea236ff0bcd7ae1eb87ba9e655210b9e44f9c6668695d39560876`。保存原文运行的模型绑定数为 0，研究场景为受控模型；本次结果 `dataTime` 均为 null，界面不拿执行时间冒充数据时间。

历史专项使用真实 Notes 执行生成 27 条，再新增第 28 条。首条 Run `85328300-786e-4e80-be15-690adca00fca`，新增 Run `4807b709-f4ff-4174-a84e-1c8cfd63d4fb`。第二页 offset 为 25、`snapshotAt=2026-09-08T11:27:32.982961Z`；刷新清除旧分页上界并显示新条目。`Pacific/Kiritimati` 本地 2026-09-09 对应 `2026-09-08T10:00:00.000Z` 至 `2026-09-09T09:59:59.999Z`，与 UTC 日期不同，实际日期筛选及刷新回显通过。全部身份及 URL 保存在 [`history-execution-evidence.json`](../../output/playwright/task-experience/history-execution-evidence.json)。

### 重复安排与 Temporal 来源

以下计划与四场景来自最终同轮隔离栈，成功计划 Run 冻结相同 Core `sha256:f48df790b6c97530f001dca9aded9a3644c6a9d751a963bbd9f98e7233e4dd15`；来源记录如下。

| 观察 | 真实身份与结果 | 留存证据 |
| --- | --- | --- |
| 修改时区、立即执行、删除后历史保留 | schedule `05aab3bb-f0a6-4972-81d4-cf294a98e7a6`；revision/syncedRevision=2/2；`Europe/Helsinki`，`buffer_one`，catchup=60；请求 trigger `efecc377-68b2-4b07-8176-adf9c35e0bc4`；实际 fire trigger `sha256:16b9a7afb7cb504195e7424a7d34af23cbc48182c3385f37941d2b0f319b71ff`；Run `67b95422-a4c1-4b27-8be6-a7d26fb79b97` succeeded；scheduledAt `2026-09-08T11:27:38.091321Z`；删除后 fire/Run 来源不变 | [成功及来源](../../output/playwright/schedule-experience/schedule-success-and-retained-provenance.json) |
| 定义改名导致启动失败 | schedule `336ccd6c-f2c6-4468-b59d-5618ec28727d`；请求 trigger `2f2e42ef-fd51-41ba-98ed-fcc72e1df4df`；Temporal run `01a080c6-1700-735f-8da9-344cc1711b6c`；fire=`launch_failed`、`workflow_not_found`、Core runId=null，界面显示尚未生成结果 | [失败来源](../../output/playwright/schedule-experience/schedule-failed-launch-provenance.json) |
| 每周与复杂规则往返 | schedule `207025ee-349a-4d30-9c56-0d3d9920cbfa`；每周一 09:30 Helsinki=`30 9 * * 1`；修改为 `0 8,17 * * 1-5` 后 revision/syncedRevision=2/2，原输入、timezone、buffer_one、catchup=180、paused=true 不变 | [时间及高级配置](../../output/playwright/schedule-experience/schedule-weekly-and-custom-preview.json) |

每周安排的 Temporal draft 与 applied 预览一致，返回 UTC：`2026-09-14T06:30:00Z`、`2026-09-21T06:30:00Z`、`2026-09-28T06:30:00Z`、`2026-10-05T06:30:00Z`、`2026-10-12T06:30:00Z`。它们是 Helsinki 每周一 09:30；暂停状态仍为 true，预览不等于启用。复杂规则已生效预览前两项为 `2026-09-08T14:00:00Z`、`2026-09-09T05:00:00Z`，对应本地 17:00 和 08:00。普通频率及 DST 春季跳过/秋季重复边界还由最终后端 schedule 回归核对，时间权威仍为 Temporal。

### 取消、未知写效果与服务离线

故障专项使用实际独立 MCP 测试进程和真实 Temporal。Run `83efb2f9-5984-41bc-a5e8-cd31749fd513`（Core `sha256:f48df790b6c97530f001dca9aded9a3644c6a9d751a963bbd9f98e7233e4dd15`）在取消后为 `cancelled`，但操作 `83efb2f9-5984-41bc-a5e8-cd31749fd513:write:agent:1:tool:deterministic` 保持 `unknown/cancelled_effect_unconfirmed`。测试独立观察到外部效果值从 1 变为 2，实际 `tools/call` 只有一次，发送 `notifications/cancelled` 不等于效果撤销。

停止插件与 Temporal 后，普通历史、取消状态、unknown 提示、调用证据与再运行核实门槛仍可读；没有通过查询启动新执行。证据：[真实双离线记录](../../output/playwright/faults/engine-offline-evidence.json)、[unknown 重跑保护](../../output/playwright/faults/unknown-repeat-guard.png)、[双离线历史](../../output/playwright/faults/engine-and-plugin-offline-history.png)。这条测试明确操作本轮自有服务，未停止现有实例。

## 界面证据与已修正问题

四场景每个都有填写、准备就绪、结果三个状态，在 375/768/1024/1440px 分别保留内容和动作截图，共 96 张；48 组关键动作通过实际 trial click 与完整 viewport bounds，另逐张视觉检查 32 张四场景表单/结果 content 图并抽查准备动作，无横向截断或文字叠压，长结果通过纵向滚动可达。[`responsive-control-evidence.json`](../../output/playwright/task-experience/responsive-control-evidence.json) 记录关键动作的实际 bounds。另有 4 张整页结果图、2 份下载报告；[shell-experience](../../output/playwright/shell-experience/) 保留首页、结果、设置、制作、资源、插件和计划在四档宽度的 28 张截图。示例为 [375px 保存原文结果](../../output/playwright/task-experience/capture-research_notes-result-375-content.png)、[1440px 市场研究结果](../../output/playwright/task-experience/research-tradingagents_advisory_research-result-1440-content.png)。

Finance 在四宽度各保留制作/报告截图共 8 张，如 [375px 模板制作](../../output/playwright/finance-ux/author-375.png)、[1440px 报告](../../output/playwright/finance-ux/report-1440.png)。计划补充保留 [375px 每周安排](../../output/playwright/schedule-experience/weekly-ordinary-375.png) 和 [375px 复杂安排](../../output/playwright/schedule-experience/custom-ordinary-375.png)。专家分栏已补跑 2 项 Playwright（13.7s）并持久保存四档属性/图视口、资源/插件草稿与导出 YAML：如 [375px 属性](../../output/playwright/expert-experience/expert-properties-375.png)、[768px 图平移](../../output/playwright/expert-experience/expert-graph-pan-768.png)、[导出的 YAML](../../output/playwright/expert-experience/expert-export.yaml)。

| 实际观察或回归问题 | 修正与复验 |
| --- | --- |
| 专家页 375px 顶部动作被 `shrink-0` 截断，页面整体无横向溢出仍漏报 | 共享 PageContextBar 动作允许完整换行，补保存按钮 bounds；专家组件、最终 19 项 E2E 和专家补跑已通过，四档属性/图视口截图已持久保存 |
| 默认风险项因 schema.default 的 null 读投影占位而未选中；行情字段与数组显示过于技术化 | 保留作者显式默认并修复 schema fallback；最终真实市场任务风险选中，报价/时间/过期状态用中文业务标签、数组无数字索引；四档截图复验通过 |
| 历史日期只按 UTC 解释会漏掉与 UTC 不同的本地当天，刷新沿用旧分页范围会隐藏新运行 | 日期边界转换为浏览器本地日对应的 UTC，刷新清除 offset/snapshotAt；真实 27+1 Notes 及 Kiritimati 日期专项通过 |
| 仅保存原文响应丢失后重新提交可能错误生成第二个运行 | 故意先接受请求再断开响应，浏览器重试保持相同 launchId；实际历史总数为 1，无第二次模型/写操作 |
| Finance 中文模板名支持曾改变原英文名称规范，引起原合同回归 | 英文规范保留，仅为空的规范名使用中文回退并独立生成 slug；最终全后端 539 项与独立 Finance 4 项通过 |
| 大产物、报告工具真实 id/slug 与普通结果关联不足 | 基于冻结映射关联报告公开 ID，主正文按需加载可读 run artifact，保留下载；结果组件、后端投影及实际两份 Finance 报告直达/下载通过 |
| 模式切换可能覆盖尚未应用的映射/资源/插件草稿 | 保持编辑器挂载并阻止未应用 JSON 被覆盖，模式切换不发写命令；专家两项 E2E 和 Finance 草稿浏览器复验通过 |

## 原交付结论与当前验收边界

原实现任务曾据当时同 Core 制品的 19 项 E2E、539 后端测试、208 前端测试、4 项 Finance 测试、双离线故障、四档视觉和静态/构建检查，记录 23 项待办及调整后 C1–C8 完成交付。原实现交付阶段未提交、推送或部署，未处置现有实例数据。当前独立验收及发现问题的修复仍在进行，本文不宣告修复后版本通过；最终结论和剩余事项由 [独立验收索引](sprint-verification.md) 记录。

本地受控 provider 不证明付费供应商、市场数据真实性或生产部署可用性；按用户调整完成的自动化体验验收也不等同真实用户无讲解操作观察。
