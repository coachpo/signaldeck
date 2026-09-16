# 后端自动化测试消融结果（2026-09-16）

## 范围、版本与环境

评估固定初始版本 `7c4bcbcf87adce626fcf6fe7dc1ef23e98538a02` 的全部后端 pytest 范围：69 个 `test_*.py` 文件（其中 `test_durable_runtime_support.py` 为零节点共享支持模块）、532 个静态测试函数、877 个收集节点。逐文件合同/风险及保留决定见 `sd-backend-risk-inventory.md`；全部节点见 `sd-backend-collect.log`；函数位置、fixture参数、直接导入及断言数见 `sd-backend-inventory.json`。CI 的 `backend-quality` 实际执行整个 pytest 入口，其中同时包含纯单元、PostgreSQL、Temporal、独立插件进程、提供商合同和 Notes Chromium 浏览器测试。

最终交付工作树：`/Users/qingli/Documents/ChatGPT/signaldeck-test-ablation-20260916`。完整前后验证在固定初始版本的完整 `/tmp` 归档中按 full/reduced、reduced/full 两对顺序运行，每对连续执行；使用交付树独立安装的 Python 3.14.4 环境和声明锁定依赖。其余环境为 uv 0.11.7、PostgreSQL 16（真实数据库，每测试独立 UUID 库）、Temporal CLI 1.8.3 / Server 1.31.2、Node 24.17.0。CI 固定 Python 3.13.13，故本轮不构成 CI 解释器版本复验。

精简归档与最终交付树的 207 个 backend 源码、测试、版本及依赖文件逐字节一致，见 `sd-backend-delivery-source-manifest.json` 和 `sd-backend-validation-summary.json`。没有修改产品实现、公共 fixture、依赖、容差、快照或 skip 配置；没有提交或推送。外部并发工作新增的测试不属于上述固定初始范围，未据此扩展本轮结论。

## 已实施精简

| 位置 | 改法及保留合同 | 实验依据 | 限制 |
|---|---|---|---|
| `backend/tests/test_auth_middleware.py::test_api_runs_rejects_missing_bearer_token_with_and_without_origin` | 合并原 missing-token 与 CORS 两例；仍分别发送无 Origin、有 Origin 两个请求，保留全部 401、精确错误体和 CORS header 断言；只减少一次数据库 fixture 生命周期 | 授权绕过、401 envelope 损坏、CORS 来源移除均被完整组及联合精简组检出 | 首个请求失败会阻止同例后续请求，减少独立失败定位粒度 |
| `backend/tests/test_core_api.py` 的 removed-memory 404、ApiError envelope 两例 | 直接构造真实 `create_app(init_database=False)` 和 TestClient，去除这两个不读数据库的路由测试的数据库 fixture；真实 middleware/handler 仍执行 | 恢复旧路由、错误 code/status 损坏及密钥过滤失效均被双方检出 | 不主张这两个测试验证数据库初始化；实际 GET、405/Logfire、匹配 token、默认 token 等数据库边界仍保留 |

初始范围 877 → 876 个 pytest 节点、532 → 531 个静态测试函数；两文件组 10 → 9 例。按既有 function-scope fixture 依赖计算，该组真实数据库生命周期 8 → 5。其余后端测试均保留。

## 实验 E1：HTTP/认证联合精简

使用相同隔离源码、同一解释器和同一命令，对完整 10 例与联合精简 9 例分别注入同一个故障，逐次恢复原始源文件。命令为 `python -m pytest -q tests/test_core_api.py tests/test_auth_middleware.py --durations=10`。原始脚本中的准确 file/before/after/替换次数、源文件 SHA256、每次运行命令/日志/退出状态以及从日志提取的 FAILED nodeids，均保存在 `sd-backend-http-evidence.json`；不是按测试名称猜测重复。

| 实际故障 | 完整组 | 联合精简组 |
|---|---:|---:|
| 绕过 bearer 校验 | 3 failed / 7 passed | 2 failed / 7 passed |
| 401 错误 envelope 改成 Forbidden | 2 failed / 8 passed | 2 failed / 7 passed |
| 移除允许的 CORS origin | 1 failed / 9 passed | 1 failed / 8 passed |
| API 错误 code 改错 | 1 failed / 9 passed | 1 failed / 8 passed |
| API 错误 status 改成 200 | 1 failed / 9 passed | 1 failed / 8 passed |
| 禁用敏感 detail key 过滤 | 2 failed / 8 passed | 2 failed / 7 passed |
| 恢复已删除的 memory 路由 | 1 failed / 9 passed | 1 failed / 8 passed |

七个可观察合同故障均为双方 7/7 检出。另一个样本仅删除 handler 的第二次清洗，完整/精简组均通过：ApiError 构造器已清洗输入，该样本没有制造可观察泄漏，**不能据此认定覆盖缺口，也不计入故障检出率**。这不证明第二层防御无价值；两个层次的现有断言均保留。

## 实验 E2：冻结效果参数消融，拒绝删除

`test_effect_projection.py` 完整组 14 例；临时候选删除 missing effect 和 conflicting effect 参数后为 12 例。无故障时双方通过。同一命令 `python -m pytest -q tests/test_effect_projection.py`，同样源码替换分别用于双方。准确替换 spec、FAILED 节点和运行记录见 `sd-backend-effect-evidence.json`。

| 故障 | 完整 14 例 | 候选 12 例 | 判断 |
|---|---|---|---|
| 缺失 effect 默认 read | 2 failed / 12 passed | 1 failed / 11 passed | agent-level 保留用例检出该广泛替换；不等于 tool 分支的契约可删 |
| 冲突声明只取第一项 read | 1 failed / 13 passed | 12 passed | 被删冲突参数在本组对该故障具有独有检出能力，联合删除会形成盲区 |
| 缺失 tool 合同默认 read | 1 failed / 13 passed | 1 failed / 11 passed | 保留的 missing-tool 用例仍检出 |

因此全部 14 例原样保留。缺失工具、缺失字段、冻结声明冲突是不同边界，即使经过同一表达式也不能视为重复。该组完整样本检出 3/3，候选仅 2/3；没有把不合格候选实施到交付树。

## 计时与验证

完整全量前后使用相同目录、同一独立 Python 环境及相同命令：

```text
TEST_DATABASE_URL=postgresql+psycopg://signaldeck:signaldeck@127.0.0.1:25432/signaldeck \
/Users/qingli/Documents/ChatGPT/signaldeck-test-ablation-20260916/backend/.venv/bin/python \
-m pytest -q --durations=30 --junitxml=/tmp/sd-backend-frozen-current.xml
```

| 测量 | 原版 | 精简版 | 测量次数/含义 |
|---|---:|---:|---|
| 全量 pytest 中位 | 877 项每次均通过；277.115s（269.02–285.21） | 876 项每次均通过；269.925s（269.09–270.76） | 各 2 次完整通过；两对顺序相反 |
| 全量进程 wall 中位 | 280.977s（271.951–290.003） | 273.053s（272.344–273.763） | 各 2 次；不是稳定收益估计 |
| HTTP 局部 pytest 中位 | 1.76s（1.74–1.92） | 1.39s（1.35–1.39） | 各 3 次，顺序 full/reduced/reduced/full/full/reduced |
| HTTP 局部进程 wall 中位 | 3.915s（3.665–3.950） | 3.319s（3.249–3.334） | 同上；该局部约减少 0.596s |

第一对 full/reduced 为 285.21/270.76s；反向第二对 reduced/full 为 269.09/269.02s，第二对精简版并未更快。**这些观测不能证明后端全量稳定提速**，不能把第一对 14.45s 差额或两次中位差额当作精简收益。第一对 JUnit 中受影响 HTTP 组实际合计 1.719 → 1.292s；未修改的 worker SIGKILL 测试自身变化 3.476s，deadline classification 自身变化 3.387s。局部组已交错重复 3 对，明确收益证据仅限该局部。

四份完整 JUnit 为 `sd-backend-frozen-full.xml`、`sd-backend-frozen-reduced.xml`、`sd-backend-frozen-r2-reduced.xml`、`sd-backend-frozen-r2-full.xml`。两对原始结果分别见 `sd-backend-frozen-results.json`、`sd-backend-frozen-round2-results.json`；合并测量/代表值见 `sd-backend-full-timing-repeated.json`，综合验证见 `sd-backend-validation-summary.json`，第一对时间来源分析见 `sd-backend-junit-timing-analysis.json`。

`sd-backend-four-run-node-outcomes.json` 记录四轮所有节点和结果：两轮原版各自为同一 877 节点，与最初 collect 清单逐项一致；两轮精简版各自为同一 876 节点。两版本集合差异仅为原 missing-token、CORS 两个节点替换成联合测试节点；其余节点均保留。四轮没有失败、错误或跳过。交付树 207 个 backend 文件在追加测量前后仍与第一轮交付 manifest 一致，见 `sd-backend-round2-source-proof.json`。

四轮全量均无失败。原版两轮分别为 3/2 warnings、精简版两轮均为 2 warnings，为已有 Temporal annotated_types 延迟导入警告及故意 fraction-token 输入引起的 Pydantic 序列化警告；没有屏蔽警告。此前受污染轮的所有五个失败对应测试在两轮冻结原版和两轮精简版均通过。

交付工作树实际门禁均通过：`uv run ruff check app tests`；`uv run black --check app tests`（185 files）；`uv run isort --check-only app tests`；`uv run mypy app`（112 source files）；`uv run pytest -q tests/test_core_api.py tests/test_auth_middleware.py`（9 passed, 1.85s）；`git diff --check`。原始结果见 `sd-backend-gate-*.log`，门禁清单见 `sd-backend-gates.json`。

## 受污染诊断轮、未完成范围与清理

早期共享工作区全量在并发外部源码修改和高负载下被正常 SIGINT 中止，记录为 **527 passed、5 failed、3 warnings、644.27s，exit 2**，不是完整基线，不用于任何精简收益比较。其中两例现场观察到外部 Notes 版本已由 1.2.0 改为 1.3.0；另三例为 durable 时间/调用次数断言。对应日志、外部进程记录和源 SHA 漂移证据均保留。冻结前后完整通过消除了本次重现中的这些失败；不把它们改称无价值测试或已确认产品缺陷。

所有初始测试均已盘点并按合同/风险分组评估，但只有上述 HTTP 组和效果投影参数组完成实际消融。其余组未取得可删除的故障/契约证据，因此保留，不声称其已完成消融。没有按行覆盖或名称认定重复；backend 无既有配置的覆盖率/变异测试能力，未添加基础设施，无法给出行覆盖率变化。真实服务、生产运行和完整 UI/UX 体验不在这些受控自动化结论内。

全部故障注入仅发生于临时源码副本。原故障副本逐 app 文件核对为恢复的初始源码后删除，见 `sd-backend-mutation-cleanup.json`；冻结验证副本、临时执行脚本及候选副本也已在证据保存后删除。最终交付树只有经验证的两个后端测试文件变更；在本次七个 HTTP 故障样本下保留了相应检出能力，不能推论绝对等价或不存在回归风险。
