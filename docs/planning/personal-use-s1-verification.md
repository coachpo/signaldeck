# PU-S1 连接、正文与诊断验证记录

2026-09-10；基线 `5a993684eb35f655d46cffbec2c0a3f73c55fd4e`，交付为当前未提交工作区。范围为[个人使用优化 Sprint Backlog](personal-use-sprint-backlog.md)的 PU-S1，未启动 PU-S2–S6。STATUS.md 的 MVP、个人私用及历史状态保持不变。

## 交付

- `pu-connect-feedback`：连接预设加载、失败、无候选、待选择、已选择分别反馈；保留显式范围确认、业务输入和凭据清空。
- `pu-markdown`：共用 MarkdownContent 覆盖声明正文、历史正文、文本附件及已有 Markdown 检查器；标题、OL/UL、表格、代码、链接采用同一排版。JSON 附件保持字面值。
- `pu-model-diagnostics`：白名单 HTTP 错误类别；模型最近实际尝试按资源 ID、冻结配置与凭据修订摘要匹配。离线只读，不新增表、不改写旧证据、不保存供应商错误正文。
- `pu-diagnostic-ui`：任务准备、已连接服务、结果失败和无 Run 的 fire 失败显示可执行的处理方向；原错误码可展开，最近调用链接到准确证据。配置就绪不等于在线。
- `pu-s1-verify`：聚焦检查、跨栈回归、四宽度检查与真实模型验证分别记录如下。

产品行为、结构与证据字段分别同步到[产品说明](../产品说明.md)、[架构说明](../架构说明.md)、[数据模型](../data-model.md)；排版同步到[DESIGN](../../frontend/DESIGN.md)。没有更改 Workflow Package schema、现有数据库结构或示例包。

## 本地回归

| 检查 | 结果 |
| --- | --- |
| `uv run pytest tests/test_model_diagnostics.py tests/test_task_experience.py -q` | 33 passed；最终失败节点关联收紧后另复验诊断14项通过 |
| Temporal 真实执行的预算与deadline聚焦回归 | 3 passed |
| Backend Ruff、Black、isort、mypy | 通过；mypy覆盖95文件 |
| Frontend lint、typecheck/build、Vitest | 通过；53个文件、248项Vitest测试通过 |
| Playwright tasks/resources/scheduled-tasks | 5项通过：首轮4项通过，剩余fire错误码改为显式展开后聚焦复验1项通过 |
| 四宽度与键盘 | 375/768/1024/1440任务表单、准备、结果截图；OL/UL标记、长表格/代码、页面无横向溢出及链接键盘焦点通过 |
| 差异与职责 | `git diff --check`通过；model_runtime、platform_store、result_projection超过300行，职责分别为模型I/O、配置安全读写、结果读取投影，保持既有依赖边界 |

跨栈回归使用隔离 PostgreSQL、Temporal、固定 Core Worker、独立 Notes/Finance/Oracle 插件和受控模型；不能据此宣称外部供应商可用。首轮发现并修复新增模块循环导入；失败结果投影按 DAG 失败节点的实际错误匹配，不以总体 `workflow_nodes_failed` 代替模型原因。旧通用 HTTP 错误不会被猜测为额度错误。

机器与截图附件位于本机忽略目录 `output/playwright/task-experience/`、`output/playwright/personal-use-s1/`；新检出可通过上述检查及 Backlog 前置条件复现，不依赖这些附件存在。

## 真实模型

用户指定 `glm-5.3-flash`，使用同一授权 provider 的真实接口。最终两条成功路径绑定同一 Core：`sha256:33e4f70b1bd43964861ccf5b06e6071e578557901e70eb24c122333e11d91f0e`。

| 路径 | 真实结果 |
| --- | --- |
| 原内置 `research_notes/research`，未修改示例预算或定义 | Run `6f23b2ff-b93c-4d68-9c8a-36e5b114d4a4` succeeded，原输入保真、正文及Notes保存均确认 |
| 独立验证包，模型主动调用 Notes search 后生成并保存结果 | Run `e154b8fc-06de-4146-8587-7ae91f8e3596` succeeded，edit节点的模型主动工具调用确认，最终输出通过闭合schema |
| 最近模型观察 | 资源与prepare一致，包含本次成功时间及精确attempt证据；更换配置后先恢复not_observed |
| 真实页面 | 上述内置结果和普通设置在四档宽度无横向溢出，清单标记可见，调用证据链接可键盘访问 |

早期 `deepseek-v4-flash` 返回额度不足，其结果、资源与prepare正确显示quota。换模型后的一个验证包回复含额外字段，被原有闭合输出校验拒绝为 `agent_output_invalid`；模型调用成功未被误记为整个Run成功。只调整该验证包的prompt后重新执行，未放松schema或修改产品代码。

最终证据为 `output/playwright/personal-use-s1/real-validation.json`。此前Core版本的额度失败及luna调用保存在 `real-validation-before-final-core.json`，仅证明相应历史请求，不代替最终glm成功证据。真实模型主动工具路径采用独立验证包的8000总token/3次请求上限，不更改内置包，也不构成Sprint 3的单次输出上限功能。

PU-S1 的 pu-a01/02/03及本阶段pu-a11已通过。自然定时成功仍属于后续PU-S4/最终共同验收，不因本阶段完成而提前关闭。

## 边界

本次不提交、不推送、不部署，不处置用户原实例数据。真实模型凭据只从用户授权配置读取，经资源写入接口保存到自有隔离实例；不写入仓库或证据。所有自有验证服务与临时数据库在验证结束后清理。
