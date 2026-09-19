# 后端机制消融实验

本实验逐项衡量 SignalDeck 已有机制对可观察结果的贡献。使用真实 Tool Gateway、
PostgreSQL 证据存储，以及 DAG 组的真实 Temporal/Worker；业务响应受控。
不会修改产品代码或连接真实模型、市场数据、写入服务。

## 设计

| 机制 | 基线 → 消融 | 工作负载与观测 | 关联合同 |
| --- | --- | --- | --- |
| 跨 Run 读缓存 | 显式 TTL 60s → 不声明缓存策略 | 8 次相同输入；8 次唯一输入负对照。记录执行、发布核验、命中、输出和耗时 | A11 |
| 读工具重试 | `max_attempts=2` → `1` | 正常、首次可重试失败、持续失败；每次 1 个逻辑请求。记录恢复成功与尝试成本 | A03、A09 |
| 资源限制 | PostgreSQL limiter → 不注入 limiter | 容量为 2 的受控服务；1 请求与 8 请求突发，两套 Gateway/存储适配器。记录峰值、成功、拒绝与许可清理 | 工具资源并发与速率，见[架构说明](../../../docs/架构说明.md#modeltool-gateway) |
| 操作独占 | 原 `operation_guard` → 实验子类直接授予所有权 | 单次写入与同 operation 重叠投递；保留查询、重试、预留与成功不可变。记录实际模拟效果数与确认重放 | A08 |
| DAG 并行 | `maxParallelNodes=4` → `1` | 四独立分支加汇合；四节点链负对照。记录完整输出、依赖顺序、并发峰值与耗时 | A05 |

合同正文见[产品说明](../../../docs/产品说明.md#验收标准)。每组只改变上述一个
配置或依赖注入点，其他组机制按该工作负载原有设置固定；不存在一个用于所有工作负载的
“全开配置”。实验子类仅在测试进程中生效，不作为可供产品使用的禁用入口。

缓存与重试执行延迟为 40ms，缓存发布核验为 5ms；DAG 工具延迟为 350ms。
缓存命中仍执行实际 Gateway 的发布核验路径，不能把节省的 execute 次数称为全部网络请求减少。
未开启缓存的默认新 Run 获取行为保持不变；实验结果不支持为所有 Run 默认开启缓存。

限流组保留 2 并发、10000 RPS 资源配置，只移除 limiter 注入，因而消融的是整个资源限制器。
10000 RPS 用于尽量降低速率间距的影响，不能由此分别量化并发许可和速率间距的成本。
受控服务将同时在途超过 2 的调用返回容量错误。首批可入场调用用事件屏障固定重叠，
不依靠线程碰巧同时到达；该组耗时包含同步屏障，主要结论是并发与成功数。

独占组在第一次写入尚未生效时投递同一个 operation；模拟插件查询当时返回 `not_found`。
首次写入与重复写入返回相同内容，独立的效果计数能观察到重复写入。
最终确认重放沿用 Worker 对 `operation_in_progress` 的有界等待与原 deadline，记录等待次数。
这是两个独立存储适配器的重叠请求实验，不是两个操作系统进程崩溃恢复实验。

DAG 组保留插件默认并发和速率限制；`maxParallelNodes` 是上限，实际传输峰值可能小于 4。
本组要求独立分支实际重叠、串行变体和链为 1，且全部节点输出、最终输出及依赖顺序正确。
MCP 通过本进程 ASGI transport 调用，Temporal 使用独立本地服务与真实 Worker。

## 复现

Temporal CLI 与测试 PostgreSQL 的准备见[贡献指南](../../../CONTRIBUTING.md#测试数据库与-e2e-环境)。
后端测试 fixture 为每个样本的每个变体创建并删除独立测试库。
若要避免共用测试容器的磁盘或其他测试负载影响，可另建仅绑定本机端口、数据放在 tmpfs 的
PostgreSQL 16 容器，用 `TEST_DATABASE_URL` 指向它，结束后只停止自己创建的容器。

从仓库根目录：

```bash
cd backend
uv run --frozen python -m pytest experiments/ablation --run-ablation \
  --ablation-samples=5 --ablation-output=results/ablation/metrics.json -q
uv run --frozen python experiments/ablation/summarize.py \
  results/ablation/metrics.json results/ablation/report.md
```

`TEMPORAL_CLI` 须指向 Temporal CLI 1.8.3（DAG 组会校验版本）。`--ablation-samples` 至少为 1，缺省 5。
不传 `--run-ablation` 时，普通 pytest 不收集这些实验。pytest 成功表示所有对照断言符合
预期，**不表示消融后仍满足产品合同**。例如无独占组应观察到两次模拟效果。

输出保存在 Git 忽略的 `backend/results/ablation/`：`metrics.json` 包含原始样本、
测试结果、源码版本、文件 SHA-256、实际 Python/PostgreSQL/依赖版本及 DAG 事件；
`report.md` 给出中位数、范围和配对耗时变化。源码指纹在运行前捕获、结束时再次比对，
被测文件发生变化则实验返回失败；存在源码漂移、失败或跳过的检查、缺失配对样本时，
汇总器拒绝生成报告。

## 解释限制

- 按样本交替基线/消融先后；无额外预热，耗时不含数据库、Temporal、Worker 初始化。
  各组计时范围见测试源码，不跨组比较绝对耗时。
- 五次是本机重复观测，不提供显著性检验或置信区间；宿主机负载、数据库和初始化后的缓存
  会影响耗时。功能计数优先于小幅时间差，串行链和唯一输入用于显示收益的适用条件。
- 没有模型质量评价、真实市场数据、收费供应商或生产负载，不能推断质量、费用或生产吞吐。
- 不证明整个 Temporal、不可变制品、取消、定时运行、前端或其他全库模块可被删除。
- 实验使用当前锁文件和本机环境，具体版本以原始结果为准；本机 Python 与 CI 固定版本
  不同时，性能数据不代表 CI 环境。
