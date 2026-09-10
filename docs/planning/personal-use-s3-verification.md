# 个人使用优化 PU-S3 阶段验证

日期：2026-09-10。范围为 `pu-usage-projection`、`pu-budget-contract`、`pu-model-controls` 与本阶段联合验证；上游为 [Sprint Backlog](personal-use-sprint-backlog.md#pu-s3--用量可见输出上限可控)。交付在当前未提交工作区，不能仅凭 HEAD 重现。

## 已实现范围

- `Budget.maxOutputTokens` 是 Workflow Package v2 的可选正整数单次输出上限；省略不向旧定义、序列化或快照补字段，显式 `null` 不合法。执行采用该值与当前 Agent 剩余 `maxTokens` 的较小值。请求次数、总 token 和 deadline 保持独立；省略字段沿原执行逻辑。Chat Completions 映射到 `max_completion_tokens`，Responses 映射到 `max_output_tokens`。
- 模型适配器只提取实际 HTTP 响应中明确提供的输入/输出 token 整数，在成功模型证据及对应网络尝试中保存安全 `metadata.usage`。缺少字段是 `null`；明确报告的零保留为零。读取不把供应商 SDK 的历史默认零猜成真实报告。
- `/api/runs/{runId}/usage` 与 `/api/model-usage?date=YYYY-MM-DD&timezone=IANA` 只读既有证据。按逻辑模型调用 ID 去重，成功模型与其网络尝试中的同一 usage 只计一次；失败或未确认尝试的未报告消耗不估算。统计包含报告数值、完整用量/耗时覆盖数、成功/失败/未确认逻辑调用、网络尝试及按冻结资源/模型分组。
- 当地日以逻辑调用最早存储开始时间归属（含恢复前的网络尝试），使用 IANA 时区转换真实 UTC 日界线。跨日重试不会把同一逻辑调用重复归入两个日期。累计模型耗时使用逻辑开始至结束的时长，未结束或缺少时间保持未知；运行总耗时单独返回。
- 结果页和设置页的用量组件显示本次/今日用量、缺失覆盖和模型明细；专家属性编辑同一 YAML 中的可选上限，准备页显示关键模型预算。模式往返不产生新配置值，读失败提供重新读取操作。

本阶段没有新增表、价格目录、余额估计、主动探测或计费状态机；既有表仅保存新增的安全证据元数据。历史正数用量可从已确认响应/本地产物读取；不可取得或不能证明存在的计数按未知处理。

## 本地验证

以下为受控本地验证，供应商成功与配额状态仍由 M 验收单独证明。

- `tests/test_model_budget_contract.py`：省略上限与 `5a993684` 基线 hash 完全一致；显式上限改变新修订，旧 Run 冻结值保持；非法上限具有源位置；剩余总预算边界；两个真实本地 HTTP 适配请求的上限字段；明确零与未报告 usage 区分。
- `tests/test_model_usage.py`：逻辑调用/重复引用去重；重试与未确认尝试；失败/旧默认零/明确零/历史正数；本地产物读取；Helsinki 夏令时 23 小时日与午夜微秒边界；跨日重试归属；冻结模型分组；离线读取不解析凭据；API 错误与空范围。
- `tests/test_model_usage_runtime.py`：真实本地 Temporal、Worker 和模型 HTTP 完成两次逻辑调用，上限均为 12；输入/输出分别汇总 16/16。确认模型恢复不新增网络调用或 usage；受控截断回复使 Run 失败，未确认正文不提升为结果。
- 前端聚焦 `model-usage-panel.test.tsx`、`use-model-usage.test.tsx`、`package-expert.test.tsx` 共 13 项通过：未知与零、覆盖说明、模型明细、读失败重试、当地日界线、预算省略/编辑/清除与原 YAML 保真。
- Ruff、Black、isort 对本阶段 11 个后端源文件/测试通过；`uv run mypy app` 对当前 110 个文件通过。前端 `pnpm lint`、`pnpm typecheck` 与 `pnpm build` 通过。

共同后端回归命令已通过：

```bash
cd backend
uv run pytest tests/test_model_budget_contract.py tests/test_model_usage.py tests/test_model_usage_runtime.py tests/test_durable_runtime_budgets.py tests/test_durable_runtime_credentials.py tests/test_target_seeds.py tests/test_dag_compiler.py -q
```

结果为 **68 passed**，包含一条既有 Temporal sandbox 的 `annotated_types` 导入警告。最后 `git diff --check` 通过。

## 联合验收入口与保留项

`frontend/e2e/model-usage.spec.ts` 在独立测试库和受控模型中执行：专家上限保存及模式往返 → 新旧 Run 快照 → 实际模型 usage → 结果和今日用量 → 375/768/1024/1440 与键盘明细。文件已经交付，执行及截图需与其余 Sprint 的同版本联合 E2E 汇总；未执行不能记为通过。

M 验收由共同隔离真实模型场景完成：新 Run 显式配置输出上限、确认供应商请求与实际 usage、模型主动工具调用及自然定时路径。Chat 与 Responses 的受控请求验证不等于两个协议的真实供应商验收。当前文档不宣称 M 或上述联合 E2E 已完成。

## 最终共同验收追加

2026-09-10，本阶段列出的后续联合条件现已由[最终共同验收](personal-use-verification.md)关闭：最终Core一致的真实模型三条路径、677项后端、289项前端、24项全栈浏览器及实际双离线专项通过。原阶段数字保留其执行时点，不累加为最终数量；具体C1–C11、Run/fire/产物及清理证据以共同记录为准。
