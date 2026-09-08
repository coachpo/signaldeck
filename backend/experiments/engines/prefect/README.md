# Prefect 候选集成探针

范围是冻结 `bca05dcd666e96561426224b89b0e06aed186a22` 的 T06 / A16 同场景候选比较。
这组实验使用真实 Prefect server、Runner、engine task 和 Pydantic AI；模型为本地 fake model，
插件为实际 Python 子进程。它不是 SignalDeck 平台 A01–A18 的整体验收。

## 固定环境与复现

Python 3.13.13、Prefect 3.8.5、Pydantic AI slim 2.40.0、Pydantic 2.13.5、
FastAPI 0.136.3。完整 111 项依赖在 `requirements.lock` 固定；没有修改 backend 共享依赖。
Prefect 3.8.5 通过官方 PyPI 元数据核实，发布日期为 2026-09-03。

从仓库根目录执行：

```bash
backend/experiments/engines/prefect/run.sh
```

脚本使用 uv 创建独立 Python 3.13 环境，在临时目录保存 SQLite server、原生 task result cache、
内容地址制品和日志；默认监听 `127.0.0.1:44217`，启动前拒绝已占用端口。可通过
`SD_PREFECT_PORT` 换端口，通过第一个参数指定新的证据目录。结束时停止自己的 server，保留
证据目录供检查；目录不与应用数据库或现有 Docker 数据卷共享。

四个子探针分别生成 `report.json`、进程日志和事件日志。`probe.py` 在模型与工具第一个结果
均被 Prefect 确认后对 Worker 发出 SIGKILL，随后按原 flowRunId 重提交。它不会把同一 Agent
整体重跑解释为调用级恢复。

## 已测结果

| 场景 | 可观察证据 | 责任 |
| --- | --- | --- |
| 动态工具 schema 与限定身份 | 两个并发 Run 在 model0 设置双向屏障；实际模型收到各自 alias 和不同 enum，输出正确 | Pydantic AI DynamicToolset + 平台冻结契约 |
| A→B/C→D，B→E 无全局屏障 | B/C 时间区间重叠；E 完成早于慢 C，D 等待二者 | Python async 就绪逻辑 + Prefect tasks |
| 调用级恢复 | model0、operation-1、成功 sibling 各仅一次；未确认 model1 重试，operation-2 继续执行 | PrefectDurability task result persistence/cache |
| 默认新 Run 新鲜度 | 完全相同参数的新 engine Run 两次均执行两次实际工具调用 | SDK 默认 cache policy 包含 RUN_ID |
| API 取消 | Cancelling 经真实 CLI executor 传播到子进程，finally 执行，最终 Cancelled，没有后续工作 | Prefect runner cancellation |
| 总 deadline | 首次超时后两次 flow retry 的剩余时间均负，未重新等待 | 平台固定绝对 deadline；原生 flow retry |
| 发布后固定制品恢复 | 发布新 current digest 后，从旧 core source digest 加载 Worker，后续工具仍启动旧 plugin digest 子进程 | 探针的内容地址 loader；不是引擎内置制品路由 |
| 缺失固定插件 | 缺失 digest 在缓存恢复前明确失败，没有执行模型或工具 | 平台 guard |
| 启动重复投递 | 同 deployment、同 idempotency_key 返回同一个 flowRunId | Prefect deployment API |
| 仅设置 flow retries=1 的崩溃行为 | 活着的 Runner 将 SIGKILL 子进程记为 Crashed，runCount=1 | 原生默认行为，不能记为自动恢复通过 |
| 配置 crash automation 的自动恢复 | 指定 Run 的 Crashed→Scheduled automation 驱动同 Run 的第 2 次执行并完成；确认结果各仅一次 | Prefect Automation + Runner + SDK cache |

本目录 `evidence/` 是忽略的实际执行证据副本。`run.sh` 的成功退出表示实验断言符合观察，
包含预期的 `Crashed` 对照组；不表示每个候选平台验收都通过。

2026-09-08（Europe/Helsinki）最终完整复现：

```bash
SD_PREFECT_VENV=/tmp/sd-target-prefect-venv SD_PREFECT_PORT=44218 \
  backend/experiments/engines/prefect/run.sh /tmp/sd-target-prefect-final2
```

命令退出 **0**，四个入口均退出 **0**。原始记录位于上述目录；`evidence/` 复制了四份
report、事件、Worker 日志、server 日志和最终代码 SHA-256 清单。单独执行 ruff、
black --check、isort --check-only、bash -n 和 git diff --check 均退出 0。

## 集成成本与缺口

Prefect 可通过官方适配实现逐调用持久结果，动态工具无需注册每个业务函数；新 Run 缓存
作用域已符合目标默认新鲜度。实际运行需要 server、持久 task-result storage 和执行 Runner；
本机使用 SQLite 验证功能，生产 Compose/PostgreSQL 运行成本尚未测。
最终运行在 0.2 秒 Runner 轮询下记录过 SQLite `database is locked`，SDK 重试后实验完成；
不能把本机 SQLite 结果当作并发运行稳定性验收。

必须显式配置 crash resubmission、重试上限和失联 Worker 检测。本探针只验证单次进程崩溃
automation；没有验证整台 Worker 主机失联和有界恢复策略。用 `Runner.aadd_flow` 直接注册
包含 Pydantic AI ContextVar 的对象曾实际报 cloudpickle TypeError；固定 file-entrypoint
deployment 路径正常，不能依赖 live Agent 对象序列化。

总 deadline、冻结契约/资源、core/plugin 制品选择、出站操作身份和 unknown 写入处理仍归平台。
完整容器镜像及依赖闭包保留、缺失 core 映像的引擎终态、MCP Streamable HTTP、未知写响应、
SignalDeck 原子 Run/snapshot/outbox 事务、实际插件独立升级和定时生命周期尚未由本探针验证。
不能将局部源码制品实验扩大为 A10 已完整通过。

建议保留 Prefect 为正式可行候选，与其他候选比较上述额外恢复政策和制品管理成本；这些
结果本身不支持绕过 Temporal/Hatchet 同场景证据直接定案。

## 官方依据

- [Pydantic AI Prefect durability](https://pydantic.dev/docs/ai/capabilities/durable_execution/prefect/)
- [Prefect states](https://docs.prefect.io/v3/concepts/states)
- [Prefect zombie detection](https://docs.prefect.io/v3/advanced/detect-zombie-flows)
- [Prefect workflow cancellation](https://docs.prefect.io/v3/advanced/cancel-workflows)
- [Prefect 3.8.5 package metadata](https://pypi.org/pypi/prefect/3.8.5/json)
