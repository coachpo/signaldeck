# PU-S2 本地实现与验证记录

日期：2026-09-10。对应 `pu-result-disclosure`、`pu-result-export`、`pu-s2-verify`；范围以[实施计划](personal-use-implementation-plan.md)和[Sprint Backlog](personal-use-sprint-backlog.md)为准。当前记录针对未提交工作区，不代表已部署或全部真实环境验收完成。

## 已交付实现

- 任务准备默认展示连接名称、显式 `scope` 全部字段、绑定变化、真实模型观察和模型预算；技术配置、完整有效设置可展开，未知业务范围字段不隐藏、不翻译为业务别名。
- 结果页保留状态、unknown、取消请求、缺失和执行问题。声明回执和完整输入默认折叠，专家模式可展开；原值组件始终挂载。声明来源已经展示时不重复呈现同一投影的兼容来源列表。Finance 冻结链接与附件原下载保持。
- `result-delivery.ts` 是导出与比较共享的确认内容选择实现：按服务器冻结的 `sections` 顺序消费，只有没有分节时才回退到历史 `body` / `receipt`。结构化值保留 JSON，不从模型 attempt 或业务键猜测正文。
- `ResultExport` 默认选入内联确认内容。每个可读附件须显式选择后才通过已有 Core artifact 接口读取；读取失败可重试，已选未读取完成时不能复制或下载。不支持的二进制格式保留原下载。
- Markdown 文件包括所选内容、运行身份、状态、时间、来源、取消/unknown/部分结果/缺失信息、证据和所选产物身份。未选内容及延后解析声明明确列出；不将只导出内联内容冒充包含全部附件，也不推测大 JSON 中延后的声明字段。
- 剪贴板与下载失败均有可恢复提示；无确认内容时不生成空白成品，只有结构化内容时明确说明无 Markdown 正文。
- 已嵌入 S3 模型用量/预算和 S4 个人标记组件；相应数据合同与专项验证由各自任务维护。

## 已执行检查

在 `frontend/` 执行：

```sh
pnpm exec vitest run src/pages/platform/result-delivery.test.ts src/pages/platform/result-diff.test.ts src/pages/platform/result-export.test.tsx src/pages/platform/result-compare.test.tsx src/pages/platform/result-view.test.tsx src/pages/platform/task-preparation.test.tsx src/pages/platform/result-content.test.tsx
pnpm typecheck
```

最后一次整组检查为 7 文件 42 项通过（包含已有服务端历史选择，见[比较验证](personal-use-compare-verification.md)）。本任务新增/修改文件的聚焦 ESLint 通过。最终整组门禁由 Sprint 集成统一执行，不累计不同版本的检查数量。

回归覆盖声明优先与历史回退、任意 JSON 字段、部分/unknown/取消状态、来源与数据时间缺省、未读附件禁止导出、显式读取/失败重试、长代码围栏原值保留、无正文、复制失败与恢复、下载失败与可重试、Markdown 文件生成、普通回执/输入披露、scope 与绑定变化可见。

## 集成验收边界

L/H 真实运行、插件与执行引擎双离线后的复制/导出、Finance 既有下载、375/768/1024/1440 与键盘操作、真实下载内容和冻结输出对照由根任务执行并补证据。组件检查使用固定样本，不能替代这些验收；本记录不把尚未执行的离线或浏览器条件标为完成。

## 最终共同验收追加

2026-09-10，本阶段列出的后续联合条件现已由[最终共同验收](personal-use-verification.md)关闭：最终Core一致的真实模型三条路径、677项后端、289项前端、24项全栈浏览器及实际双离线专项通过。原阶段数字保留其执行时点，不累加为最终数量；具体C1–C11、Run/fire/产物及清理证据以共同记录为准。
