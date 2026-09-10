# PU-S5 结果比较实现与验证记录

日期：2026-09-10。对应 `pu-result-compare` / `pu-a09`；本文件仅记录比较子项，草稿及完整 PU-S5 验收另行汇总。当前对象为未提交工作区。

## 已交付实现

- `/runs/compare` 接收两个固定运行 ID（`left`、`right`）和显式内容选择（`leftSection`、`rightSection`）。结果页提供带入当前 ID 的入口；可填写 ID，或按服务端搜索、分页和 `snapshotAt` 从结果记录中选取两边，固定后写入 URL。
- 两侧使用现有 `useRunResult` / `useTaskReuse`，呈现运行状态、确认内容状态、来源、创建/完成/数据时间、冻结包修订及输入摘要，完整输入和来源记录可展开。unknown 和取消不被当作确认全部成功，尚在运行的结果标明可能继续更新。
- 确认内容来自与 S2 共用的 `result-delivery.ts`。普通结构化输出按 JSON 阅读；无确认内容明示；附件即使已在 URL 中选定仍须显式点击读取，不自动拉取全文。
- `result-diff.ts` 按行确定性比较，保留两侧原始文本与末尾换行。LCS 表限制为 250000 单元；更长变更区域按完整删除/新增块显示并明确说明，不静默截断原文，不作模型摘要或业务变化判断。
- 相同正文仍显示各自运行、修订、输入和状态。比较仅消费 Core 确认读取，不调用模型、不写入原运行。

## 已执行检查

```sh
cd frontend
pnpm exec vitest run src/pages/platform/result-compare.test.tsx
pnpm exec eslint src/pages/platform/result-compare.tsx src/pages/platform/result-compare.test.tsx
pnpm typecheck
```

比较组件 4 项通过，聚焦 ESLint 与类型检查通过。另有 `result-diff.test.ts` 6 项在 S2 联合检查中通过，覆盖空内容、相同文本、重复行、末尾换行和大区域退化比较；每例重建左右输入核对没有丢失原文。

组件回归覆盖固定两个 ID、相同文本/不同修订和输入、unknown/取消、URL 分节选择、附件显式读取、任意字段保持 JSON，以及从真实接口合同的服务端结果记录选取运行。

## 未在本子任务宣告完成的条件

根任务负责最终路由/壳集成、四宽度与键盘、历史样本、插件离线比较及跨 Sprint E2E。上述组件固定数据不等于真实双离线或真实模型验收。S5 草稿恢复与比较属于不同交付，不能因比较已实现关闭整项 Sprint。

## 最终共同验收追加

2026-09-10，本阶段列出的后续联合条件现已由[最终共同验收](personal-use-verification.md)关闭：最终Core一致的真实模型三条路径、677项后端、289项前端、24项全栈浏览器及实际双离线专项通过。原阶段数字保留其执行时点，不累加为最终数量；具体C1–C11、Run/fire/产物及清理证据以共同记录为准。
