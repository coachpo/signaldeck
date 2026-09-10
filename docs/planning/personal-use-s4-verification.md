# PU-S4 个人结果整理与执行更新验证记录

2026-09-10；交付为当前未提交工作区，对应[个人使用优化 Sprint Backlog](personal-use-sprint-backlog.md)的 PU-S4。此文件记录阶段实现与验证；自然定时真实成功、关闭浏览器后再打开及跨 Sprint 联合验收由共同验收记录补充，不以单元测试代替。

## 已实现范围

- `pu-result-metadata`：独立附属表保存收藏、结果已读和个人备注。旧 Run 读取为 revision 0、未收藏、未读、空备注；GET 不创建附属记录。PATCH 携带 `expectedRevision`，只更新明确提供的字段，空备注表示删除备注；省略字段保持原值，显式 null/未知字段拒绝。并发首写串行化，旧版本返回 409；不改 Run/spec/output 或启动命令。
- `pu-result-organizer`：结果页显式收藏、已读和备注编辑；列表显示个人标记，支持收藏、阅读状态的数据库级过滤及就地标记。写操作保留查询、页码、时间上界；更改筛选时仍按原规则回第一页。备注冲突保留草稿，并显示最新保存值，核对后才允许基于新版本保存。
- `pu-attention-inbox`：`/attention` 只投影持久执行事实，包括当前完成/失败/取消、逻辑 unknown 的 Run，以及没有 Run 的 fire 启动失败。第一次打开纳入所有既有当前记录，不新增观察写入、调度或执行恢复。结果标为已读时，在同一附属事务内确认当时观察到的更新身份；后续变化仍产生新更新。更新页的“已查看本次更新”只确认该次变化；已查看的 unknown 仍出现在待核实范围。

注册与持久化由现有 `create_all` 创建 `platform_result_metadata`、`platform_attention_receipts` 两张新表，不修改现有表、不转换旧数据。API 为 `GET/PATCH /api/runs/{runId}/metadata` 和 `GET/PATCH /api/attention[/{identity}]`；历史接口新增 `isFavorite`、`isRead` 查询参数。权威产品行为与数据表合同由[产品说明](../产品说明.md)及[数据模型](../data-model.md)维护。

## 更新身份与读取边界

Run 更新身份包含 Run ID、当前终态、完成时间及非 attempt 证据的逻辑身份/状态/错误码；同一 unknown 的重复观察时间不改变身份。unknown 变为确认结果时，即使 Run ID 和终态不变也得到新身份。已恢复网络 attempt 的 unknown 不冒充未解决逻辑效果。

fire 更新身份由 trigger、固定 engine workflow/execution、状态及错误码组成；重复投影的更新时间不产生新身份。确认收据独立保存，进程重启后仍去重。旧状态已经变化的收据 PATCH 返回 409，不能把新状态静默标为已查看。

列表先对全量当前符合条件的持久事实做过滤、排序和计数，再分页，不截断最近 50 条后筛选。`snapshotAt` 是当前状态发生时间的上界，晚于上界的新状态不进入原查询；它不是历史事件快照，正在变化的记录可退出当前页，刷新会重新纳入。此入口保留当前更新，不声称重建从未保存的历史状态序列。

模型失败类别共用 S1 的安全失败节点关联投影；DAG 总体错误可展示实际失败模型的额度等类别，类别不明确或历史字段畸形时不猜测，不读取供应商原始错误正文。

## 阶段验证

| 检查 | 实际结果 |
| --- | --- |
| `uv run pytest -q tests/test_result_organizer.py` | 7 passed：精确 PATCH/冲突/重启、全库筛选分页、unknown 已查看后核实的新身份、无 Run fire、无副作用读取、发生时间上界/安全 DAG 类别、并发首写、排除网络 attempt unknown |
| `tests/test_model_diagnostics.py tests/test_task_experience.py tests/test_result_organizer.py` 初次组合 | 37 passed，1 项在创建隔离数据库时遇到 PostgreSQL 连接关闭；该项随后单独复跑通过，未修改测试或产品逻辑规避 |
| `pnpm exec vitest run src/pages/platform/result-metadata.test.tsx src/pages/platform/attention.test.tsx src/pages/platform/result-history.test.tsx src/pages/platform/result-view.test.tsx` | 4 文件、18 项通过：精确写入、备注冲突草稿、unknown 可操作、fire导航、任务筛选、页码和查询保留、原结果阅读回归 |
| 聚焦 Ruff、Black、isort、mypy | 通过；mypy 覆盖新增及受影响 7 个源文件 |
| 聚焦 ESLint、TypeScript | 通过；最终全项目门禁与跨栈覆盖由共同验证汇总 |

浏览器真实操作、四宽度与键盘、自然定时成功、重启和双离线结果阅读等证据需要与最终集成版本核对后记录。当前阶段测试没有调用真实模型、没有发送外部通知、没有提交或部署，也没有操作用户原实例数据。

## 最终共同验收追加

2026-09-10，本阶段列出的后续联合条件现已由[最终共同验收](personal-use-verification.md)关闭：最终Core一致的真实模型三条路径、677项后端、289项前端、24项全栈浏览器及实际双离线专项通过。原阶段数字保留其执行时点，不累加为最终数量；具体C1–C11、Run/fire/产物及清理证据以共同记录为准。
