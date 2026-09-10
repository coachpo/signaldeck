# PU-S5 阶段验证记录

## 草稿合同与恢复 UI（pu-draft-contract / pu-draft-ui）

本轮新增 `platform_task_drafts` 独立表、闭合 `TaskDraftWrite/Read` 合同、`/api/task-drafts` 查询与带乐观 revision 的 PUT/DELETE。读取使用已存不可变包修订，无执行引擎或插件调用。原有 PU-S1 未提交成果保留；本阶段证据不是 S1 历史通过数。

任务首页展示已保存草稿，`/tasks/new?draftId=...` 显式恢复；保留参数原值、缺失标识与未应用 JSON 原文，非法 JSON 可保存但不能启动。草稿独立于常用配置/收藏。编辑显示未保存提示；修订冲突可明确放弃本页修改恢复服务器版本。原包 schema 随草稿恢复，当前 hash 漂移显示提示，不物化默认值。来源 Run 保存时核对包/Workflow/hash。

所有普通任务提交前先持久化 pending、launchId 与已审阅 bindingToken，获得保存回执后先将当前 URL replace 为 `?draftId=...` 再发送启动；保存失败不会发送启动。网络响应不确定时恢复同一身份并禁用输入、名称和删除；成功回执清理草稿，清理失败保留安全的同身份记录。确定拒绝后清除 pending 并重新核对。上述行为的前端确定性回归断言发送前已存 pending、模拟丢响应后卸载旧页面并从实际导航后的 URL 及 API 恢复新编辑器、两次 launch 参数及身份完全一致。

### 已执行检查

- `cd backend && uv run pytest tests/test_task_drafts.py tests/test_task_presets.py -q`：13 passed。覆盖 null、缺失、空字符串、对象、数组、非法 JSON；旧 revision 与同内容重试、pending 输入不可变、schema 漂移、凭据拒绝与无 Run 副作用。
- `cd frontend && pnpm exec vitest run src/pages/platform/tasks.test.tsx src/pages/platform/launch-inputs.test.tsx`：24 passed。包括新增丢响应恢复、持久化失败不提交、非法文本恢复与原修订保存。
- `cd frontend && pnpm exec vitest run src/pages/platform/tasks.test.tsx src/pages/platform/launch-inputs.test.tsx src/pages/platform/task-inputs.test.tsx`：最终为 31 passed。
- 草稿后端模块 ruff、black、isort、mypy 通过；受影响前端 eslint 与 `pnpm typecheck` 通过。

### 联合验收待补

本记录当前仅声明草稿阶段的局部证据；PU-S5 的比较路径 pu-a09、跨栈浏览器刷新/多窗口/真实启动和截图，以及最终同版本门禁由共同验收补全。没有提交、部署或修改原实例数据。新表通过 `create_all` 注册；无旧表升级或迁移步骤。

## 最终共同验收追加

2026-09-10，本阶段列出的后续联合条件现已由[最终共同验收](personal-use-verification.md)关闭：最终Core一致的真实模型三条路径、677项后端、289项前端、24项全栈浏览器及实际双离线专项通过。原阶段数字保留其执行时点，不累加为最终数量；具体C1–C11、Run/fire/产物及清理证据以共同记录为准。
