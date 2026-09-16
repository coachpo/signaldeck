# 自动化测试消融与精简实测

在固定版本完成全部入口盘点与分组评估后，依据局部故障对照修改 7 个测试文件：后端 **877→876**、前端 **428→426**，E2E **27 项全部保留**。原版和最终版完整回归及适用门禁通过；另有一个现有平台恢复脚本因 fixture 合同失配失败，单独列明。可确认的收益是减少重复维护和三次数据库初始化、补齐字符串保真边界；重复测量未证明全套稳定提速。未实验范围保留，不宣称全范围完成消融或绝对等价。

本记录对应 2026-09-16 从 `7c4bcbcf` 开始的本地测试精简。开始时工作区干净；不提交、不推送，不修改产品实现或放宽测试门槛。当前产品合同仍以[产品说明](产品说明.md)为准，本记录不是新的验收标准。

本文及关联盘点中的“保留”、测试数量和文件名只描述该次实验。后续移除示例依赖时删除的测试或验证入口，不改写这些历史结果；当前平台测试不得依赖 `demo/`，以[产品解耦原则](产品说明.md#工作流与平台解耦原则)为准。

## 方法与解释边界

先盘点默认 CI、独立测试、验收编排器和历史探针，再选择局部候选。相同故障分别施加到完整组和候选组；先确认原组能检出，再判断候选是否失去检测能力。多个候选同时移除后共同验证。无故障运行必须通过，测试加载或服务启动失败不算故障被检出。故障仅注入临时副本，产品文件不留变异。

保留或删除以断言对应的契约和实际故障结果为依据，不按文件名、相同代码行或测试数量推断。未实际进行故障对照的范围仅完成盘点、风险评估或基线执行，不称为已完成消融。已有机制消融的“关闭缓存/重试/限流”等配置实验，不等于删除测试的消融实验。

环境为 macOS arm64、Node 24.17.0、现有 backend Python 3.14.4、uv 0.11.7；与 CI Python 3.13.13/Linux 不同。入口 pnpm 报告 11.15.1，项目执行通过固定 pnpm 10.30.1 转交。使用真实本机测试 PostgreSQL、固定 Temporal CLI 和受控 provider；不调用付费 provider，不连接用户应用数据库。独立测试只清理自己的 UUID 库、进程和临时目录。

最初并行基线出现超时和大幅耗时波动，同时观察到本任务之外 `.claude` 验收工作区的 Vitest 进程；未终止或修改这些进程，也不据此认定具体 CPU/磁盘瓶颈。后续本任务的重型测量按队列串行，仍不能控制整台主机的其他活动，不能将本机耗时等同于 CI 性能。报告区分总进程时间、测试运行器时间和单项 call/setup 时间；有波动的原始样本保留，不据一次快慢声称提速。

基线开始后另一个任务修改了共享工作区的 backend、frontend、插件和 Docker/Nginx 文件，并新增 `test_plugin_pages.py`、`playwright.integrated.config.ts` 等自动化入口。本任务不回退、不接管这些改动。盘点范围锁定开始时的 `7c4bcbcf87adce626fcf6fe7dc1ef23e98538a02`；外部任务随后新增的测试未纳入本轮消融，不将本报告冒称为这些新增测试的评估。共享工作区初次执行结果只代表该次实际运行，不能作为严格同源码性能对照；后续对照使用固定修订的隔离归档，明确区分这两类证据。

随后按用户要求将本次改动迁至独立 Git 工作树 `signaldeck-test-ablation-20260916`，分支 `codex/test-ablation-20260916`，基于上述初始修订。本任务已从原工作区精确撤去自己的两处后端测试改动和报告，保留另一任务的全部修改。后续交付只位于新工作树；此前冻结副本的同源码实验可继续复用。

## 全部入口与 CI 范围

| 入口 | 实际范围与关键依赖 |
| --- | --- |
| `.github/workflows/ci.yml` backend-quality | backend 目录 `uv run pytest`；真实 PostgreSQL、Temporal、独立插件进程，部分 pytest 再调用 Notes 浏览器。另跑 ruff/black/isort/mypy。 |
| 同文件 frontend-quality | `pnpm test:run`；Vitest 的 `src/**/*.{test,spec}.{ts,tsx}`，jsdom、Testing Library；另跑 lint/typecheck/build。 |
| 同文件 frontend-e2e | `pnpm test:e2e`；14 文件 27 个 Chromium 测试，CI 1 worker、失败最多重试 2 次。独立故障配置不在默认 CI 命令中。 |
| `frontend/playwright.fault.config.ts` | 单独串行执行插件离线后停止自有 Temporal 的故障路径；不能用普通配置的同名测试替代。 |
| `plugins/finance/tests` | 5 个独立 pytest 项，其中 1 项调用真实 Finance 浏览器；另有 6 条断言的 Node authoring 脚本，未由默认 CI 显式调用。 |
| `plugins/notes/tests/browser.mjs` | 由 backend `test_notes_browser.py` 包装，不能重复计入用例总数。 |
| `plugins/tests/image_smoke.py` | 3 个独立插件镜像的打包/HTTP/MCP 验证，默认 CI 未执行。 |
| `backend/experiments/ablation` | 5 个测试函数、11 场景×2 机制变体×5 默认重复＝110 项；普通 pytest 不收集。 |
| `backend/experiments/engines` | Temporal、Prefect、Hatchet 的独立固定依赖和历史比较探针；不属于当前产品 CI。 |
| `backend/scripts/acceptance*` | 20 个验收配方复用现有测试并附加恢复、Compose、依赖边界和证据检查；配方不能再计为独立测试数量。 |
| `backend/scripts/verify_goal_case.py`、`goal_verification/**` | 35 个配方编排原生套件、Finance、fault、静态检查和真实 provider 验收；29 个配方含真实 provider 分支。本轮不调用该付费分支。 |
| `backend/scripts/*recovery.py` | 独立的产品恢复和固定 Core 制品恢复探针。 |
| `frontend/scripts/goal-verification-{browser,schedule}.mjs` | 消费本轮真实运行的证据，检查离线历史、用量、来源和浏览器关闭前后定时行为；不能用假造的输入冒充完成。 |
| `docker/verify_target_stack.py`、`inspect_target_ui.mjs` | 隔离 Compose 中的运行、制品、插件及浏览器检查，需要本轮部署证据。 |

本次实测时的 Docker 镜像工作流构建拆分 backend/frontend 镜像，不执行上述镜像 smoke 或根组合镜像验收；当前镜像入口以[部署说明](../docker/deployment.md)为准。清理工作流不提供额外测试覆盖。

公共 fixture 保持不变：backend 每项独立 PostgreSQL 库、settings/engine cache 清理和 API token 隔离；Temporal/插件 helper 保留真实进程边界；前端 setup 的 ResizeObserver、IntersectionObserver、matchMedia 和固定几何值是 jsdom mock，不能证明真实响应布局。E2E fixture 使用独立库、服务端口、受控模型及插件，保留真实浏览器和跨进程边界。未删除测试依赖或修改锁文件。

没有发现已配置的 pytest-cov/Vitest coverage provider、mutmut/Stryker 等变异框架，因此本轮采用定向故障注入，不新增大型基础设施，也不提供不存在的覆盖率前后百分比。没有提交的 `.snap`、像素基线、`toHaveScreenshot`、ARIA snapshot 或 axe 扫描。截图是执行证据；role/name、标签、键盘和布局断言只验证实际覆盖的语义与交互，自动化通过不代表完整可访问性或 UI/UX 验证。

历史与契约保留依据包括：`0924f95e` 引入 Inventory toolbar 可省略行为，仍保留独立无 toolbar 分支；`1e80999e` 修复专家任务入口，仍保留普通/专家切换后的可见性和导航检查。Core API 的真实 Logfire 405 回归仍走数据库支持的 `/api/runs` 路径；只移除完全不读取数据库的路由/错误投影测试的数据库准备，不以 mock 替换该历史回归。

## 基线、实验和最终验证

逐文件盘点见[后端](test-ablation-2026-09-16/backend-inventory.md)、[前端](test-ablation-2026-09-16/frontend-inventory.md)，补充入口见[插件与历史探针](test-ablation-2026-09-16/plugins.md)、[辅助验收](test-ablation-2026-09-16/auxiliary.md)。后端完整初始用例标识见[877 项清单](test-ablation-2026-09-16/backend-nodeids-before.txt)，机制实验另实际收集了[110 项](test-ablation-2026-09-16/mechanism-nodeids-before.txt)，收集不算执行。所有未运行或未完成对照的范围保留原测试。

### 实际故障对照

| 局部组 | 原组 | 删除/合并候选 | 决策与最终检测能力 |
| --- | --- | --- | --- |
| Core HTTP / auth | 10 例，7/7 个可观察故障检出 | 9 例，7/7 检出 | 接受；401、CORS、错误 code/status、秘密键过滤及已移除路由仍受断言保护；数据库 fixture 生命周期 8→5。 |
| 冻结效果投影 | 14 例，3/3 故障检出 | 12 例，2/3 检出 | 拒绝；冲突声明误取首项只有拟删除的参数能检出，保留全部 14 例。 |
| 共享 UI 三组件 | 10 例，11/11 故障检出 | 同时精简为 7 例，11/11 检出 | 接受；名称、mixed 状态、回调、内容归属、滚动、toolbar/filter 与无 filter 内容均保留检测。 |
| 两个 API client 测试文件 | 13 例，4/5 故障检出 | 缩减根参数后 9 例，仅 1/5 检出 | 拒绝删除参数。新增空白/换行根字符串后最终 14 例，5/5 检出。 |
| Finance authoring | 6 条断言，4/4 故障检出 | 同时去 2 条后只检出 2/4 | 拒绝；精确字节往返与编辑器中的代码保护各有独有检测，全部保留。每个变体/样本重复 3 次。 |
| Chromium shell | 5 例，4/4 故障检出 | 保留 5 例，仅移除同状态重复循环，仍 4/4 检出 | 接受；375/768px 溢出、隐藏任务链接、错误 href 均仍检出。额外删除 768px 的联合候选只测两种溢出、检出 1/2，已否决，不把未测的另两种故障计入其分母。 |

HTTP 另有删除 handler 第二层清洗的变异：原组和候选均存活，因为构造器已经清洗输入。该样本未造成可观察泄漏，既不计为有效故障，也不能据此认定真实覆盖缺口。API 的 `trim()` 样本不同：用合法非空字符串直接探测后，原实现保留字节、变异实现确实改写字节，证明这两个 API 测试文件原先漏检该边界；新增参数使用原来的 launch 与 schedule 精确断言补齐，未修改产品代码。

故障失败节点与结果见 [HTTP 原始记录](test-ablation-2026-09-16/backend-http-results.json)、[效果参数对照](test-ablation-2026-09-16/backend-effect-results.json)、[前端完整/候选/最终矩阵](test-ablation-2026-09-16/frontend-fault-matrix.json)及 [Finance 重复样本](test-ablation-2026-09-16/finance-authoring-results.json)。这些局部样本不能推导全仓故障检出率，完整回归通过也不证明绝对等价。

后端的文件、精确 before/after 替换、初始源码 SHA256 和对应失败节点另见 [HTTP 故障规范](test-ablation-2026-09-16/backend-http-evidence.json)、[效果故障规范](test-ablation-2026-09-16/backend-effect-evidence.json)。独立[只读复核](test-ablation-2026-09-16/review.md)未发现六个测试文件精简引入的具体契约损失；审阅指出的证据粒度问题已用原始执行记录补齐。

### 已实施精简清单

| 测试位置 | 方式 | 保留或替代覆盖 | 限制 |
| --- | --- | --- | --- |
| [test_auth_middleware.py](../backend/tests/test_auth_middleware.py) | 合并两个缺少 bearer 的用例；仍分别发送不带 Origin、带 Origin 的请求 | 同文件 `test_api_runs_rejects_missing_bearer_token_with_and_without_origin` 保留所有原 status/body/CORS 断言；matching token、非 ASCII、health、默认配置仍各自测试 | 两请求现在共享一个 fixture；本次 7 个故障不穷尽所有请求顺序故障。 |
| [test_core_api.py](../backend/tests/test_core_api.py) | 404 和合成 ApiError 测试直接创建真实 `create_app(init_database=False)`，不准备无关数据库 | 原 HTTP 路由、中间件和错误处理器仍参与；数据库依赖的 `/api/runs` 200/405 测试保留 PostgreSQL | 不以这两个测试证明数据库初始化或持久化行为。 |
| [resource-selection-checkbox.test.tsx](../frontend/src/components/shared/resource-selection-checkbox.test.tsx) | 删除单独的可访问名称重复用例 | 状态转换和回调测试已有带不同调用方 name 的 `getByRole`；名称丢失变异仍失败 | 不是屏幕阅读器或完整可访问性验证。 |
| [workspace-page-shell.test.tsx](../frontend/src/components/shared/workspace-page-shell.test.tsx) | 删除重复内容归属用例 | 首例已有 body 包含内容、rail 不包含内容和顺序断言；无 rail 分支保留 | jsdom 几何为 mock；不证明真实浏览器布局。 |
| [inventory-page-shell.test.tsx](../frontend/src/components/shared/inventory-page-shell.test.tsx) | 把内容包含、控件隔离与顺序合并到无 filter 用例 | 保留原 Create action 输入，保留有 filter、无 filter、无 toolbar 三分支；仅无 filter 丢内容的故障在最终组合中仍检出 | 没把不同条件组合当作等价；其他布局风险仍依赖浏览器覆盖。 |
| [workflow-platform.test.ts](../frontend/src/lib/api/workflow-platform.test.ts) | 保留全部原根值参数，新增 `"  source text\n"` 一项 | 现有 launch 与 saveSchedule 精确值断言同时保护字符串空白/换行，消除该局部组的 trim 漏检 | 增加 1 例是故障证据驱动的加强，不是为测试数量设定目标。 |
| [shell.spec.ts](../frontend/e2e/shell.spec.ts) | 删除任务目录初次加载后的一行重复 href 可见性循环；不减少用例 | `openSavedTaskCatalog` 已逐项检查同一批 href；模式切换返回后的第二轮检查仍保留；四档视口及所有导航断言保留 | 只验证四个浏览器可观察故障，不代表像素回归或完整可访问性审计；不声称显著性能收益。 |

未删除全局 fixture、依赖、快照或任何测试入口；未修改超时、重试、容差、skip、错误过滤或生产实现。前端删除 3 例、补充 1 例，428→426；后端合并 2 例为 1 例，877→876。没有证据支持的参数、恢复测试和高层用户路径保留。

### 后端完整验证与耗时

固定完整源码归档，同一目录、交付树的同一独立 Python、同一 PostgreSQL 和相同命令；执行顺序为完整→精简→精简→完整。每轮保留独立结果，命令的 JUnit 输出路径保持相同：

```sh
/Users/qingli/Documents/ChatGPT/signaldeck-test-ablation-20260916/backend/.venv/bin/python \
  -m pytest -q --durations=30 --junitxml=/tmp/sd-backend-frozen-current.xml
```

| 范围 | 原版 | 精简后 |
| --- | --- | --- |
| 完整 pytest | 877/877，两轮全过 | 876/876，两轮全过 |
| 全量 pytest 时间（秒） | 285.21、269.02；中位 277.115 | 270.76、269.09；中位 269.925 |
| 全量进程墙钟（秒） | 290.003、271.951；中位 280.977 | 273.763、272.344；中位 273.053 |
| HTTP 两文件局部 pytest，3 对 | 中位 1.76 秒，范围 1.74–1.92 | 中位 1.39 秒，范围 1.35–1.39 |
| 同一局部进程墙钟，3 对 | 中位 3.915 秒，范围 3.665–3.950 | 中位 3.319 秒，范围 3.249–3.334 |

局部中位墙钟少 0.596 秒，对应减少三次无关数据库准备。**后端全量没有证明稳定提速**：第二对反向运行时精简版并不更快；第一对中未修改的恢复/超时测试本身即有数秒变化，不能把整套的差额归因于这次精简。四轮节点集合逐项一致，唯一差异是两个原 auth 节点被一个合并节点替代，无 failure/error/skip。

详见[后端报告](test-ablation-2026-09-16/backend.md)、[四轮耗时和节点差异](test-ablation-2026-09-16/backend-full-timing-repeated.json)、[四轮逐节点结果](test-ablation-2026-09-16/backend-four-run-node-outcomes.json)、[未改测试的时长变化](test-ablation-2026-09-16/backend-junit-timing-analysis.json)、[最终 876 节点](test-ablation-2026-09-16/backend-nodeids-after.txt)。归档与交付树 207 个 backend 源、测试及依赖文件[逐字节一致](test-ablation-2026-09-16/backend-source-manifest.json)。交付树的 `ruff check app tests`、`black --check app tests`、`isort --check-only app tests`、`mypy app` [均通过](test-ablation-2026-09-16/backend-gates.json)。既有 Temporal 延迟导入与故意异常 token 输入的 Pydantic 警告未被屏蔽。

### 前端完整验证与耗时

在新工作树 `frontend/` 使用完全相同命令，两轮原版、两轮最终版：

```sh
pnpm test:run --maxWorkers=2 --reporter=json --outputFile=/tmp/signaldeck-frontend-measure.json
```

| 范围 | 原版 | 精简/加强后 |
| --- | --- | --- |
| 完整 Vitest | 84 文件、428 例，两轮全过 | 84 文件、426 例，两轮全过 |
| 全量墙钟样本（秒） | 87.974、57.503；中位 72.739 | 69.808、85.388；中位 77.598 |
| 三个 UI 文件，3 对交替计时（秒） | 5.787、5.978、4.124；中位 5.787 | 5.567、5.465、2.498；中位 5.465 |

**未证明全量提速**。全量最终中位数更高，且样本范围明显重叠；不能把这种主机/启动波动直接归因于测试变更。局部 UI 墙钟中位少 0.322 秒，同样不足以推断稳定全量收益。可确认的是移除重复 render/断言维护、保留本次 11 个 UI 故障检测，并加强 API 字符串边界。

原版和最终 `pnpm lint`、`pnpm typecheck`、`pnpm build` 均通过；最终格式收尾后再次通过。最初共享工作区的 `result-history` 5 秒超时在这四轮未复现，不代表已证明没有不稳定性。详见[前端实测报告](test-ablation-2026-09-16/frontend.md)、[完整命令/墙钟](test-ablation-2026-09-16/frontend-validation-results.json)、[局部配对样本](test-ablation-2026-09-16/frontend-ui-timing-results.json)、[最终静态检查](test-ablation-2026-09-16/frontend-final-quality.json)、[精确故障替换](test-ablation-2026-09-16/frontend-experiment-spec.json)。[原始 428 节点](test-ablation-2026-09-16/frontend-nodeids-before.json)、[最终 426 节点](test-ablation-2026-09-16/frontend-nodeids-after.json)及[差额](test-ablation-2026-09-16/frontend-node-delta.json)可逐项复核。

CI 的 backend/frontend VERSION 与各自 manifest 同步检查通过（均为 0.1.0）。本次七个测试文件均未超过 300 行，没有新增普通行为代码；报告 JSON 和 Markdown 属于本次要求的实测证据，不是产品或测试基础设施。

### 浏览器、插件及补充验证

| 入口 | 实际执行 | 耗时与边界 |
| --- | --- | --- |
| 普通 Chromium E2E | 原版与最终均 27/27，通过，无重试、跳过或 flaky | 各完整跑 1 次；Playwright 报告总时间 148.986→148.250 秒，含服务启动/构建/清理。约 0.5% 差异不足以声称稳定提速。 |
| 独立 fault 配置 | 1/1，通过；`engineStopped=true`、`pluginStopped=true` | 33.183 秒；真实执行双依赖离线后的历史读取，不以普通配置替代。 |
| shell 清洁局部对照 | 完整与最终各 3 次，共 30/30，通过 | 五例 body 合计中位 5.894→5.788 秒；只受改动的导航例中位 1.104→1.017 秒。不含共享启动；非交错顺序有热身影响，不宣称显著提速。 |
| Finance 专项 | 5/5 pytest，通过，含真实浏览器；Node authoring 通过 | pytest 30.67 秒，1 次；没有修改这些测试。 |
| 既有机制实验 | 110/110，通过；配对完整性检查通过，`source_drift=[]` | pytest 111.42 秒，默认每变体 5 次。是机制实验基线，不是测试删除对照。 |
| Core 制品恢复探针 | 通过 | 已确认调用不重放、旧/新制品隔离、缺失/篡改拒绝及自有进程清理；约 64.57 秒仅为建目录至报告写入时间。 |
| 完整平台恢复脚本 | **现有基线失败** | 启动即 HTTP 422 `mapping_type`，旧 note fixture 只有四个字段，与当前 Notes 的 `sourceKind/sourceNoteIds` 输出不一致，尚未执行恢复阶段；保留并记录，不顺带修改产品或该历史脚本。 |

E2E 实际故障矩阵 40 项中的 9 个失败均为注入故障的预期检出，正常原版/最终回归均无失败。其余 13 个 E2E spec 没有进行定向消融，全部保留。普通、故障及实验服务使用独立端口/库；已清理本任务服务和注入源，没有停止原有服务。最后 `pnpm exec eslint e2e/shell.spec.ts` 与差异检查通过。

详见[浏览器逐文件/逐用例记录](test-ablation-2026-09-16/e2e.md)、[原版](test-ablation-2026-09-16/e2e-baseline.json)、[最终](test-ablation-2026-09-16/e2e-final.json)、[双离线配置](test-ablation-2026-09-16/e2e-fault.json)、[实际故障矩阵](test-ablation-2026-09-16/e2e-fault-matrix.json)、[精确注入源码和候选差异](test-ablation-2026-09-16/e2e-mutation-spec.json)、[三次重复数据](test-ablation-2026-09-16/e2e-timing-results.json)。机制实验的[完整 110 项数据](test-ablation-2026-09-16/mechanism-baseline.json)及[原工具汇总](test-ablation-2026-09-16/mechanism-summary.md)独立留存，不将其中机制启用/停用的性能差异冒充本次测试精简收益。

## 未完成消融、未执行及结论边界

- 所有初始测试入口均纳入盘点与分组评估；实际测试消融限上述 HTTP、效果参数、共享 UI、API 参数、Finance authoring 和 shell 局部组。其余测试即使全量通过，也没有取得可删除的故障/契约证据，全部保留。
- 独立插件镜像 smoke 未运行：指定的三个冻结镜像不存在，本轮未构建这些镜像；真实镜像包装边界仍未验证。完整隔离 Compose 验收、三个历史引擎探针及完整历史证据编排未重新运行，不把已有历史结果当作本轮通过。
- 真实付费 provider 分支未调用；其浏览器/自然定时附加脚本依赖本轮真实 provider 证据，也未执行。它们不因未运行而被删除。
- 完整平台恢复脚本仍存在上述 fixture 合同失配，不能把 Core 制品探针或普通测试通过当成该脚本已完成恢复验证。
- 未采集行覆盖率，未建立像素视觉基线或全面可访问性扫描。现有 DOM、键盘、交互、原生表单与响应布局断言只支持各自实测行为；不能由自动化通过推断完整体验质量。
- 数据针对任务开始时的固定修订及这次测试改动，不包含另一任务随后新增的产品与测试；未验证两条工作合并后的状态。本机并非 CI 的 Python/操作系统环境，不能推断生产或 CI 耗时。

因此，本轮只说明在已验证的契约和故障样本下保留了相应检测能力，并补齐一个 API 字符串边界；不声称测试集绝对等价、不存在回归风险或全部范围完成消融。
