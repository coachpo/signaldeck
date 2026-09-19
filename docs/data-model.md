# 数据模型

Core 表由 [`platform_models.py`](../backend/app/infrastructure/platform_models.py) 和各 infrastructure store 定义，保存在 Core PostgreSQL 数据库。Finance 与 Notes 各用独立的数据库和角色，Temporal 保存执行历史，内容寻址目录保存大值、引擎 payload 和 Core 制品。恢复执行需要同时保留 Core 与插件数据库、Temporal 历史、产物目录和 Core 制品目录，只备份查询表不足以恢复；执行环境缺失时 worker 按制品的锁文件重新安装，保留执行环境和 uv 缓存可免去重新下载。需保留的卷见[部署说明](../docker/deployment.md)。

## Core 表

| 表 | 主键与约束 | 内容 |
| --- | --- | --- |
| `platform_package_revisions` | (`package_key`, `package_hash`) | 规范化源码、定义、全部 Workflow 的编译计划和创建时间。 |
| `platform_packages` | `package_key` | 当前修订指针；推进指针不改写历史修订。 |
| `platform_resources` | `id` | `model` 或 `tool`、非敏感 config、以 `EncryptedJSONB` 加密且默认延迟加载的 credentials、是否已配置凭据和 `credential_revision`。 |
| `platform_plugin_releases` | (`plugin_id`, `artifact_digest`) | 不可变的发布描述与工具合同。 |
| `platform_plugins` | `plugin_id` | 当前发布指针和 enabled；不保存插件业务数据。 |
| `platform_runs` | `id`；`launch_id` 唯一 | 启动意图摘要 `launch_digest`、冻结的 `spec`、状态、输出、错误代码，以及创建、开始、结束和请求取消时间。 |
| `platform_commands` | `start:<runId>` 或 `cancel:<runId>`；外键 Run | start/cancel outbox：投递尝试次数、创建与投递时间、admission 拒绝代码；与创建 Run 或请求取消在同一事务写入。 |
| `platform_evidence` | `id`；外键 Run | 调用证据：`parent_id` 和 payload（kind、status、attempt、operation 与 tool 身份、输入输出、时间、错误代码和安全 metadata）。 |
| `platform_tool_operations` | 工具证据的 `id`（外键） | operation 状态（`pending`、`succeeded`、`failed`、`unknown`）、effect、输入摘要、参数、调用上下文、尝试次数和已确认结果。 |
| `platform_task_drafts` | 客户端给出的 `id` | `revision`、更新时间和闭合的草稿 payload，见[任务草稿](#任务草稿)。 |
| `platform_task_presets` | `id` | 名称、package/workflow key、保存时的 package hash、`parameters`、收藏、置顶和时间戳；与包、Run、计划没有级联。 |
| `platform_task_preset_execution` | `preset_id`（外键，随配置级联删除） | 该配置的 `executionOptions` 预算覆盖。 |
| `platform_result_metadata` | `run_id`（外键） | `revision`、收藏、已读、备注（不超过 20000 字符）和更新时间；不改 Run 或输出。 |
| `platform_attention_receipts` | 执行更新身份 | `revision`、已读和更新时间；不保存另一份执行状态。 |
| `platform_schedules` | `id` | JSON 定义（名称、任务、参数、`executionOptions`、cron、时区、重叠策略、补触发窗口、暂停）、期望修订 `revision`、`synced_revision`、删除意图 `desired_deleted`、同步错误代码和更新时间。 |
| `platform_schedule_targets` | `schedule_id`（外键） | 最近一次写入引擎的修订和 Core task queue；与当前 Core 不一致的未删除安排按原修订重新写入引擎，期望修订、已同步修订和同步状态都不变。 |
| `platform_schedule_triggers` | (`schedule_id`, `trigger_id`)；(`schedule_id`, `identity_time`) 唯一 | 手动触发：各自占用一个早于所有日历 action 的整秒作为时间身份，另存请求、投递时间和错误。 |
| `platform_schedule_fires` | `trigger_id`；`run_id` 唯一 | 每次实际 fire 的计划、计划时间、Temporal workflow/run 身份、状态、Core Run ID 和错误；同一 fire 重复投递时保留首次关联的 Run。 |
| `platform_io_resource_permits` | (`reservation_id`, `resource_id`) | 跨 Worker 外部 I/O 的并发许可：所属 operation、过期时间及冻结的并发与请求间隔。 |
| `platform_io_resource_rates` | `resource_id` | 该资源下一次请求的最早开始时间。 |
| `platform_read_tool_cache` | cache key；外键指向 operation | 已确认只读 operation 的 ID 及获取、过期时间；不另存结果副本。 |

包修订、插件发布、Run 的 `spec`、已确认的证据和 operation 结果都不可改写，这由事务、身份 advisory lock 和写入边界校验保证，而不是数据库约束，JSONB 列本身可以更新。业务标题、`hasUnknownEffects`/`hasUnknownResults`、`unknownEvidenceIds`/`readUnknownEvidenceIds`、结果阅读模型、执行更新和模型用量汇总都在读取时从 Run、`spec`、证据和 fire 记录派生，没有结果表、计费表或持久化标记列；读取路径见[架构说明](架构说明.md#前端与-http)。

删除计划只设置 `desired_deleted` 并递增修订，计划、触发和 fire 行都保留。读缓存行只在新获取时间更晚时替换；命中时有效期取存储的过期时间与 `fetchedAt` 加本次 TTL 中较早者，且不返回给来源 Run 自身，命中结果的 `cacheProvenance` 记录 `hit`、`cacheKey`、`sourceRunId`、`sourceOperationId`、`fetchedAt` 和 `expiresAt`。

## 写入身份与冲突

下列写入由身份或乐观修订防止重复和覆盖，冲突返回 409 和表中的错误代码。

| 写入 | 身份或修订 | 幂等与冲突 |
| --- | --- | --- |
| 启动、重跑、修改输入后启动 | 请求中的 `launchId`；`launch_digest` 覆盖包与 Workflow key、参数、来源和非空的预算覆盖 | 同一 `launchId` 且意图相同返回原 Run；意图或包修订不同为 `launch_identity_conflict`。 |
| 保存包修订 | (`package_key`, `package_hash`) | 同身份内容不同为 `revision_conflict`。 |
| 登记插件发布 | (`plugin_id`, `artifact_digest`) | 同身份描述不同为 `release_conflict`。 |
| 创建计划 | 请求中的 `requestId` 成为 schedule ID | 同定义重试返回原记录且不增加修订；定义不同为 `schedule_identity_conflict`。 |
| 手动触发计划 | (`schedule_id`, `triggerId`) | 同一 `triggerId` 返回原回执。 |
| 保存草稿 | 客户端 ID 与 `revision`（新草稿为 0，每次内容变化加 1） | 内容相同的重复写入幂等；修订过期为 `draft_conflict`；`pending` 期间除 `pending`、`bindingToken` 外的变化为 `draft_pending`。 |
| 删除草稿 | 查询参数 `revision`（≥1） | 修订过期为 `draft_conflict`；`pending` 且其 `launchId` 还没有 Run 时为 `draft_pending`。 |
| 保存常用配置 | 请求的 `packageHash` 须等于当前包指针 | 不等为 `preset_package_changed`。 |
| 修改结果标记 | `expectedRevision`（无记录时为 0），至少一个非 null 字段 | 修订过期为 `result_metadata_conflict`。 |
| 标记执行更新 | 更新身份与 `expectedRevision` | 该身份已不是当前状态为 `attention_changed`；修订过期为 `attention_read_conflict`。 |

把结果标为已读会在同一事务为该 Run 当前的执行更新写入已读回执。Run 的执行更新身份是 Run ID、状态、结束时间及其非 attempt 逻辑证据的 ID、状态与错误代码的摘要，没有 Run 的 fire 失败按触发、状态、错误和引擎身份计算；观察时间不参与，所以重复读取不产生新身份，`unknown` 核实后的状态变化会产生新身份。

## 任务草稿

草稿 payload 是闭合合同：名称、原包修订（`packageKey`、`workflowKey`、`packageHash`）、可选 `sourceRunId`、`hasParameters` 与已应用的 `parameters`（任意 JSON 根）、尚未应用的 `jsonText`（不超过 1,000,000 字符，可以是非法 JSON）、`executionOptions`、稳定的 `launchId`、`pending` 和 `bindingToken`。保存只检查所引用的包修订和 Workflow 存在，以及 `sourceRunId` 与原 Run 的包、Workflow 和修订一致（否则 422 `draft_source_mismatch`），不按 Workflow schema 校验参数，启动时照常校验。`pending` 表示用该草稿的 `launchId` 发出的启动尚待核实，此时草稿必须带准备得到的 `bindingToken` 且没有 `jsonText`；非 pending 草稿不保留 token。草稿和常用配置都拒绝参数中（草稿还包括 `jsonText` 中）的凭据类键名，如 `password`、`apiKey`、`authorization`，错误不回显值。

## 常用配置与收藏

`platform_task_presets.parameters` 是可空 JSONB，用三种值区分含义：JSON `null` 表示只收藏任务、不含输入；SQL NULL 表示显式保存的 `null` 输入；其他 JSON 值原样保存。读取由值和 `parameters IS NULL` 推导 `hasParameters`。请求省略 `hasParameters` 时按 `parameters` 是否非 null 推断，因此保存 `null` 输入必须显式发送 `hasParameters: true`；`hasParameters: false` 同时带非 null 输入会被拒绝。

保存时在包锁内核对 `packageHash`，按当前定义校验输入 schema 和预算覆盖，并把覆盖写入 `platform_task_preset_execution`；没有该行视为没有覆盖。读取按当前定义重新校验，返回 `validationStatus`（`valid`、`invalid`、`unavailable`、`not_applicable`）、`needsRevalidation` 和诊断；失效的输入或覆盖只报告为 `invalid`，不改写或删除。列表按置顶、收藏、更新时间排序。

## 快照与凭据版本

Run 的不可变快照就是 `platform_runs.spec` 中的 `ResolvedRunSpec`，与 Run 和 start command 同事务写入，没有单独的快照行。它包含 `definition`（整个包定义）、`plan`（只含所选 Workflow 的编译计划）、参数、有覆盖时的 `executionOptions` 与解析后的 `effectiveAgentBudgets`、模型与工具资源绑定（非敏感配置和 `credentialRevision`）、所需插件发布、工具别名、Core 制品摘要、绝对 `deadline` 和 `origin`。`origin.kind` 为 `manual`、`rerun`、`reuse` 或 `schedule`；重跑和修改输入记录 `sourceRunId`，定时触发记录 `scheduleId`、`triggerId` 和 `scheduledAt`。

重跑和省略 `executionOptions` 的修改输入继承原 Run 的有效预算，没有预算字段的旧快照按其冻结定义解析；显式 `{}` 恢复包默认值。重跑或修改输入沿用同一 `launchId` 重试时，使用原命令记录的覆盖，不重新推导。

资源读取只选择 config、是否已配置和 `credential_revision`，不解密 credentials。只改 config 保留原 revision；提交 credentials（包括空对象）生成新的 UUID revision。I/O 由 [`resolve_bound_credentials`](../backend/app/infrastructure/platform_store.py) 按 Run 绑定的 revision 取值，revision 已变时返回 409 `resource_binding_changed`；系统不保留历史凭据。凭据规则见[开发规范](开发规范.md)。

## 执行证据与内容寻址存储

`platform_evidence` 按 ID 写入：身份字段（Run、parent、node、kind、attempt、operation、tool、input）不可更改（`evidence_identity_conflict`），进入终态的证据不可更改状态、输出、错误代码和 metadata（`evidence_result_conflict`）。调用归属按下表校验，父记录必须属于同一 Run 和节点：

| kind | parentId |
| --- | --- |
| `node` | 空，直接属于 Run。 |
| `agent` | 本节点的 `node` 证据。 |
| `model`、`tool` | 本次 Agent 执行的 `agent` 证据；工具证据的 ID 即 operation ID，另存限定的 `toolId`。 |
| `attempt` | `model` 或 `tool` 证据；`metadata.networkKind` 为模型的 `model_request`，或工具的 `execute`、`query`、`cache_validation`。 |

调用归属树与编译计划的依赖图分开保存：多上游汇聚节点只有一条 Run/节点/Agent 归属链，多个来源由计划中的边和输入引用关联，不伪造多个父级。同一工具 operation 的执行所有权使用会话级 `pg_try_advisory_lock`，不另设待执行队列表；锁只防止存活调用重叠执行，不能证明外部写入没有发生，等待与恢复见[架构说明](架构说明.md#modeltool-gateway)。

模型证据与其网络 attempt 在同一事务确认。二者的 metadata 保存 `resourceId`、`modelBindingDigest`（含凭据修订的绑定摘要，最近观察按它对应当前配置）、实际请求的 `outputTokenLimit` 与 `outputTokenLimitParameter`、供应商报告的 `usage.inputTokens`/`usage.outputTokens`（未报告为 null，不推断）和闭合的 `finishReason`；没有 `metadata.usage` 的旧证据从成功响应里的 SDK 用量读取，只采用正数，零值视为未知。失败另存 `failureType` 和 `errorCategory`：HTTP 失败只按状态码和结构化错误标识归为 `quota`、`authentication`、`rate_limit`、`model`、`input` 或 `unknown`，不保存供应商错误正文；输出超限、用量缺失和截断分别为 `output_limit`、`usage_unavailable` 和 `output_truncated`，对应稳定失败代码 `model_output_limit_exceeded`、`model_usage_unavailable` 和 `model_output_truncated`，并保留已报告的用量和结束原因。Agent 预算耗尽记为 `agent_budget_exceeded`，读取时归为 `budget_exceeded`。

证据输入输出、operation 参数与结果、Run 输出和引擎间传递的值序列化后超过 64 KiB 时写入产物目录（sha256 寻址，单个对象不超过 64 MiB），原位置只保留单键引用 `{"$artifact": {"digest": …, "sizeBytes": …, "mediaType": …}}`，因此 Workflow schema 不能声明 `$artifact` 字段。超过同一阈值的 Temporal payload 也写入产物目录，引擎历史只保留引用。读取核验大小与 digest，拒绝缺失、篡改、符号链接和非普通文件。Core 制品保存在另一目录，见[架构说明](架构说明.md#制品数据与安全)。

## 插件业务数据

插件表不属于 Core metadata，由各插件启动时在自己的数据库执行 `create_all`，同样只创建缺失表，也不在下文的兼容检查范围内。Finance 的数据库有 `text_templates`、`reports`、`market_quotes`、`research_monitor_snapshots`、`research_monitor_heads` 和 `plugin_operations`；Notes 的数据库有 `notes`、`note_provenance` 和 `plugin_operations`；Digital Oracle 没有业务持久化。两个 Compose 共用的 [`init-target-databases.sh`](../docker/init-target-databases.sh) 让每个数据库归对应角色所有并撤销 PUBLIC 的连接权限，插件角色因此不能连接 Core 数据库。该脚本挂载为 PostgreSQL 的 initdb 脚本，只在数据目录首次初始化时执行，不论启用哪些插件都创建 Core、Finance 和 Notes 的数据库与角色；已有实例不会执行之后修改过的脚本，新增有状态插件的数据库和角色需要另行创建。

`plugin_operations` 是各插件的 operation journal：以 operation ID 为主键，保存工具 ID、工具/参数/scope 指纹、scope 摘要和结果；业务效果与结果在该 operation 的事务级 advisory lock 下同事务提交。重放、去重和 `not_found` 语义见[写操作与恢复](writing-extensions.md#写操作与恢复)。

`note_provenance` 以 `note_id`（外键 `notes.id`）为主键，保存 `source_kind` 和 JSON `source_ids`，与笔记及 operation 结果同事务写入；没有该行的笔记读取为 `unclassified` 和空引用，不按内容推断。字段与检索规则见 [Notes 来源与检索合同](writing-extensions.md#notes-来源与检索合同)。

`research_monitor_snapshots` 每行是一次显式观察：`monitor_key`、规范化的范围及其 `scope_hash`、冻结的 `cutoff_at`、所属 `run_id`、证据、观察结果、`previous_snapshot_id`、`report_status`（`pending`、`succeeded`、`failed`）、`report_id` 和 `report_digest`。`research_monitor_heads` 以 (`monitor_key`, `scope_hash`) 为主键，指向最新有效观察的快照和截止时刻。三个 monitor 工具都经 journal 写入，并对同一 (`monitor_key`, `scope_hash`) 持有事务级 advisory lock。

`monitor_begin` 在新快照中冻结截止时刻：已提交的调用重放时返回原结果，提交前回滚的调用重试时取得新的截止。`monitor_observe` 对每个快照只执行一次，与截止更早的最近一次有效观察比较，结果为 `invalid`、`no_baseline`、`changed` 或 `unchanged`。只有有效观察推进头指针，而且只在截止更晚时推进，较旧的快照后完成不会使它倒退；无效观察不会成为基线，之后的模型或报告失败也不会让有效观察失效，`unchanged` 推进基线但不需要报告。比较只覆盖范围选定的来源，额外采集的资料可以保存，但不影响该范围的新鲜度和变化判断。

研究写工具保存报告时，`metadata.researchSnapshotId` 只能指向同一 Run 中需要研究且报告仍为 `pending` 的快照。`monitor_report_attach` 只能设置一次报告状态；成功时核对报告由同一 Run 创建并带有该快照 ID，再记录 `report_id` 和正文摘要。

## 初始化与 schema 演进

API、dispatcher 和 worker 启动时在 advisory lock 下对 Core metadata 执行 `create_all`，worker 另外创建 I/O 许可和读缓存表。`create_all` 只创建缺失的表，从不修改已有表；项目没有迁移框架，也不回填数据。因此持久化变更以新增表承载，例如以父记录 ID 为主键的附属表：给已有表的模型增加列（即使可空）会让现有数据库不兼容；模型只能停止写入可空，或有默认值、identity、computed 值的已有列。

[`schema_compatibility.py`](../backend/app/infrastructure/schema_compatibility.py) 由新镜像在切换前对现有数据库运行（命令见[部署说明](../docker/deployment.md)），只读比对 `app.infrastructure` 下全部声明式 base 的表，即上文的 20 张 Core 表，忽略同一进程中插件或测试声明的 base。数据库中缺失的表报告为 `created_on_start`；已有表缺少模型列，或包含模型不写入、`NOT NULL` 且没有默认值、identity 或 computed 值的列时判为 `incompatible`；数据库里的其他表只列出，不判失败。输出只含表名和列名，不兼容时退出码为 1。

Core 没有 Run、产物或 Core 制品的自动保留清理，也没有删除包、Run 或资源的 API。
