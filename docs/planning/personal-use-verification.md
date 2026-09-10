# 个人使用优化共同验收

本记录对应[实施计划](personal-use-implementation-plan.md)与[24项Sprint任务](personal-use-sprint-backlog.md)。当前基线为 `5a993684eb35f655d46cffbec2c0a3f73c55fd4e`，PU-S1继承工作区未提交成果；S2–S6及本次共同验收在该工作区继续实施。历史阶段数字不计作本次验证。

状态：24项主体任务及C1–C11共同验收已完成，交付保留在未提交工作区。保持个人本地内网MVP，不包括未排期候选、提交、推送、部署或原实例数据处置。

后续三项实测问题修复及两个 GOAL 的独立闭环复验见[三项实测优化交付与验证](observed-gaps-verification.md#独立闭环复验2026-09-11)：26+9项必需用例全部通过，完成检查均为 COMPLETE。本文其余阶段状态、数字和版本保留历史时点。

## 任务与完成标准映射

| Sprint | 主体任务 | 共同标准 | 本次证据状态 |
| --- | --- | --- | --- |
| PU-S1 | pu-connect-feedback、pu-markdown、pu-model-diagnostics、pu-diagnostic-ui、pu-s1-verify | C1–C3；pu-a01–03 | 继承[S1阶段记录](personal-use-s1-verification.md)，最终后端/前端/E2E与真实模型已复验 |
| PU-S2 | pu-result-disclosure、pu-result-export、pu-s2-verify | C4；pu-a04 | 已通过本地阶段及最终共同验证 |
| PU-S3 | pu-usage-projection、pu-budget-contract、pu-model-controls、pu-s3-verify | C5；pu-a05 | 已通过本地阶段及最终共同验证 |
| PU-S4 | pu-result-metadata、pu-result-organizer、pu-attention-inbox、pu-s4-verify | C6–C7；pu-a06–07 | 已通过本地阶段及最终共同验证 |
| PU-S5 | pu-draft-contract、pu-draft-ui、pu-result-compare、pu-s5-verify | C8–C9；pu-a08–09 | 已通过本地阶段及最终共同验证 |
| PU-S6 | pu-notes-read-api、pu-notes-page、pu-notes-links、pu-s6-verify | C10–C11；pu-a10–11 | 已通过本地阶段及最终共同验证 |

## 最终版本核验

以下各项已使用最终代码、检查结果与运行证据核验；命令和证据映射见下文。

- 接入及阅读：五态、就地连接/输入保留、绑定变化与稳定启动身份；Markdown声明/历史/附件、四档宽度与键盘。
- 成品交付：成功与局部/取消/unknown/无声明/大产物、剪贴板及下载失败；Finance原下载；插件与引擎实际离线后的读取、导出和比较。
- 用量与预算：调用身份去重、日界线、缺值和网络覆盖；单次输出上限、旧包hash、旧快照、两协议映射；真实请求及usage对账。
- 标记与处理：附属数据冲突、筛选分页保真、变化身份去重、unknown核实、无Run fire失败；关闭浏览器后自然定时真实成功及来源链。
- 草稿与比较：各JSON根、未应用/非法文本、schema变化、跨窗口冲突、启动响应丢失刷新恢复原身份；固定两Run/分节/状态/时间的确定性差异。
- Notes：独立只读API/页面、集合/字面搜索/稳定分页/特殊ID、公开冻结链接，新旧发布和Run分别核对。
- 共同回归：实际最新版的内置笔记整理、模型主动工具调用、自然定时成功；全新包/Workflow/业务字段；受影响A01–A18/D01–D06、仓库必需门禁、规范同步、资源清理。

真实provider沿用用户提供的同一配置，优先 `glm-5.3-flash`；不复制原始凭据到文档、日志或截图。本机运行附件放 `output/playwright/`，精简结果与复现命令在本记录收口。

## 最终检查结果

下列数量来自本次最终检查，未累加继承的S1或早期失败运行。最终Core源文件重新计算的digest与真实模型三条路径一致：`sha256:223cb2c6ec5f8d338cf503566508f39f462062949e8f33e9053b226250ee16e1`。Notes发布为1.1.0，真实运行冻结制品为 `sha256:f7264cb958ec502da846f478b77d9eb49453661c8ce778834d4697aa61f82cb2`。

| 范围 | 命令与实际结果 |
| --- | --- |
| Backend，`backend/` | `uv run ruff check app tests`、`uv run black --check app tests`、`uv run isort --check-only app tests`、`uv run mypy app`全部通过；mypy覆盖110文件 |
| Backend全量 | 设置独立 `TEST_DATABASE_URL` 后 `uv run pytest`：677 passed，202.51秒；保留1条既有Temporal sandbox导入警告 |
| Frontend，`frontend/` | `pnpm lint`、`pnpm typecheck`、`pnpm build`通过；生产构建完成 |
| Frontend全量 | `pnpm test:run`：62文件、289项通过；包含大文本大量代码分隔符导出的边界回归 |
| 全栈浏览器 | 设置独立 `DATABASE_URL` 后 `pnpm exec playwright test --workers=1 --reporter=line`：24 passed；包含四种普通任务、专家编辑、参数根、历史、自然运行之外的受控计划、S2–S6组合及四档宽度 |
| 实际双离线 | `pnpm exec playwright test --config playwright.fault.config.ts --reporter=line`：1 passed；真实关闭自有插件与Temporal后，确认结果及大产物导出、比较、个人标记、unknown更新仍可使用 |
| Compose | 根及拆分部署示例 `docker compose ... config --quiet`通过；拆分示例使用仅用于解析检查的占位环境变量，没有启动或部署 |
| 差异 | `git diff --check`通过；未提交、未推送、未建立PR、未部署 |

本次默认共享测试PostgreSQL曾在建表时报告文件权限错误；没有更改其权限、目录或数据。最终全量检查使用新建、仅本轮拥有的tmpfs PostgreSQL容器，测试按CONTRIBUTING创建并删除独立数据库。复现可使用符合[测试数据库要求](../../CONTRIBUTING.md#测试数据库与-e2e-环境)的独立PostgreSQL。

## C1–C11的具体证据

| 标准 | 本次证明 |
| --- | --- |
| C1 | `tasks.spec.ts`实际缺模型连接、显式预设选择、范围确认、模式切换及输入保留；`personal-use.spec.ts`先持久化启动身份，再丢弃已受理响应，刷新后仍沿同一launchId取得唯一Run |
| C2 | 共享Markdown组件/JSON附件回归；四宽度任务及结果截图、OL/UL标记与键盘焦点；最终真实正文与Notes复制保持原文 |
| C3 | `test_model_diagnostics.py`安全白名单、恶意/旧错误、配置与凭据修订隔离；最终真实模型观察及精确attempt链接；读取不探测 |
| C4 | `result-delivery`/`result-export`测试覆盖局部、unknown、取消、无正文、字面JSON、附件选择和失败恢复；全栈真实下载与剪贴板；`faults.spec.ts`关闭引擎/插件后读取并导出大JSON产物、确认未选部分提示；Finance原报告下载在四场景中保留 |
| C5 | 预算/usage合同与真实Temporal回归覆盖旧hash省略、快照、两个HTTP协议、截断失败、恢复去重、缺值/零与23小时当地日；`model-usage.spec.ts`编辑到运行与界面；真实请求上限及供应商usage逐项对账 |
| C6 | `test_result_organizer.py`并发首写、精确字段PATCH、过期修订、历史筛选；组合E2E实际备注冲突保留草稿、刷新持久化、筛选返回；标记前后完整Run相等 |
| C7 | 当前状态身份、重复观察/重启、unknown核实后新身份、无Run fire及已查看unknown保持可见；最终真实UTC自然触发、浏览器关闭时间及fire/Run来源链；标已查看不改Run |
| C8 | `test_task_drafts.py`与任务/JSON组件覆盖null、缺失、空值、数组、非法/未应用文本、来源和冲突；组合E2E修改当前schema后恢复原修订并启动、真实丢响应/刷新；整段提交期间禁用重入 |
| C9 | 共享确认内容、相同文字不同身份、分节选择、无正文、长差异有界；组合E2E固定两Run/分节并重载；实际双离线比较与大产物显式读取；最终真实手动/定时结果四宽度并排 |
| C10 | Notes真实PostgreSQL/HTTP/MCP、集合与字面搜索、稳定分页、特殊ID、只读边界、旧新发布冻结；最终Notes链接打开与复制；停止真实Notes后Core导出逐字节一致且收藏成功 |
| C11 | 上表24项任务全部覆盖；最终同Core的真实整理、主动工具及自然定时；全新package/workflow/业务字段的组合E2E与D01–D06回归；规范、数据影响及清理同步 |

A01–A15、A17–A18受影响部分由677项后端、24项跨栈与独立双离线共同覆盖，保留原不可变、恢复、取消、unknown、资源授权及插件隔离用例。A16的历史选型比较未改写、不重新运行已淘汰引擎；本次实际执行权威仍是Temporal。D01–D06由解耦、外部导入/旧hash、展示、Notes冻结链接及离线回归覆盖。

## 最终真实运行

| 路径 | Run / 结果 |
| --- | --- |
| 确定性保存原文 | `2e511e4d-9071-4052-9820-aa902f671707`，succeeded |
| 原内置 `research_notes/research` | `dc86161f-c32f-4347-9133-289198248ed6`，真实glm整理并保存成功 |
| 模型主动Notes search后生成并保存 | `d8d3245a-2007-4a4c-a8e3-38432fd263ff`，两次真实请求、确认工具操作及最终保存成功 |
| 浏览器关闭后的自然定时 | `7e24a8de-1542-4353-b98b-15100eead085`，2026-09-10 01:14:00 UTC自然触发，succeeded；并非调用立即执行 |

安排 `pu-final-3ae8d294-4401-4ec4-8096-d82f10fd64ff` 实际显示“安排已生效”后，浏览器在01:13:19.120510 UTC关闭；fire `sha256:c4ff8345ddd7d4bad0bf5fb556f7226e5ef88f138fd0b3558b69306d7123ddc6` 在01:14:00 UTC自然触发并关联上述Run，完成后安排已暂停。

4次实际HTTP请求，输入2465、输出1255 tokens；供应商允许字段、逐Run与当日汇总一致。独立工具验证包两次请求的 `max_completion_tokens` 均为2048，符合显式 `maxOutputTokens`；原内置包省略该字段时仍保留旧预算语义。两个协议映射由本地真实HTTP回归覆盖；本轮外部供应商成功证明使用chat_completions，不宣称外部Responses供应商验收。

为核对线上的请求上限，使用一次性本地透明转发，只记录模型名、输出限制、状态、usage及请求序号；未改变回复，也未记录密钥、请求正文或供应商原始错误。使用者可按同样顺序，以当前独立栈注册Notes、配置授权模型、准备及启动两种工作流，再创建明确时区的未来安排、关闭浏览器、读取fire/Run/usage并暂停安排复验。

## 交付、影响与清理

- 新增3张独立附属表：任务草稿、结果标记、执行更新查看回执；由现有 `create_all` 注册创建，没有修改旧表或迁移/重建原实例数据。
- 新增只读模型用量与附属数据API、可省略预算字段、Notes1.1.0页面与公开链接；普通模式仍支持全部合法JSON输入，Finance所有权与下载不变。
- 已同步产品说明、架构、开发规范、数据模型、Notes合同、设计说明、示例锁定hash及本地/拆分配置。长行为文件按职责检查；新增职责使用独立模块，保留既有编辑/投影边界。
- 本机证据在 `output/playwright/personal-use-final/`：`real-validation.json`、`request-limits.json`、`real-result.md`、`notes-offline-core-evidence.json`及四宽度截图；`output/playwright/faults/`保留真实双离线、未确认操作及大产物文件。完整检查日志与源码指纹同在最终证据目录。
- 真实模型自有进程、临时数据库、端口和暂停的launcher均已清理，产物密钥扫描通过；原测试容器、原实例数据及其他应用保持。最后一次性测试PostgreSQL由本轮独立清理。

没有剩余功能或验收阻塞。运行提供商未来可用性不是永久承诺，未排期候选未混入本次交付。S1的原历史数字仍只属于其原阶段；以上最终结果证明当前共同交付。
