# 简化操作 Sprint 独立验收

## 验收范围与版本

本记录对照 [Sprint 清单](sprint-backlog.md) 的全部 23 个稳定任务 ID，以及 GOAL `sd-ux-all-sprints` 的 C1–C8。验收基线是 `05a61151fb6239c0d222630c3e7c722e8c88c5a8` 加简化操作实现与本轮修复；依赖升级已在该提交内，不重复应用。[原实现交付记录](sprint-delivery.md) 保留实现阶段的来源与结果，不替代独立验收。

2026-09-08，用户在「0908｜FEA｜简化操作六个 Sprint 实现」明确调整 C8 为“由你自行安排 Playwright 测试，无需人员参与”。本轮读取该会话原答复后采用此调整，其余范围与必需条件保持。自动化体验测试不等于真实参与者观察，也不证明真实外部供应商可用性。

## 本轮确认并修复的问题

| 问题 | 修复与回归入口 |
| --- | --- |
| 准备摘要与绑定 token 两次读取之间变更，可能展示 A 却执行 B | 准备阶段共享同一资源/插件快照，启动仍核对 token；`backend/tests/test_task_experience.py` 确定性竞态回归 |
| 计划首次保存后响应丢失，同身份重试被后来变化的包/schema阻断 | 已持久化身份先恢复，并保留请求冲突检查；同文件 API 重试回归 |
| 历史显式 null 被默认值覆盖，非对象常用配置保存失败 | 保真所有 JSON 根，通过 `hasParameters` 区分有效 null 与仅收藏；任务组件和实际 PostgreSQL 预设回归 |
| 未确认 rerun 在访问证据后返回时生成新身份 | 按当前 QueryClient 与来源 Run 保留未确认身份/绑定；`frontend/src/pages/platform/result-view.test.tsx` 导航重试回归 |
| Finance 写请求等待期间继续编辑或切换对象会丢草稿 | 写请求期间禁用冲突操作，成功/失败后恢复；`plugins/finance/tests/browser.mjs` 实际延迟响应回归 |
| 普通启动强制先核对再开始，与方案的一次开始不符 | 有效输入自动准备，一次开始提交；缺连接与绑定变化仍受保护，组件及四场景 E2E验证 |
| 自动准备新增查询键不符合现有资源分组约定 | 将准备查询归入 workflowPackages 分组，保持现有 query-keys 回归与失效范围 |

以上问题已由失败回归确认、修复并复验。修复后的完整闭环验收通过：23/23 必需用例和综合完成检查均通过，无豁免项。

## 最终独立验收结果

| 检查 | 结果 |
| --- | --- |
| 后端完整 pytest | 547 passed，1 warning；无失败或跳过 |
| 前端完整 Vitest | 218 passed；无失败或跳过 |
| Core Playwright E2E | 19 passed；无失败、flaky 或跳过 |
| 实际插件与 Temporal 双离线专项 | 1 passed |
| 独立 Finance pytest/HTTP/Chromium | 4 passed，包含延迟写入与失败解锁 |
| 后端及 Finance Ruff/Black/isort、后端 Mypy | 全部通过 |
| 前端 lint/typecheck/build、Compose 配置检查 | 全部通过 |
| 文档链接、23 任务映射、A01–A18 保持、差异检查 | 通过；验收记录收口后补查文档 |
| 四档宽度 | 375/768/1024/1440px 的原生浏览器检查及界面证据通过 |

四场景使用相同 Core 制品 `sha256:801101b2d7c16850e88ab8b406f8930e9a834924acf0a75e2a30f7adcea1b2a4`，实际运行如下。保存原文没有模型调用；所有业务端点均为本轮隔离环境。

| 场景 | 实际 Run | 终态 |
| --- | --- | --- |
| 保存原文 | `56b61bd8-5cb0-489f-8234-a5ee97fd25c6` | succeeded |
| 整理笔记 | `176ff41d-ecf9-4e58-bf56-341bd733397b` | succeeded |
| 市场研究 | `ebf70c9e-fe99-48e9-98f7-a8c52e0f7987` | succeeded |
| 综合资料研究 | `d414a971-ad60-43c3-8585-ae52ffed7c23` | succeeded |

检查通过后只补充本验收记录、STATUS 和原交付记录的结论入口，未改变已测试代码。超过 300 行的保留文件已按职责检查：平台存储、E2E 启动器、Layout、Sidebar、计划表单、任务启动表单、Finance 报告服务均维持各自模块职责，无未通过项。

## 验证方式与证据保存

独立验证使用与工作区源码逐文件一致的隔离副本、真实 PostgreSQL/Temporal、dispatcher、固定制品 worker、独立 Finance/Notes/Oracle 插件与受控 provider。复用项目原生 pytest、Vitest、Playwright 与静态检查；同一源码版本的共享套件只运行一次，各任务绑定其适用测试和实际产物。所有 GOAL 用例仍为必需项。

本机详细闭环结果与用例附件位于 `.steward/goals/sd-ux-all-sprints/verification/`，简要本机报告位于该目录的 `report.md`。这些目录以及原实现的 `output/playwright/` 均不进入 Git；新检出不包含本机日志和截图。本文件保留可随提交获取的范围、修复、原生命令及最终结论索引。

原生复现入口与环境前提见 [贡献指南](../../CONTRIBUTING.md)：后端 `ruff check app tests`、`black --check app tests`、`isort --check-only app tests`、`mypy app`、`pytest`；前端 `pnpm lint`、`pnpm typecheck`、`pnpm test:run`、`pnpm build`、`pnpm exec playwright test`；另运行 `pnpm exec playwright test --config playwright.fault.config.ts` 及 `PYTHONPATH=plugins/finance:plugins/runtime <Python 3.13.13 环境>/bin/python -m pytest plugins/finance/tests/test_finance_ux.py -q -s`。数据库必须是具备临时建库权限的隔离测试实例，不能使用现有业务数据库作为可丢弃数据。
