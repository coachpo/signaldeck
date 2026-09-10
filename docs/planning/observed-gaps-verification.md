# 三项实测优化交付与验证

2026-09-11（Europe/Helsinki）。仅补齐模型输出上限、只读/写入不确定性及 Notes 来源过滤三项；复用已交付的 S1–S6。原六 Sprint、十三项 `pu-later-*`、文件/URL采集、外部通知及其他扩展均未重建或纳入。

## 独立闭环复验（2026-09-11）

本节是后续独立验收结果；下方实施阶段记录保留当时的 Run、计数及 provider 观测，不作为本次新执行证据。

| GOAL | 必需用例 | 完成检查 |
| --- | --- | --- |
| `sd-personal-use-all-sprints` | 26/26 通过，覆盖 C1–C11 | `COMPLETE` |
| `sd-observed-gaps` | 9/9 通过，覆盖 C1–C8 | `COMPLETE` |

无豁免用例。两份完成检查绑定同一源码指纹 `sha256:e968347525b6ddb0a6aac7e93517d075ee7812fed1c4d3dc116bde84a353426f`，真实运行使用同一固定 Core `sha256:a00475e79f99069e9b28a17e9d9923c2c92437a5e438e2e43085ec4c100ecf83`。完成后仅更新验收记录；产品、执行器及测试源码保持通过时的内容。

本轮补齐逐用例执行器、隔离源码快照、实际原生报告与真实运行原件的证据绑定，并增加8项模型计数/取消边界回归。执行器曾将 `innerText` 与 `textContent` 混用，以及在异步已读保存完成前读取 API；两处均按失败证据修正并通过定向重测。另补齐打开已生效安排、关闭浏览器、自然触发后重新打开处理结果的实际见证。首轮共享执行组中断留下的后续失败按技能恢复路径归档、重新初始化；最终所有用例在修复后的源码上通过，没有改写 GOAL 意图或降低断言。

| 最终原生检查 | 结果 |
| --- | --- |
| Backend `pytest` | 746 passed，3条警告；含工作区原有的4项独立测试存储用例，该存储改动未纳入本次提交。 |
| Frontend `vitest run` | 293 passed。 |
| Playwright 全流程 / 双离线故障专项 | 24 passed / 1 passed。 |
| Finance 自有页面专项 | 4 passed。 |
| Ruff、Black、isort、mypy；前端 lint、typecheck、build | 全部通过。 |
| 两份 Compose 配置、执行器 Python/JS 语法、文档引用和 `git diff --check` | 全部通过。 |

测试/API/固定 Worker 使用 Python 3.13.13，依赖来自现有锁文件。最终真实组含16个 Run，完成内置整理、模型主动调用 Notes 工具、自然定时三条路径；来源集合保持2→2→2→3，派生来源引用对应实际检索集合。浏览器于自然触发前关闭，触发后重新打开并确认已读保存。实际停止自有 Notes 与 Temporal 后，Run、结果、用量、元数据、导出、比较及故障提示保持一致；四宽度页面检查和键盘操作通过。

| 本轮真实上限 Run | 实际请求 | 报告输出 token | 结果 |
| --- | --- | --- | --- |
| `6cf7beb4-8166-458f-8f5e-01cbb58ef15c` | `max_tokens=16` | 16 | length；工作流没有输出成功成品。 |
| `1287ad3c-987f-4cb9-be14-608210beaeaf` | `max_tokens=4096` | 496 | succeeded。 |
| `8e39a26e-b72e-4cbd-8bb8-3d0271e96120` | `max_completion_tokens=16` | 501 | `model_output_limit_exceeded`；用量保留，结果分类为 `output_limit`。 |

这次实际复现了 provider 违反请求上限；它与下方实施阶段“两种字段都按16截断”的观测属于不同调用。两种 Chat 字段和 Responses 的完整边界矩阵继续由实际 HTTP 回归验证，不把一次 provider 行为视为长期保证。

本机逐项状态与不可变证据保存在 `.steward/goals/<alias>/verification/campaign/`；原始执行组和早期失败归档在 `.steward/controls/dual-goals-b81677b0dbdc/`。这些本地证据不纳入 Git。复现使用已冻结的 GOAL 和 [`verify_goal_case.py`](../../backend/scripts/verify_goal_case.py)：每项绑定 `--goal <alias> --case <id> --session <session>`，由验收技能设置 `CLOSED_LOOP_EVIDENCE_DIR`。会话控制 `config.json` 明确提供自有 loopback PostgreSQL 的 `testDatabaseUrl`、Python 3.13.13 环境的 `pythonEnvironment` 及固定版本 `temporalCli`；执行器在隔离源码副本中按锁文件准备依赖，真实组使用本机既有 `prism / glm-5.3-flash` 配置及凭据。缺少配置或证据时直接失败，不回退到历史结果。

职责自检未通过文件：无。`model_runtime.py`、`native.py`、`real/start.mjs` 分别保持模型 I/O、原生验证组、测试栈生命周期职责；`real/acceptance.py` 保持完整端到端验收叙事。本轮没有部署、切换已有服务或转换原实例数据；独立 PostgreSQL 存储改动及其诊断文件原样保留在工作区。

## 实际版本与证据边界

- 基线：`a518c65e831a70367fa3bb7f14b1bec9485692ad`；交付仍在当前未提交工作区，没有提交、推送、PR、发布或部署。
- 最终固定 Core：`sha256:a00475e79f99069e9b28a17e9d9923c2c92437a5e438e2e43085ec4c100ecf83`。本记录的15个实际 Run、最终原生回归与双离线验证使用此实现；先前 `75946c95…`、`37bda48a…` 的中间验证不计入最终通过数字。
- 源码清单摘要：`8e431ec86b948cf8a6505216a6116bd7dcaa9a1f2e4026c28cb6223d6a8a601d`；完整路径/散列、Notes release/artifact/contract 摘要见本机 `output/playwright/observed-gaps/verified/source-version.json`。
- 本机原始材料位于 `output/playwright/observed-gaps/verified/`；门禁日志在 `output/playwright/observed-gaps/checks/`。这些目录被 Git 忽略；新检出以本文、相应测试与当前规范为复现入口。
- 模型成功内容全部来自既有授权的 `prism / glm-5.3-flash`。协议边界的受控错误测试与真实模型调用分别标识，没有把模拟成功或旧记录当成本次真实成功。

## 实现差异与根因

| 实测问题 | 根因 | 本次实现 |
| --- | --- | --- |
| 上限配置未真正约束输出 | SDK 的缺省 Chat 字段与当时 provider 接入不匹配，且响应量没有二次校验 | 闭合 `providerCapabilities.outputTokenLimitParameter` 选择 SDK 原生 profile；冻结于模型绑定。接受响应前校验已报告输出量，超限记录 `model_output_limit_exceeded` / `output_limit`，保留 usage，停止模型/工具调用和整节点 `maxAttempts` 重启。 |
| 只读错误提示可能保存 | 所有非 attempt 的 unknown 被统一解释为写入效果不确定 | 共享 `effect_projection.py` 使用冻结工具 effect；模型仅生成回复，工具执行有独立证据；无写授权的完整冻结 Agent/节点也可判定为只读。缺少可靠历史合同仍保守，原 evidence 不改写。全部读取入口共享结果。 |
| 整理反复取回自身总结 | 原始资料与派生笔记没有公开来源属性，搜索同集合标题/正文会再次选中总结 | Notes 1.2.0 增加 `sourceKind` / `sourceNoteIds`；来源与笔记、操作回执同事务。公开 `includeDerived` 过滤；整理包显式缺省排除派生，原文保存为 original、整理保存为 derived。 |

模型配置示例（本次真实验证的显式选择，不按服务名称推测）：

```json
{"providerCapabilities": {"outputTokenLimitParameter": "max_tokens"}}
```

Chat 允许 `max_tokens` / `max_completion_tokens`，Responses 允许 `max_output_tokens`，不匹配的 API style、未知字段及显式 null 均拒绝。省略能力对象保持旧序列化和摘要；旧 Run 仍使用其固定配置与 Core。`maxOutputTokens` 和剩余总 token 预算继续取小。参数选择不触发读取探测。

超限检查在 SDK 成功解析及异常路径都执行，避免无效/截断回复绕过检查。`output_limit` 在汇总 `workflow_nodes_failed` 下仍显示明确诊断。已报告超限不能撤销已消耗 token；缺 usage 仍是未知。模型响应截断也不等于工作流结果成功。

## 本次真实模型参数、响应和用量

| Run | 实际请求字段 | 已报告输入/输出 token | 结束原因 | 工作流结果 |
| --- | --- | --- | --- | --- |
| `1107a3e4-cf5d-41b5-8b63-6fe380def18d` | `max_tokens=16` | 104 / 16 | length | failed |
| `18fed8e2-d6ff-4cd0-8b4b-e682b320134a` | `max_tokens=4096` | 104 / 554 | stop | succeeded |
| `0fde1b3b-bcc1-4591-865a-6cd25da20848` | `max_completion_tokens=16` | 104 / 16 | length | failed |

低上限的两次工作流都没有把截断内容当作成功输出。当前 provider 已对两种字段都按16截断，因此本次没有重现旧的真实超限响应；此前599/498等旧数字只用于根因背景，不作为最终版本的实测通过。当前版本的**超限拒绝、保留用量、零后续工具/模型调用、禁止节点重启及两个 failurePolicy**由 `test_model_output_enforcement.py` 和 `test_model_usage_runtime.py` 的实际 HTTP/Temporal 受控错误回归验证；这不是本次真实 GLM 超限样本。

附加的 `max_tokens=1` 请求被当前 provider 以 HTTP 错误拒绝，没有把缺 usage 当作0或宣称该值可用。独立延迟转发器仅延迟真实 provider 字节，用于验证响应丢失：Core 未收到的回复用量保持未知，即便观察转发器随后收到真实16-token响应，也不回填或重写 Core 证据。对应 `model-timeout.json` / `model-timeout-relay.jsonl`。

`provider-observations.jsonl` 与 `runs.json` 保存实际字段、响应ID、请求/响应散列、可见回复、usage、结束原因及模型/网络调用身份；按请求开始时间匹配 attempt，迟到响应不会误归到下一 Run。自然定时曾有一次未获响应的失败尝试，最终成功回复的用量与该未知尝试分开，未把汇总当作供应商账单。

## 连续来源集合与运行关联

来源A/B/C分别为下列原文保存 Run 的 `:save:agent:1:tool:deterministic` 操作，也是 Notes ID：

- A：`362c35b9-044b-4298-91ce-f473685fbb09`。
- B：`42fce39c-2744-47bc-8481-e254ab5be4e9`。
- C：`ed21cd62-d2e0-4ff3-80ec-27966d5379f4`。

| 执行 | Run | 来源集合 | 已确认回复输入/输出 token |
| --- | --- | --- | --- |
| 手动 | `5c3ba0f3-1148-4b16-a5d4-4605e0db59b3` | A、B | 461 / 1092 |
| 原修订重跑 | `a93109bf-96c9-4e35-87f4-83f456d76f9d` | A、B | 461 / 709 |
| 自然定时 | `53917c3b-4447-4379-a5e6-acecd8cb2422` | A、B | 461 / 1285 |
| 新增C后运行 | `b43aacd6-cbd0-44e0-a3fd-91197f731746` | A、B、C | 601 / 108 |

四次都创建独立 derived 笔记，保存的 `sourceNoteIds` 与实际搜索返回集合相同；首三次不含任何前次总结。新增C后取得三条原始资料，仍保留10/12欧元冲突及14欧元新增候选，没有把候选定案。来源集合、保存操作和完整引用见 `source-sets.json`，全部原始文本仍可读。

自然安排 `304e6e52-c9f9-41af-a345-51abea6e1446` 在 `2026-09-11 00:00 Europe/Helsinki` 自然触发（UTC `2026-09-10T21:00:00Z`），fire `sha256:753daad3f98956056fa90f8643504a655cdaa54d426711efd299adef2d4c68a4` 关联上表定时 Run，状态 succeeded，安排随后暂停。重跑的 `sourceRunId` 指向首次手动 Run；四次包修订均为 `07570cd2d267891787466e096f5133fb577a64a6f3ab5de029c02597e238a0bd`。

普通任务入口的“包含整理生成的笔记”缺省关闭，可显式打开；Notes 页面默认显示3条匹配原始资料，选择包含派生后显示7条（3条原始、4条整理），详情提供已确认来源链接。不是隐藏或删除派生记录，也不是跨 Run 缓存。历史未分类记录不根据标题/正文猜测，仍可查看并参加默认检索。

## 读写故障与离线读取

| 情况 | Run | 确认事实及读取语义 |
| --- | --- | --- |
| Notes 查询失败 | `2447c36a-4dfd-40fb-b9e3-985923874187` | 实际 MCP isError；没有 create 调用；`hasUnknownResults=true`、`hasUnknownEffects=false`，保留查询证据且无需保存核实。 |
| 已提交后回复丢失、回执可查 | `9c681b19-757e-4bc9-b9b3-94bb937ffef0` | 实际业务事务已提交；同 operation 查询回执恢复成功，不重复写入。 |
| 已提交后回复与核实都不可用 | `88dce327-676e-4a3b-9741-1cb6a1ddfc8a` | 实际笔记存在，create仅一次；逻辑 write仍 unknown，结果要求核实，未勾选确认时重跑按钮禁用。 |
| 只生成模型回复的调用超时 | `aeac55bf-eba6-4ff7-98a4-001ee223aaa0` | 真实HTTP回复被延迟，Core模型证据 unknown且usage未知；零工具调用，结果只提示只读结果未确认，没有保存警告。 |

写入故障的确认记录 ID 为 `88dce327-676e-4a3b-9741-1cb6a1ddfc8a:save:agent:1:tool:deterministic`，与未知 write operation一致。直接查看该笔记没有擅自更改 Core 的 unknown。`read-write-faults.json`、`notes-observations.jsonl`、`model-timeout.json` 保留完整关联。

真实关闭本次自有 Notes 与 Temporal 后，确认21082/18233端口不可达；15个 Run详情/结果/用量、全库历史与执行更新仍可读取。前后除用量响应的 `asOf` 外相同；确认正文 Markdown 导出逐字节一致。浏览器分别比较读/写故障状态及两次真实成功正文，未推断业务变化、未伪造无正文结果。只读无确认正文时导出禁用；有局部确认正文的只读失败导出由同版本原生故障E2E覆盖。证据见 `online-histories.json`、`double-offline.json`、`double-offline-result.md` 与对应截图。

## C1–C8完成对照与最终门禁

| 标准 | 当前实现的证据 |
| --- | --- |
| C1 | 闭合能力配置、style/null拒绝、冻结/旧摘要及三种实际HTTP字段矩阵：`test_model_budget_contract.py`；真实低/正常上限见上表。 |
| C2 | 相等/超出/缺usage、有效/无效回复、重放不发网络：`test_model_output_enforcement.py`；真实Temporal两个failurePolicy、maxAttempts=3仍只调用一次且不执行工具：`test_model_usage_runtime.py`；真实成功和截断另列。 |
| C3 | 原始冻结effect、历史缺失/歧义、模型回复与Agent授权的分类：`test_effect_projection.py`；真实读/写/模型超时见上表。 |
| C4 | 详情、结果、历史、执行更新、重跑、导出和比较统一投影；`test_task_experience.py`、结果组件测试、`faults.spec.ts`及本次15Run双离线。 |
| C5 | 来源存在/集合/授权拒绝、重复ID、原文不可附派生引用、事务回滚、去重回执：`test_notes_workspace.py` / `test_independent_plugins.py`。 |
| C6 | 来源集合2→2→2→3、自然fire、确认引用、原始矛盾、普通入口和Notes显式选择；新包/导入/hash：种子、编译及展示回归。 |
| C7 | 缺省旧hash、不可变绑定、旧/新Notes合同同时运行、历史未分类、独立数据所有权；相关原生回归通过，没有原实例数据转换。 |
| C8 | 下列完整当前工作区检查及同Core实际运行/双离线；规范、合同、示例与交付索引同步。 |

| 执行检查 | 最终结果 |
| --- | --- |
| `uv run --frozen pytest`（自有隔离PostgreSQL） | **738 passed**；1条既有Temporal `annotated_types` 沙箱导入警告。 |
| `uv run --frozen ruff check app tests` | 通过。 |
| `uv run --frozen black --check app tests` | 通过。 |
| `uv run --frozen isort --check-only app tests` | 通过。 |
| `uv run --frozen mypy app` | 111个源文件通过。 |
| `pnpm test:run` | **62 suites / 293 tests passed**。 |
| `pnpm lint`、`pnpm build`（含`tsc -b`） | 通过。 |
| `pnpm exec playwright test --workers=2` | **24 passed**。 |
| `pnpm exec playwright test --config playwright.fault.config.ts` | **1 passed**，实际停止自有插件及Temporal。 |
| Notes格式/JS语法、demo同步及发布合同 | 通过；相应后端回归包含在738项中。 |
| split Compose示例 `config --quiet`（占位环境值） | 通过；只更新Notes镜像示例tag，未部署。 |

检查日志使用 `*-verified.log`；Python测试/API为3.14.4，固定Core Worker为3.13.13，Node24.17.0，项目pnpm10.30.1，uv0.11.7，Temporal CLI1.8.3/Server1.31.2。长行为文件仅 `model_runtime.py`（374行）；模型I/O证据边界职责内聚，职责自检无未通过文件，未进行无关拆分。

## 合同、数据及交付边界

Core仅演进安全JSON配置/证据/读取字段，没有增加Core业务表或迁移框架。Notes新增 `note_provenance` 旁表，由 `create_all` 创建，不ALTER原 `notes`、不回填分类、不改写旧笔记。sourceNoteIds是事务中确认存在且属于授权集合的笔记引用，不宣称模型文本中的任意引用都正确。

Notes发布源版本为1.2.0；新示例必须配合相应发布及显式包修订使用。保存新发布或配置只改变当前指针，旧Run/hash/端点/快照不重写；旧服务和制品的保留、实际升级和原实例数据处置仍需按现行授权另行处理。本次没有执行这些切换。

复用了原预算/用量、安全诊断、结果/标记/待处理/重跑/导出/比较与Notes工作区；全量检查保留Finance所有权、四场景、取消、并发去重及恢复覆盖，没有接入真实Finance外部供应商或扩张产品范围。原共享测试PostgreSQL曾出现宿主机文件权限错误，本次改用自建临时容器验证，没有修改/清理共享库。暂停期间工作区出现的测试PostgreSQL默认存储改动属于另一项工作，原样保留，未纳入本次实现。

实际清理与最后差异检查见本机 `verified/cleanup.json`、`private-pg-cleanup.json` 及 `completion-audit.json`。没有待授权的部署/提交作为本GOAL前置；实时provider没有再次违反上限这一观测差异已明确记录，不把它伪装为本次真实超限复现。
