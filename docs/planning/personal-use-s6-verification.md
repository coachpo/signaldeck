# PU-S6 Notes 阶段验证

2026-09-10，Notes API、独立页面与冻结链接实现完成；本记录仅覆盖 `pu-notes-read-api`、`pu-notes-page`、`pu-notes-links` 的插件/声明边界。六 Sprint 同版共同验收仍由 `pu-s6-verify` 汇总，本阶段不宣称全部共同场景完成。

## 实现与公开入口

Notes 1.1.0 自行分发轻量 HTML/CSS/JavaScript，提供集合、字面搜索、按不可变标识排序的 cursor 分页、详情及复制。API/分页可见性/部署访问边界见 [Notes HTTP 合同](../../plugins/notes/README.md)。数据库结构及 MCP 写入、去重和集合授权保持原合同。

`create` 发布 `pageUrl` 与 `resultLink/1` 的 `note` 链接，`research_notes` 的两个 Workflow 使用公开 presentation 声明；示例合同已重新生成。特殊 ID 放在 query 参数中编码，不拼入路径。旧 Run 使用冻结发布且不从新目录补链。未改 Core 的业务分发、结果字段推断或路由。

## 验证结果

- `uv run pytest tests/test_notes_workspace.py tests/test_independent_plugins.py tests/test_result_declarations.py -q`：38 passed。实际隔离 PostgreSQL、HTTP 与 MCP；46 条只读 API 样例覆盖三页、字面 `%_\\`、集合边界、长 Unicode/URL 特殊 operation 标识、未知 ID、限额及拒绝删除；读前后 Notes 和操作记录数不变。
- `uv run pytest tests/test_target_seeds.py tests/test_dag_compiler.py tests/test_demo_presentation.py -q`：50 passed，覆盖外部普通导入、示例计划和数据合同。首次合并运行曾出现 PostgreSQL 临时库文件 permission 错误，其余 59 项通过；单独重跑全部相关示例检查通过，没有通过改断言或修改数据库权限隐藏错误。
- 冻结投影使用实际 Notes descriptor；对目录 pageUrl 修改后，已有 Run 链接保持原值；旧无链接 descriptor 仍有正文且不补链。已有通用合同覆盖确认 operation、离线 projection 和业务字段重命名。
- 实际独立 Notes MCP 进程向独立临时库写入25条笔记，Playwright CLI 完成 `%_` 搜索、第二页、特殊标识详情、复制、返回保留查询/页码、未知 ID、空结果和受控 HTTP 503 提示。375/768/1024/1440 四宽度截图均已生成，列表宽度断言无横向溢出，375px 详情已视觉检查，正文中的 `<script>` 作为纯文字显示。
- 截图：[375px 详情](../../output/playwright/personal-use-s6/detail-375.png)、[1440px 列表](../../output/playwright/personal-use-s6/list-1440.png)，同目录包含其他六张截图。浏览器证据使用实际 MCP 写入内容，不冒充真实模型研究。

本阶段临时 Notes 进程、浏览器和 UUID 临时库均已清理。无真实模型或付费 provider 调用。

## 共同验收边界

仍需同一最终 Core/Notes 发布上的 capture/research Run 链接与 operation 对照、真实模型主动工具、自然定时成功/失败、Notes 离线后的 Core 正文/导出/个人标记以及其他 Sprint 的组合路径；插件单元/浏览器验证不替代这些跨栈结果。根 Compose 和 E2E 启动器须提供实际 browser 可达的 `PLUGIN_PAGE_URL`。

## 最终共同验收追加

2026-09-10，本阶段列出的后续联合条件现已由[最终共同验收](personal-use-verification.md)关闭：最终Core一致的真实模型三条路径、677项后端、289项前端、24项全栈浏览器及实际双离线专项通过。原阶段数字保留其执行时点，不累加为最终数量；具体C1–C11、Run/fire/产物及清理证据以共同记录为准。
