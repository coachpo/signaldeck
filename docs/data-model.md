# 数据模型

SignalDeck 使用 PostgreSQL 保存工作流包、计划任务、模型连接、运行证据以及 finance 模板与报告。表结构以 [`backend/app/models/`](../backend/app/models/) 为实现依据；应用层生命周期见 [`架构说明.md`](架构说明.md)，数据与兼容政策以 [`STATUS.md`](../STATUS.md) 为准。

本文记录当前表结构。后续定义、执行证据与插件业务数据的目标所有权见 [`迭代目标`](迭代目标.md)；目标领域对象不等同于已存在的数据表。

## Finance 表

| 表 | 作用与约束 |
| --- | --- |
| `text_templates` | 可复用的报告 Markdown 模板。 |
| `reports` | 按唯一 `name`、`slug` 保存 Markdown 报告、source 和 JSON metadata；source 限于 `compiled`、`uploaded`、`external`、`agent`。 |
| `market_quotes` | 按 provider、symbol、`as_of` 保存报价缓存；价格为 `Numeric(20, 8)`，同时记录抓取时间和 stale 状态。 |
| `symbol_name_cache` | 可重建的 symbol 展示名称缓存。 |

Report 的 name、slug、source 和 metadata 在创建后由服务保持不变，编辑只更新 content；这是一项服务/API 契约，不是数据库的不可变列约束。

## Platform 表

| 表 | 作用与约束 |
| --- | --- |
| `workflow_packages` | unique key 标识当前 package；保存 manifest source、package definition、compiled plan、两类 hash、扩展依赖和时间戳。 |
| `workflow_package_secret_bindings` | `(package_id, key)` 唯一；`secret_payload` 使用 `EncryptedJSONB` 保存包内凭据。 |
| `workflow_package_schedules` | package/workflow target、enabled/paused 状态、recurrence、IANA timezone、时间范围、next fire、overlap/misfire policy、input template 和 template vars。 |
| `workflow_package_schedule_fires` | `(schedule_id, fire_key)` 唯一；保存 scheduled/manual 原因、UTC 与当地计划时间、渲染参数、物化时间、状态及 skip/error。 |
| `model_connections` | 全局 provider/model binding；保存 protocol profile、endpoint/model、capabilities、执行 policy、probe/test metadata 和加密 API key。 |
| `runs` | 只允许 `workflowPackage` target；保存根输入、最终输出、生命周期、执行 scope、lease/heartbeat、取消请求、token、trace、source-run link 与 package/schedule ownership。 |
| `run_workflow_package_snapshots` | `run_id` 同时是主键和外键；每次运行一份 executable package snapshot，包含 package/workflow identity、hash、安全 manifest material、compiled plan、launch inputs、非 secret Model Connection profile 和 preflight summary。 |
| `run_steps` | `(run_id, step_index)` 唯一；保存计划步骤、graph metadata、状态、error 和时间戳，origin 固定为 `planned`。 |
| `run_agent_invocations` | `(run_step_id, slot)` 唯一；保存 agent/schema identity、wiring、resolved input/origin、output、error、token、duration 和可选 span id。 |
| `run_operation_invocations` | `(run_step_id, slot)` 唯一；当前 operation kind 仅为 `http`，保存脱敏请求、有界响应 metadata、output、error、duration 和可选 span id。 |

Package-local agents、output schemas、capability profiles、private MCP configs、HTTP operation nodes 和 workflow graphs 保留在 package artifact 内，不拆成全局 authoring 表。运行表中的 agent/schema identity 是运行快照上下文，不指向这些已不存在的全局资源表。

## 快照与读取边界

[`RunService`](../backend/app/services/run_service.py) 在创建 run 时复制 package artifact、launch parameters 和解析后的 Model Connection profile。SQLAlchemy `before_flush` guard 拒绝缺少 snapshot 的 Workflow Package run。执行与 rerun 从这份快照构建 plan，后续 package 编辑不改变历史运行定义；rerun 创建新的完整运行与 snapshot，并保存 `source_run_id`，不会继承已执行结果。

非 secret runtime profile 冻结 endpoint、model、protocol 和执行 policy；API key 不写入快照，执行时仍从当前 Model Connection 读取。HTTP operation 和扩展工具所需的 secret 仍按 package/key 读取当前 binding。删除这些依赖后历史详情仍可读，未来 readiness 或执行可能失败。扩展依赖记录 `extensionKey`、`surfaces`、`fields`，用于说明运行依赖的能力，不是扩展代码版本快照。

`EncryptedJSONB` 对 Model Connection 和 package binding 的 payload 执行 Fernet 加密；普通 JSONB 输入、输出、schedule template 和 compiled plan 不因此成为加密字段。manifest hydration/export 会去掉数据库内部引用、原始 secret 字段及私有 MCP 的 `env`、`headers`、`query`；run read projection 另行构建安全 provenance。API envelope 可以保留 `packageId`、`packageKey` 等安全 identity，不能把内部存储结构直接作为响应。

schedule read 不返回 `inputTemplate` 或 `templateVars`，但它们仍存在数据库中。queue/progress、typed failure、`toolCallRetries` 和 provider transient retry 信息由运行及 invocation 记录投影而来，不是独立表。

## 状态与唯一性

- Run status 为 `queued`、`running`、`succeeded`、`failed`、`cancelled`；step 和 invocation status 为 `pending`、`running`、`succeeded`、`failed`、`skipped`。
- Schedule fire status 为 `pending`、`queued`、`skipped`、`failed`，描述物化结果；运行完成状态通过关联 run 读取。
- `runs.schedule_fire_id` 的非空 partial unique index 保证一个 fire 至多关联一个 run。
- 默认 execution scope 为 `package:<key>`、concurrency policy 为 `serial`。同 scope 的 running serial run 受 partial unique index 约束，领取按 `queued_at`、`id` 保持排队顺序。
- 时间戳使用 timezone-aware 数据库列；API serialization 统一输出 UTC。报价在数据库中使用 Decimal，跨 API 边界转换为 decimal-safe string。

## 删除与保留

| 操作 | 数据结果 |
| --- | --- |
| 删除 schedule | 删除其 fires，清空既有 run 的 live schedule/fire 外键，并保存 run-owned schedule provenance；运行及重跑后代保留。 |
| 删除 Workflow Package | 删除其 secrets、schedules/fires 和拥有的 runs；运行证据随 run 级联删除。 |
| 删除 run | 级联删除 snapshot、steps、agent/operation invocations；后代 run 的 `source_run_id` 置空。 |
| 删除 Model Connection 或 secret binding | 不删除历史 snapshot；后续依赖可用性由 readiness 和执行时解析判断。 |
| 启用运行保留清理 | scheduler 按 `SIGNALDECK_RUN_RETENTION_DAYS` 删除 `finished_at` 早于截止时间的终态 run；默认关闭。 |

删除 schedule 与删除 package 的语义不同；不能把 schedule detach 路径改为删除历史运行。相关契约见 [`test_workflow_package_run_contracts.py`](../backend/tests/test_workflow_package_run_contracts.py) 与 [`test_runtime_repositories.py`](../backend/tests/test_runtime_repositories.py)。

## 初始化与异常恢复

[`db/session.py`](../backend/app/db/session.py) 在 PostgreSQL advisory lock 内执行 `create_all`、bundled preset seed 和启动恢复，没有 schema migration 路径；`create_all` 不升级已有表。schema 变化的重建边界遵循项目数据政策，不能把初始化当作无损迁移。

内置 preset SQL 使用 upsert，重启会覆盖相同 key 的受管理包定义；测试 fixture 使用独立的临时数据库。启动恢复仅将缺失或过期 lease 的 running run 标为 failed，保留有效 lease 的 run；scheduler 的 lease recovery 同样终结失效运行并跳过 pending 子记录，不自动重试执行。验证依据见 [`test_db_bootstrap.py`](../backend/tests/test_db_bootstrap.py)。
