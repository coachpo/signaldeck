# 数据模型

当前 Core PostgreSQL 表由 [`platform_models.py`](../backend/app/infrastructure/platform_models.py) 及相应 infrastructure store 定义。Finance、Notes 使用独立数据库和角色，Temporal 保存自己的执行历史，文件内容寻址存储保存大产物与 Core closure。产品生命周期见 [`产品说明.md`](产品说明.md)，数据和兼容政策以 [`STATUS.md`](../STATUS.md) 为准。

v2 数据模型替换旧 workflow/step/extension 表合同；本文不描述旧表的兼容读取或无损迁移。交付与验收记录由 [`STATUS.md`](../STATUS.md) 索引。

## Core 配置与运行表

| 表 | 所有权、用途与约束 |
| --- | --- |
| `platform_package_revisions` | `(package_key, package_hash)` 主键；保存规范化 YAML、定义、所有 Workflow compiled plans 和创建时间。同身份的内容必须一致。 |
| `platform_packages` | 当前包指针：每个 `package_key` 指向一个已有内容 hash。历史修订不随指针更新而改写。 |
| `platform_task_presets` | 可选命名输入组合及任务收藏：稳定 ID、名称、package/workflow key、校验时 package hash、JSON 输入 parameters、收藏/置顶和时间戳。与包、运行、计划无级联删除关系；不充当执行定义。 |
| `platform_resources` | model/tool 资源；非敏感 config、加密且默认 deferred 的 credentials、presence 和 credential revision。 |
| `platform_plugin_releases` | `(plugin_id, artifact_digest)` 主键；保存不可变发布描述及工具契约。 |
| `platform_plugins` | 插件当前发布指针和 enabled 状态；不保存插件业务实例。 |
| `platform_runs` | Run ID、唯一 launch ID、launch intent digest、完整不可变 resolved spec、状态、输出、错误代码及时间戳；spec 内保存包/计划/绑定/来源/绝对 deadline。 |
| `platform_commands` | Run start/cancel outbox；保存尝试、创建和投递时间以及 admission rejection code。与 Run 创建或取消请求原子写入。 |
| `platform_evidence` | 调用证据 ID、Run ID、parent ID 和 payload。payload 区分 node、agent、model、tool、attempt，并含 status、输入输出、时间和安全 metadata。 |
| `platform_tool_operations` | 与工具 evidence ID 对应的 operation 状态机；保存 effect、输入摘要、参数、调用上下文和已确认结果。 |

Run 创建、身份冲突检查、取消请求和投递确认由 [`PlatformRunStore`](../backend/app/infrastructure/platform_run_store.py) 管理；证据写入、调用身份及已确认终态保护由 [`evidence_records.py`](../backend/app/infrastructure/evidence_records.py) 和 [`evidence_store.py`](../backend/app/infrastructure/evidence_store.py) 管理。不可变性由事务、身份锁及写入边界校验共同实现，不应表述为所有 JSONB 列均具数据库 immutable constraint。

Run status 为 `queued`、`running`、`succeeded`、`failed`、`cancelled`；evidence status 还包括 `pending`、`blocked`、`skipped`、`timed_out`、`unknown`。取消请求只设置请求时间并产生 command，不能直接把正在执行的 Run 改成 cancelled。最终 projection 消费引擎终态，不拥有调度权。

业务标题从固定 spec 的参数和定义派生，`hasUnknownEffects` 从非 `attempt` evidence 的 `unknown` 状态派生；它们没有独立持久列。业务结果阅读模型由 Run 输出和已确认的节点/工具输出投影，不另存结果表。历史筛选、计数与排序在数据库完成；分页的 `snapshotAt` 仅限制 Run 创建时间上界。查询与阅读边界见 [`架构说明`](架构说明.md#前端与-http)。

## 常用配置与收藏

[`task_preset_store.py`](../backend/app/infrastructure/task_preset_store.py) 定义独立新增表 `platform_task_presets`；初始化注册到同一 Core metadata，再由现有加锁 `create_all` 创建缺失表，不修改已有表或处置实例数据。`/api/task-presets` 提供列表、创建、读取、完整更新与删除。

API 使用 `hasParameters` 区分命名业务输入与无输入收藏：为 `true` 时，`parameters` 可以是符合 Workflow input schema 的对象、数组、标量或显式 JSON `null`；为 `false` 时只收藏任务，不能同时携带非 null 输入。创建和完整更新沿用同一规则。为兼容既有请求，省略 `hasParameters` 时根据非 null 的 `parameters` 推断为 `true`；参数缺失或为 null 则推断为 `false`。要保存有效的 JSON null 输入，必须明确发送 `hasParameters: true`。

存储继续使用原有可空 JSONB `parameters` 列，不新增 `hasParameters` 列。既有无输入收藏保存为 JSONB 的 JSON null；显式有效 JSON null 输入保存为 SQL NULL；其他 JSON 值原样保存。读取通过原值及 `parameters IS NULL` 查询投影推导 `hasParameters`，保留既有收藏含义，不重解释或重写旧记录。

保存时锁定当前包指针并核对调用者的 `packageHash`；有输入时按现有闭合 input schema 完整校验并拒绝凭据字段，不读取或复制资源凭据。读取会按当前定义重校验并返回当前 hash、`hasParameters`、`needsRevalidation`、安全诊断和验证状态；无输入收藏在定义可用时为 `not_applicable`，显式 null 输入仍参与 schema 校验。定义变化不会丢弃字段或改写原输入，版本不符的保存返回 409，待用户核对当前版本后再次保存。列表按置顶、收藏、更新时间排序。

保存与删除配置均不创建运行或计划，也不改写包、既有运行快照或结果。配置仅提供重新填入业务表单的输入来源，执行仍通过 Workflow Package/v2 和既有启动边界完成。

## 计划与限流/缓存

| 表 | 用途 |
| --- | --- |
| `platform_schedules` | JSON schedule definition、期望修订、已同步修订、删除意图、同步错误和更新时间。定义包含 cron、timezone、overlap、catchup window 和参数。 |
| `platform_schedule_triggers` | `(schedule_id, trigger_id)` 主键；手动触发的稳定时间身份、请求时间、投递时间和错误。同 schedule 的 identity time 唯一。 |
| `platform_schedule_fires` | 每次实际 fire 的 trigger、schedule、Temporal workflow/run 身份、scheduled time、Core Run ID、状态和错误。 |
| `platform_io_resource_permits` | 跨 Worker 的外部 I/O 并发许可与过期时间。 |
| `platform_io_resource_rates` | 资源请求间隔协调。 |
| `platform_read_tool_cache` | cache key 指向已确认只读工具 operation，保存 fetched/expiry 时间；不另存可变结果副本。 |

计划表是期望配置和查询来源，Temporal Schedule 负责日历、时区、重叠和补触发。fire action 等待完整 Run 结束；投影修复关联与终态不启动新执行。删除计划记录删除意图并同步引擎，保留其本地记录、triggers、fires 和历史 Run。相关实现为 [`schedule_store.py`](../backend/app/infrastructure/schedule_store.py)、[`schedule_fires.py`](../backend/app/infrastructure/schedule_fires.py)。

创建请求提供 `requestId` 时，该值作为持久 schedule ID；同身份、同定义重试复用原记录并继续同步，不增加 revision，不同定义返回 409 `schedule_identity_conflict`。HTTP 创建恢复先检查已提交的身份，再决定是否校验当前包，因此包暂不可用或 schema 已改变不会阻断原创建请求的重试。

读缓存必须由 Agent 的 `toolCache` 显式声明，只支持 read 工具。缓存键绑定 release、input 和 resource 身份；读取使用原 operation 的不可变输出与来源。`cacheProvenance` 保存 hit、cacheKey、sourceRunId、sourceOperationId、fetchedAt 和 expiresAt，实际有效期同时受来源记录和当前请求 TTL 限制。当前 Run 的确认恢复不通过跨 Run cache。参见 [`tool_cache_store.py`](../backend/app/infrastructure/tool_cache_store.py)。

## 快照与凭据版本

`ResolvedRunSpec` 保存完整 package definition、所选 Workflow plan、参数、模型/资源非敏感配置、credential revision、所需 plugin releases、tool alias、Core digest、deadline 和 origin。启动时这些值与 Run 和 start command 同事务提交；不存在必须在后续事务补齐的独立 snapshot 行。

资源读取只选择 config、presence 和 revision，不解密 credentials。[`EncryptedJSONB`](../backend/app/infrastructure/secret_storage.py) 通过应用加密密钥保护凭据；普通参数、定义、证据和配置不是加密凭据字段。原始凭据不得放进 package YAML 或普通参数。

编辑资源配置而不提交 credentials 会保留凭据 revision；显式写入新的 credentials 会生成新 revision。I/O 使用 `resolve_bound_credentials` 核对固定 revision；旧 revision 被轮换后不再可用，返回 `resource_binding_changed`。系统没有历史凭据归档，也不允许旧 Run 默默使用当前新凭据。历史快照和证据读取仍不依赖解密或外部服务。

新 Run 默认使用当前包及绑定；rerun 使用原包修订和参数，但重新解析当前资源/插件/Core 并生成新 deadline 与 Run ID，origin 保存 `sourceRunId`。修改输入复用同样固定原包修订，保存用户修改后的参数，origin.kind 为 `reuse` 且记录 `sourceRunId`。新运行不继承原运行结果。schedule origin 还保存 schedule、trigger 和 scheduled time。

## 执行证据与内容寻址存储

工具 operation 的身份、上下文和输入摘要在网络发送前保留；每次 execute/query/cache validation 是独立 attempt。已成功 operation 不允许被不同内容覆盖，写效果不确定时保留 `unknown`。模型成功与其网络 attempt 成功批量原子确认，避免部分确认。

同一 operation 的执行所有权使用会话级 PostgreSQL advisory lock，不增设另一张待执行队列表。操作记录与网络尝试仍是持久证据；锁只防止存活调用的重叠执行，不能证明外部写一定没有发生。重叠调用的等待、未知结果核实和恢复边界见 [`架构说明`](架构说明.md#modeltool-gateway)。

证据的调用归属按下表校验，父记录必须属于同一 Run 和节点；它与编译计划的依赖 DAG 分开保存。

| evidence kind | 调用归属 |
| --- | --- |
| `node` | 直接属于 Run，parentId 为空。 |
| `agent` | parentId 指向本节点的一条 node evidence。 |
| `model`、`tool` | parentId 指向本次 Agent attempt；工具另保存 operationId 和限定 toolId。 |
| `attempt` | parentId 指向模型调用或工具 operation；attempt 序号及 networkKind 记录实际网络尝试。 |

多上游汇聚节点只有一个 Run/节点/Agent 归属，通过计划中的边和输入/输出引用关联多个来源，不伪造多个调用父级。终态 Agent/节点投影完成提交后才传播恰逢提交的取消；Run 的 cancelled 状态可以与已完成节点的 succeeded 证据并存。引擎补投影只处理尚未终结的 Run，不能取代终态证据本身的可靠提交。

大输入/输出和 Temporal payload 通过 [`artifact_store.py`](../backend/app/infrastructure/artifact_store.py)、[`evidence_payloads.py`](../backend/app/infrastructure/evidence_payloads.py) 和 [`temporal_payloads.py`](../backend/app/infrastructure/temporal_payloads.py) 保存。公开引用包括 digest、sizeBytes 和 mediaType，内部 `$artifact` 字段为保留 envelope。读取核验完整内容，拒绝缺失、篡改和非普通文件；已确认结果不能指向可覆盖的普通文件路径。

Core closure 使用另一目录，manifest 固定文件字节、锁文件和 Python 版本。运行所需 PostgreSQL、Temporal 历史、artifact 目录、Core closure 及其可核验环境必须共同保留；单独备份查询表不足以恢复执行。当前没有自动 Run/产物保留清理或 package/Run 删除 API。

## 插件业务数据

Finance 自己定义 `text_templates`、`reports`、`market_quotes` 和 `plugin_operations`；Notes 自己定义 `notes` 与 `plugin_operations`。Digital Oracle 当前无业务持久化要求。插件 PostgreSQL 用户不能读取 Core 私有表；Core metadata 不包含这些业务表。

Finance 的普通 report API 与 Agent report 写入有不同生命周期：Agent 来源报告禁止覆盖或删除。Notes 记录不可变。两种写路径在同一插件事务提交业务效果与 operation result，并通过 operation lock 和输入/工具/scope 身份核验去重。详情见 [`writing-extensions.md`](writing-extensions.md)。

## 初始化与数据影响

`create_all` 在初始化锁下只创建当前 metadata，不升级已有表。独立数据导入与普通保存锁定同一 package 身份；missing-only 在事务内保留已存在的操作者指针，显式 update 才推进指针。启动数据目录可选，不属于 create_all 或 Core 可执行 closure。数据库初始化不再将过期 lease 的 Run 直接标记失败；恢复由 Temporal 的历史和固定 Worker 执行。

根 Compose 使用独立 `.signaldeck-target` 数据目录和独立 Core/Finance/Notes 数据库，不读取、重置或迁移旧模型连接、工作流、运行、模板及报告表。切换到该数据布局需要按 STATUS 数据政策处理；初始化路径不提供旧数据迁移。

持久化回归入口包括 [`test_platform_persistence.py`](../backend/tests/test_platform_persistence.py)、[`test_execution_projection.py`](../backend/tests/test_execution_projection.py)、[`test_artifact_store_target.py`](../backend/tests/test_artifact_store_target.py)、[`test_target_seeds.py`](../backend/tests/test_target_seeds.py)、[`test_independent_plugins.py`](../backend/tests/test_independent_plugins.py) 和 [`test_terminal_projection_cancellation.py`](../backend/tests/test_terminal_projection_cancellation.py)。常用配置、派生结果和计划创建身份分别见 [`test_task_presets.py`](../backend/tests/test_task_presets.py)、[`test_task_experience.py`](../backend/tests/test_task_experience.py) 和 [`test_target_schedules.py`](../backend/tests/test_target_schedules.py)。这些入口与实际 Temporal/Worker 集成验收的完成记录一同由 [`STATUS.md`](../STATUS.md) 关联。
