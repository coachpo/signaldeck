# E2E 消融实验与最终验证记录

本页是 2026-09-16 实验的历史盘点，“保留”和路径不构成当前回归要求；后续示例测试删除不改写原结论。当前边界见[产品解耦原则](../产品说明.md#工作流与平台解耦原则)。

## 范围与原始基线
- `frontend/playwright.config.ts`: Chromium，27 用例、14 spec，fullyParallel；CI workers=1、失败重试2次，本地默认无重试。本次用 --workers=1 固定工作数。
- `frontend/playwright.fault.config.ts`: 同一个 faults.spec.ts，独立串行 invocation，额外停止 harness-owned Temporal。普通 CI 只跑默认配置；fault 配置不在 CI。
- 默认端口已有非本任务服务占用；第一次命令0用例运行，不能计作测试失败。未停止这些服务。后续全量基线设置独立端口8101/4273/18233/19081-4、独立/tmp build目录。
- 公共fixture: platform-fixtures.ts (v2 YAML/model resource/package seed), task-fixtures.ts (独立插件发布/业务资源/模型), held-plugin-fixture.ts (真实可阻塞MCP服务/故障控制), responsive-evidence.ts (375/768/1024/1440视口、trial click、可见/可用/边界/溢出)。harness启动隔离PostgreSQL库、受控provider、固定版本Temporal、dispatcher、artifact worker、3插件和生产前端构建。
- 没有 toHaveScreenshot、toMatchSnapshot、ariaSnapshot 或 axe 扫描。PNG是证据捕获，不能称像素差异视觉回归测试；现有a11y限可访问名定位、部分键盘焦点/Enter操作和可点击性，并非完整可访问性审计。JS/CSS覆盖率未配置。

## 所有文件的契约/风险评估
| 文件 | 用例 | 关键契约/独有风险 | 消融处置 |
|---|---:|---|---|
| decoupling.spec.ts |3|非内置包、重命名和业务同名字段、schema/2提示、冻结结果、历史复用、missing-only并发及坏源隔离|保留；两组字段不是等价冗余，分别抵御硬编码正常名称/碰撞名称|
| expert-resources.spec.ts |1|未保存密钥与服务/安装草稿跨模式和导航保留，浏览器持久存储无密钥，无外部写入|保留，未实验|
| expert.spec.ts |1|助手预算/原样提示词，模式草稿、图缩放/键盘、导入注释/导出/无修改保存不变性，四视口|保留，未实验；和workflow-packages编辑契约不相同|
| faults.spec.ts |1|取消后未知真实写入、重跑闸门、未知读不同语义、离线历史、冻结通用结果、附件按需读与导出/比较|保留；插件和Temporal同时离线配置不能以普通配置替代|
| history.spec.ts |1|27真实Run越过25条分页、稳定snapshot、筛选往返/刷新、非UTC日期边界|保留；不因27看似多而缩减跨页数据|
| model-usage.spec.ts |2|maxOutputTokens、旧快照不变、真实计量、预算覆盖独立于包、草稿恢复、有限预算失败恢复|保留，未实验|
| parameters.spec.ts |2|array非object根，非空/空手动和定时输入、null根精确传递|保留，数组/null是独立序列化边界|
| personal-use.spec.ts |2|未完成草稿、旧修订、丢响应跨reload同身份、导出复制、个人标记并发冲突、插件深链接、固定比较、旧jsonText恢复|保留；与tasks中的同页retry不等价|
| resources.spec.ts |1|write-only凭据保存/读/reload、URL规范化、内部ID不展示|保留；与只保留未保存密钥的expert-resources不等价|
| runs.spec.ts |1|真实hold模型后取消，实际cancelled、无伪造输出/成功证据|保留；不能由unknown外部工具写取消替代|
| scheduled-tasks.spec.ts |3|timezone/overlap/sync/trigger来源/删除后保留；缺失workflow启动失败；weekly/custom预览与模式草稿|保留，未实验|
| shell.spec.ts |5|通用导航、仅一个main、插件页面不编译进Core、四视口所有关键入口不溢出|重复初始链接检查已精简；768视口删除候选因故障漏检被拒绝|
| tasks.spec.ts |1（内部4场景）|4普通任务真实插件、缺模型修复、丢响应同身份、不可变结果、markdown键盘/长行、四视口关键动作、Finance独立报告下载|保留；场景类型有独立plugin/策略边界|
| workflow-packages.spec.ts |3|导入到控件保存和合并边原因；错误顺序不能保存且修复后不改原快照；关页面执行与重跑|保留；expert的检查错误不等价于阻止保存|

## 实验方法
隔离副本 `/tmp/signaldeck-e2e-experiment`，保留原测试和仅作候选变更的副本。所有故障通过同一page.addInitScript钩子在浏览器加载后注入，不修改产品源码。完整/候选同样生产构建、同样独立harness、workers=1。故障样本：768宽CSS溢出；375宽CSS溢出；隐藏任务目录链接；任务href错误。干净control用于排除候选自身失败。实验分别包含原组、仅删除初始重复href轮询的最终组，以及同时删除768视口的联合候选；联合候选因实际漏检被拒绝，全部四视口保留。

## 局限
初轮机器同时存在其他任务的Vitest和本任务前后端重型检查。初轮失败只记为“未修改基线失败”，不未经串行复核断定预存产品缺陷。并发耗时不作为稳定性能比较。其余未注入的E2E契约仅完成盘点评估及运行，不声称完成消融。

外部活动限制：初始E2E基线启动后，其他用户任务修改共享backend/app/api/platform_router.py、domain/tool_contracts.py及Docker/nginx；未覆盖或回滚。已启动harness的API及固定Core使用当时加载/发布的版本，但后续重新启动不再是相同源码版本。不可将跨此变更的全量前后耗时和通过率声称纯消融效果；隔离shell实验两组在同一次启动/同一个构建中比较仍有效。

后续冻结策略：外部修改进一步涉及E2E启动器、Vite、routes/layout及新增integrated配置。已从固定 7c4bcbcf87adce626fcf6fe7dc1ef23e98538a02 归档到 /tmp/signaldeck-e2e-frozen，版本见 /tmp/signaldeck-e2e-frozen-head.txt，依赖仅symlink现有锁定node_modules/.venv，后续对该冻结版本重新执行。初始清单是原有27项，不把其他用户任务随后新增的integrated配置计入已盘点/验证。

## 被外部源码漂移中止的预运行
`/tmp/signaldeck-e2e-before-isolated.json`：正常SIGINT清理，exit130，589.540s，13通过，2失败，1中断，11未执行（Playwright合计12 skipped）。这是为冻结版本重跑而中止，不是以skip获得通过。独占服务端口已全部释放。
- decoupling business-name collision：58.865s，立即执行后缺少接受提示，显示待确认/连接错误。
- history：231.769s，27个capture中26成功，120s轮询耗尽；第27个Run的node/agent为agent_execution_failed，tool/attempt均成功。不能未经复核归因产品或负载。
- 普通fault分支通过117.634s，但此配置未停止Temporal。
- 实验启动尝试 `/tmp/signaldeck-e2e-experiment.json`：harness在原60s限制内未就绪，0用例，75.572s含清理；无消融结论。不放宽原timeout。

最终执行环境迁移：用户要求独立worktree，使用 /Users/qingli/Documents/ChatGPT/signaldeck-test-ablation-20260916，固定7c4bcbcf87adce626fcf6fe7dc1ef23e98538a02；现有测试精简不改产品，node_modules与backend/.venv为独立锁定安装。shell实验依赖与harness已指向该worktree，后续修改只写该树。候选分为full、reduced（仅去初始重复href轮询）、no-tablet（合并删除重复轮询及768视口）；40项配对矩阵随后在本任务串行窗口内执行，结果如下。

## 最终结果（独立worktree、相同固定产品版本）
- 新树原测试：27/27通过，148.986s；最终测试：27/27通过，148.250s；两次均workers=1、retries=0、0 skipped、0 flaky。前后各完整运行1次，计时含harness/构建/清理；除日志和test-results输出位置外相同命令、端口及build目录。产品assets SHA-1逐文件核对相同。约0.737s（0.49%）差异不能归因于稳定提速。
- 独立fault配置：1/1通过，33.183s；证据明确`engineStopped=true`且`pluginStopped=true`，实际覆盖双离线历史分支。
- shell故障矩阵：40项，105.667s；31通过、9个注入故障按预期被检出。Playwright原始status保留为9 failed/unexpected；这些是预期变异检出，不是正常回归失败。完整和最终组都检出4/4故障样本，正常对照均5/5通过。
- 不保留768的联合候选：正常对照4/4通过；只实际测试2种故障，375溢出检出、768溢出漏检（1/2）。未对该已拒绝候选执行hidden/href，不能写1/4、3/4或全样本对照。完整/最终组对768故障均在文档溢出断言检测到1032px，证明该视口有本次样本下独有能力，拒绝删除。
- 局部清洁配对重复各3次：30/30通过，总51.072s。五用例测试body合计原组6.332/5.894/5.739s（中位5.894），最终组5.788/5.731/5.797s（中位5.788）。只受改动的导航用例原组1.263/1.104/1.035s（中位1.104），最终组1.007/1.052/1.017s（中位1.017）。worker串行、同harness，不含共享启动成本；非交错顺序仍有热身影响，差异很小，不声称显著性能收益。
- 未修改共享树阶段decoupling/history失败，在固定新树baseline与final各通过一次；没有改对应用例、延长timeout或减弱断言。只能说明在本次隔离串行条件下未复现，不证明不存在不稳定性。

### 精简清单
| 位置 | 实施方式 | 实验证据 | 保留的检测位置 | 局限 |
|---|---|---|---|---|
| frontend/e2e/shell.spec.ts 原41行 | 删除初始化同一UI状态的第二遍逐href可见性循环，1行；不删除用例 | hidden/href故障完整和最终均在openSavedTaskCatalog的原始断言被检出；最终全4故障均检出；正常5例各3次通过 | 同文件openSavedTaskCatalog第5–16行对API目录数量及每个真实href可见性检查；模式往返后逐href检查仍保留；全部四视口保留 | 仅证明本次4种故障样本及已有契约下保留检测，收益主要是减少重复维护；未穷举瞬时渲染时序 |
| frontend/e2e/shell.spec.ts 768视口 | **不实施**联合删除候选 | 768断点溢出只在该宽度检出，删除后失检 | 原768用例原样保留 | 已拒绝候选只测2故障，不夸大样本量 |

### 最终命令与产物
从新worktree的`frontend/`执行，统一环境为`SIGNALDECK_E2E_BUILD_DIR=/tmp/signaldeck-ablation-e2e-dist-isolated SIGNALDECK_E2E_BACKEND_PORT=8101 SIGNALDECK_E2E_FRONTEND_PORT=4273 SIGNALDECK_E2E_TEMPORAL_PORT=18233 SIGNALDECK_FAKE_PROVIDER_PORT=19081 SIGNALDECK_E2E_NOTES_PORT=19082 SIGNALDECK_E2E_FINANCE_PORT=19083 SIGNALDECK_E2E_ORACLE_PORT=19084`：
- 原/最终完整：`pnpm exec playwright test --workers=1 --reporter=json --output=<before-or-final-output>`。
- 双离线：`pnpm exec playwright test --config=playwright.fault.config.ts --reporter=json --output=<fault-output>`。
- 故障矩阵：同一新树harness，改用8201/4373/19233/20081–4及独立experiment build，`pnpm exec playwright test --config=/tmp/signaldeck-e2e-experiment/playwright.config.ts`。
- 局部重复：矩阵命令加`--project=clean-full --project=clean-reduced --repeat-each=3`。
- `pnpm exec eslint e2e/shell.spec.ts`通过；`git diff --check`通过。

机器证据：
- `/tmp/signaldeck-e2e-baseline.json` 与 `/tmp/signaldeck-e2e-final.json`：原/最终完整测试每例状态、耗时和node位置。
- `/tmp/signaldeck-e2e-fault.json`：独立故障配置完整结果。
- `/tmp/signaldeck-e2e-matrix.json` 与 `...-matrix-summary.json`：实际故障结果，精确project/nodeid/断言错误。
- `/tmp/signaldeck-e2e-mutation-spec.json`：完整注入JavaScript/CSS源码，full/reduced/no-tablet差异与候选说明。
- `/tmp/signaldeck-e2e-timing.json` 与 `...-timing-summary.json`：重复每例状态和耗时。
- `/tmp/signaldeck-e2e-frozen-baseline-build.sha`：前后相同生产assets指纹。

其余13个spec及shell中未改变的契约全部纳入盘点评估并完整执行，但未做定向消融，不声称这部分已完成故障矩阵实验。未配置代码覆盖率能力，不能报告覆盖率百分比变化。没有删除依赖、fixture、截图证据、任何业务路径或视觉宽度；不存在把自动化通过等同于完整UI/UX验证的结论。

### 所有原/最终用例body耗时（ms，不含共享harness）
| nodeid（文件与标题） | 原 | 最终 |
|---|---:|---:|
| decoupling.spec.ts :: D01-D04/D06: imported business-name collision fields drive ordinary form and frozen result | 10548 | 10555 |
| decoupling.spec.ts :: D01-D04/D06: imported renamed fields drive ordinary form and frozen result | 2087 | 2084 |
| decoupling.spec.ts :: D02: concurrent missing-only imports preserve the winning revision and isolate invalid sources | 112 | 134 |
| expert-resources.spec.ts :: expert service forms and installation review preserve drafts across modes without writing credentials | 806 | 852 |
| expert.spec.ts :: expert authors with named controls, keeps session drafts and fixes invalid step order | 3601 | 3532 |
| faults.spec.ts :: actual independent write remains unknown after cancellation and history survives plugin shutdown | 13477 | 13592 |
| history.spec.ts :: UX03: complete history preserves filters, respects local dates and refreshes the snapshot | 11912 | 11572 |
| model-usage.spec.ts :: PU-S3: optional output budget survives editing and model usage is readable | 6064 | 5982 |
| model-usage.spec.ts :: generic task budgets survive draft restore and freeze independently of the package | 7292 | 7289 |
| parameters.spec.ts :: array input uses the same definition for manual and scheduled launches without an object wrapper | 3965 | 3897 |
| parameters.spec.ts :: a task with no input starts with an exact null root through the ordinary form | 1538 | 2600 |
| personal-use.spec.ts :: personal workflow retains drafts and launch identity, delivers results, and organizes fixed comparisons | 7359 | 7039 |
| personal-use.spec.ts :: legacy unfinished input remains downloadable and recovers through the form | 1285 | 1275 |
| resources.spec.ts :: resource credentials are write-only through an ordinary form, save and reload | 487 | 492 |
| runs.spec.ts :: running cancellation reports actual stopped state and does not fabricate outputs | 5412 | 4933 |
| scheduled-tasks.spec.ts :: schedule retains timezone, overlap, synchronization state and trigger provenance | 4676 | 4696 |
| scheduled-tasks.spec.ts :: failed scheduled launch retains provenance with a readable failure reason | 593 | 624 |
| scheduled-tasks.spec.ts :: weekly preview and custom schedules preserve business input and advanced policy across modes | 3474 | 3577 |
| shell.spec.ts :: generic navigation owns one route shell without embedded finance pages | 1257 | 1174 |
| shell.spec.ts :: definition workspace and resources fit width 375 | 1159 | 1184 |
| shell.spec.ts :: definition workspace and resources fit width 768 | 1470 | 1469 |
| shell.spec.ts :: definition workspace and resources fit width 1024 | 1445 | 1414 |
| shell.spec.ts :: definition workspace and resources fit width 1440 | 1465 | 1529 |
| tasks.spec.ts :: UX01/03/06: four ordinary tasks execute with real plugins and retain reusable results | 36265 | 35525 |
| workflow-packages.spec.ts :: imported workflows retain their contract while named controls and graph explain every dependency | 1095 | 1124 |
| workflow-packages.spec.ts :: invalid step order is explained at the affected control and never saved | 1428 | 1477 |
| workflow-packages.spec.ts :: expert starts with ordinary task controls and reads durable results after closing the browser | 4296 | 4344 |

清理完成：临时实验源、故障注入钩子、冻结副本和本任务build目录已删除；精确注入源码和配置作为JSON报告数据保留用于复现。两组专用harness端口均无监听，未停止原有8001/17233等服务。测试报告/截图保留为交付证据，仓库未留临时注入或调试文件。
