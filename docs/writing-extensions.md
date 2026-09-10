# 编写独立插件

SignalDeck 插件是独立发布、独立进程的业务服务。Core 通过数据库保存的发布描述和 MCP Streamable HTTP 调用插件；不在 `backend/app` 内注册 Python 业务代码。本文保留原文件路径作为当前插件契约权威，旧静态 Extension/INSTALLED_EXTENSIONS 接入方式已移除。

Finance、Digital Oracle 和非金融 Notes 的构建、配置及本地运行入口见 [`plugins/README.md`](../plugins/README.md)。安装插件描述不会自动部署业务服务，也不引入插件市场。

## 单一工具契约

工具身份使用 `publisher/plugin/tool`，例如 `signaldeck/finance/reports_create` 和 `example/notes/create`。发布的 `ToolDefinition` 同时用于目录、模型工具声明、dispatch 查找、输入校验和输出校验。Core 的 ToolCatalog 从限定身份生成确定性模型 alias，不使用容易冲突的字符串替换规则。

每个工具声明 owner、description、inputSchema、outputSchema、`effect: read|write`、resourceRequirements、timeoutSeconds 和 maxAttempts。输入输出均为 object schema。确定性 Agent 的所选工具必须同时出现在其 tools grant 中；模型 Agent 只能看见其授权工具。Gateway 在最终调用前仍校验授权与参数，不依赖模型遵守指令。

有效工具由启用发布、Agent tools 选择及其 resource grants 共同决定。模型侧使用构造时注册的稳定 DynamicToolset，具体声明从本 Run 的冻结目录生成；插件更新通过发布制品和配置接入，不为每个业务工具向 Core Worker 注册 Python 函数。

合同以 [`tool_contracts.py`](../backend/app/domain/tool_contracts.py) 和 [`schema_contract.py`](../backend/app/domain/schema_contract.py) 为 Core 依据，插件 wire/dispatch 实现见 [`plugins/runtime/plugin_runtime`](../plugins/runtime/plugin_runtime/)。模型声明和插件实现不得另行维护一份不同约束的 schema。

## 固定协议与 schema 子集

当前 MCP protocol 为 `2025-11-25`，SDK 固定 1.26.0。Schema dialect 为 JSON Schema 2020-12，子集标识为 `signaldeck.schema/1`：

| 范围 | 支持关键字 |
| --- | --- |
| 通用 | `$schema`、单一 `type`、`title`、`description`、`enum`、`const` |
| object | `properties`、`required`、`unevaluatedProperties: false`、`minProperties`、`maxProperties` |
| array | `items`、`minItems`、`maxItems`、`uniqueItems` |
| string | `minLength`、`maxLength` |
| integer / number | `minimum`、`maximum`、`exclusiveMinimum`、`exclusiveMaximum`、`multipleOf` |
| boolean / null | 通用关键字 |

所有 object 隐式闭合，发送给外部校验器时显式补全 `unevaluatedProperties: false`。不支持的关键字直接拒绝，不丢弃；`additionalProperties`、`allowAdditionalProperties`、`patternProperties`、组合/引用及多类型 schema 不在合同内。`$artifact` 保留给平台内部产物引用，不能作为业务 schema 字段。可选字段使用省略而不是擅自增加 nullable 联合类型；日期由业务 adapter 校验后输出 ISO 字符串，金额、数量和市场价值输出十进制字符串。

schema/1 仍拒绝 default/examples。需要注解时，在对应 schema 节点显式声明 `x-signaldeck-schema: signaldeck.schema/2`，再提供 `default` 或 `examples`；子节点不继承该标记。注解值须通过完整闭合 schema 校验，服务端不会据此改写工具参数或 Workflow 输入。省略标记的旧 schema 保持原序列化与摘要。表单只在新草稿中显式物化默认值。

## 发布描述

发布描述 `PluginRelease` 包含：

- `pluginId`、`releaseId`、`artifactDigest`：插件及不可变制品身份；
- `endpoint`、可选 `pageUrl`：MCP 和独立业务页面地址，不允许 URL 凭据、query 或 fragment；
- `protocolVersion`、`tools`、`contractDigest`：固定协议和完整工具定义；contract digest 对排序后的工具声明规范化散列；
- `configSchema`：非敏感资源 scope 的固定合同；
- `supportsOperationQuery`、`supportsOperationDeduplication`：写恢复能力声明。

当前示例服务的 `GET /release` 提供描述，`GET /health` 提供运行发布身份。通过 Core `POST /api/plugins` 安装描述，`PATCH /api/plugins/{publisher}/{plugin}` 修改 enabled。同 plugin/artifact 身份不能登记不同描述。目录读取仅返回保存的描述和已有 operation health observation，不连接插件；禁用的无关插件不参与 launch 解析。

每次调用 `_meta["signaldeck/release"]` 携带四字段精确身份：pluginId、releaseId、artifactDigest、contractDigest。MCP adapter 验证协议、工具集合与发布绑定，插件也拒绝身份不符的业务调用。当前插件的制品摘要覆盖插件目录及共享 runtime 下的全部分发文件，包括 VERSION、发布代码、web assets、Dockerfile、锁文件及随包文档（排除 `__pycache__`、`.venv` 和 `.git`）；Finance 和 Oracle 还绑定已解析的非敏感 provider 设置。修改随包文档同样会改变新进程启动时计算的制品身份。

### 声明结果页面链接

工具可选声明 `resultLinks`，每项为闭合 `{version: "signaldeck.resultLink/1", key, label, path, query}`，同一工具内 key 唯一。`query` 把非空 URL 参数名绑定到该工具 output schema 中存在的 `tool.output.<字段>` 标量引用；`path` 只能是安全相对路径（允许空串），不能包含 authority、scheme、query、fragment、反斜杠或路径穿越。发布的 pageUrl 提供页面基址，Core 只按确认工具输出绑定和编码，不理解报告或笔记参数。例如，工具 output schema 已声明 recordKey 时：

```json
{
  "resultLinks": [{
    "version": "signaldeck.resultLink/1",
    "key": "item",
    "label": "打开记录",
    "path": "",
    "query": {"item": "tool.output.recordKey"}
  }]
}
```

Workflow 的 presentation/1 `link` 分节明确提供节点输出 ref、toolId 和 linkKey。编译校验授权，Launch 在实际发布中验证链接及 pageUrl；链接和确认操作保留 evidence/operation/plugin 身份。插件离线不妨碍确认输出与声明链接读取，但不能保证目标页面可访问。Workflow 的确认调用选择、绑定错误及历史读取语义见[解耦契约](工作流解耦方案.md#插件链接)；工具发布线格式以本节为准。

resultLinks 参与工具 contract digest；旧工具缺省该字段时不自动序列化，原 digest 可验证。显式 null 拒绝。新增链接须发布新制品/描述，不修改已经冻结的发布。Finance 的报告路径及 query 参数由其自身发布提供，不能在 Core 添加业务路由推断。

## 资源、凭据与业务数据

Agent 的 resources 是显式授权集合；工具 resourceRequirements 必须是其子集。工具资源配置固定所属 pluginId、scope、maxConcurrentCalls 和 requestsPerSecond。launch 验证 owner 和 configSchema；插件在自身业务查询中继续执行 scope 约束。Notes 按 collection 保存/检索，Finance 按 allowedSymbols 限制市场查询。

MCP `_meta["signaldeck/context"]` 携带 Run/node/invocation/operation 身份、deadline、grant 及必要的非敏感 resourceBindings。凭据单独加密保存在资源中，仅最终 I/O adapter 解析固定 revision；不得放入工具参数、模型消息、描述、scope、快照、证据、日志或错误。插件自己拥有的 provider 凭据可以在插件部署 I/O 边界读取，例如 Oracle 的 FRED_API_KEY 和 EDGAR_CONTACT_EMAIL；不得返回这些值。

Core 的 MCP HTTP 请求可携带 W3C `traceparent`，将 client span 关联到发起调用的 Temporal activity；不发送 baggage 或 tracestate。资源凭据不得占用这些追踪 headers 或 `MCP-*` headers。插件如接入自己的追踪系统，应只传递安全身份，不能将工具参数、scope、凭据、输出或异常文本作为未经保护的 span 属性。Core 的持久调用证据独立于外部追踪服务。

Core 与插件只交换值合同，不交换 ORM、Session 或万能 Context。Finance/Notes 的 `PLUGIN_DATABASE_URL` 必须使用插件自己拥有的数据库和角色，不回退到 Core `DATABASE_URL`。Core 不创建、读取或代理这些业务表。Finance Templates/Reports API 和业务页面始终属于 Finance；添加业务能力不要求在 Core 增加业务 router 或导航定义。

## 写操作与恢复

发送网络请求前，Core 保留 operation 和 attempt。插件必须准确声明 effect；不要把写操作声明为 read 来获得自动重试或缓存。写响应丢失、超时或取消可能已有外部效果，Core 会保留 `unknown` 并使用同一个 operationId 查询或去重。

运行读取按冻结的显式 effect 区分只读结果 unknown 与写入效果 unknown；缺少可靠 effect 的历史证据保守处理，不用当前发布重解释。只读失败不意味着可能保存，真实写入 unknown 的核实和去重保护不变。

Core 对同 operation 的活跃执行互斥，重叠 Activity 在原 deadline 内等待既有结果；这不能替代插件在自身业务事务中的去重。旧写效果仍未核实时，本次重投的凭据或发布检查失败也不能把旧效果改成已知失败。查询 `not_found` 必须能证明该操作没有产生效果，不能把仍在处理或暂时不可见解释为不存在。

当前 Finance Agent-report 写入和 Notes 写入用同一 PostgreSQL 事务保存业务效果及不可变 operation result，operation advisory lock 防止并发重复。相同 ID 携带不同参数、工具或资源 scope 会被拒绝。`signaldeck/operations/query` 在事务进行中返回 unknown，提交后返回原成功结果，确认回滚/不存在后返回 not_found，并再次校验调用归属与 scope。

这种去重只覆盖插件实现的事务效果，不能宣称任意外部远程写都恰好执行一次。不能确认的效果保持 unknown；取消和 deadline 也不能证明已经撤销。Agent 产出的 Finance 报告与 Notes 记录不可覆盖；后续修改应产生新的业务记录/操作。

取消使用标准 MCP `notifications/cancelled`，`requestId` 必须匹配当前活动 `tools/call`，协议和会话身份必须与该调用一致。当前共享插件 runtime 保留会话内请求关联，使通知能够到达正在执行的调用。插件应尽力停止对应工作；同步 provider 调用或已提交事务可能继续完成，收到通知或 HTTP 断开都不能作为效果回滚凭据。Core 在有界时间内尝试发送通知，并保留原 operationId 与无法确认的写效果状态；通知失败不得触发盲目重写。

读操作默认取新数据。跨 Run cache 必须由 Agent 显式声明受限 TTL，缓存来源可追溯且仅引用确认成功的读 operation；插件不得在新 Run provider 失败时悄悄返回先前 Run 的值。

## Notes 来源与检索合同

Notes 1.2.0 的闭合 create 输入可选 `sourceKind: original|derived` 和 `sourceNoteIds`；省略类别保持 `unclassified`，不推断为原始资料。来源 ID 为不重复、最多 50 项的非空字符串，仅 derived 可带非空引用；插件在当前 `notes-workspace` 授权 collection 内核实每个 ID 指向已存在的不可变笔记，缺失或跨集合引用拒绝。笔记、来源旁表与操作回执同事务提交，失败不留下部分来源或业务写入。

所有新合同的笔记输出包含 `sourceKind: original|derived|unclassified` 和 `sourceNoteIds`。search 可选 `includeDerived`，省略为 true 以保留普通 API 调用方语义；显式 false 只排除明确 derived，保留历史未分类记录。search 的顶层 `sourceNoteIds` 恰好对应本次返回的 notes，包通过显式映射将这些确认引用传给派生笔记，不让模型编造 ID。

整理笔记包将 `includeDerived` 声明为普通业务输入，默认及缺失映射为 false；总结保存为 derived，保存原文为 original。Notes 页面同样提供明确的包含派生内容选择，默认排除；详情继续可查看原始及历史未分类记录和来源引用。这是插件数据与包检索策略，不是 Core 对业务 ID 的特殊处理，也不建立隐式跨 Run memory 或缓存。

新版本通过独立制品和新 endpoint 发布；旧 Run 保留原 release/contract 与回执，不把当前新增字段补入旧冻结输出。`note_provenance` 的新增表初始化不修改旧笔记，具体存储见[数据模型](data-model.md#插件业务数据)。更新示例包形成新修订，missing-only 导入不覆盖既有操作者版本；旧包/hash 和旧 Run 不自动获得新检索策略。

## 独立接入与升级

1. 构建独立服务，发布上述身份与工具合同，在插件端完成 schema、scope 和 effect 校验。
2. 为有状态插件配置自己拥有的数据库/角色，为所需资源配置非敏感 scope 及独立凭据。
3. 启动可由 Worker 访问的 MCP endpoint，获取发布描述，通过 Core 通用插件目录登记。
4. 在 Workflow Package Agent 中授予限定工具与资源；确定性策略或模型策略使用同一工具合同。
5. 验证 schema/grant/owner 拒绝、发布身份、故障隔离及真实 MCP 调用。写工具还须验证响应丢失、进行中查询、冲突去重和不可变结果。

升级使用新不可变制品和新 endpoint。安装新发布只移动当前指针；已有 Run 固定原 descriptor，必须在其恢复需求结束前保留旧服务和制品。原地换掉旧 endpoint 会导致明确 release mismatch，不能自动回退到新代码。

当前可运行示例和验证入口为 [`plugins/notes`](../plugins/notes/)、[`test_independent_plugins.py`](../backend/tests/test_independent_plugins.py)、[`test_tool_gateway_target.py`](../backend/tests/test_tool_gateway_target.py) 和 [`test_plugin_wire_contracts.py`](../backend/tests/test_plugin_wire_contracts.py)。插件级契约与完整 Core/Worker/Compose 行为的验收标准见 [`产品说明`](产品说明.md)，已执行验收记录见 [`STATUS.md`](../STATUS.md)。

## 普通模式的连接选择

Core 的 `GET /api/connection-presets` 读取部署方提供的非敏感配置文件，供普通任务就地选择连接。该入口只验证配置格式，不部署服务、不探测在线状态，也不会仅因存在预设而改写资源。操作人确认选择后才保存资源；真正启动仍核对当前绑定。最近调用成功/失败是带时间的历史观测，不代表当前在线。

本地 `./start.sh` 和根 Compose 默认将 [`docker/connection-presets.local.json`](../docker/connection-presets.local.json) 只读挂载到 `/etc/signaldeck/connection-presets.json`。默认内容来自 [`docker/plugin-defaults.json`](../docker/plugin-defaults.json)：Notes 的 `notes-workspace` 保存到 `research`，Finance 的 `finance-market-data` 仅允许 `MSFT`、`AAPL`。这些只是本地部署选择，插件是否启用由 Compose profile、bootstrap 和实际调用结果决定。

部署方可通过宿主机环境变量 `SIGNALDECK_CONNECTION_PRESETS_FILE=/absolute/path/connections.json` 替换该文件；启动、停止、状态与刷新命令沿用相同环境。路径必须指向既有普通文件，挂载缺失时不会创建空目录。直接运行 API（不经 Compose）时，此变量就是 API 进程可读取的文件路径。

文件根为 `{"items": [...]}`。每项包含 `id`、用户可辨认的 `name`、`description`、与任务定义一致的 `resourceId`、`kind`（`model` 或 `tool`）、按资源合同验证的 `config`，以及 `credentialFields`。凭据字段只声明 `key`、`label`、`required`，不包含值。以下是部署方填写模型选择时的结构说明，**不是可以直接使用或已经在线的模型配置**：

```json
{
  "id": "verified-research-service",
  "name": "部署方确认的研究服务名称",
  "description": "说明服务归属、账户及使用范围",
  "resourceId": "research-model",
  "kind": "model",
  "config": {
    "name": "部署方确认的研究服务名称",
    "baseUrl": "https://replace-with-verified-service.example/v1",
    "modelId": "replace-with-verified-model",
    "apiStyle": "chat_completions"
  },
  "credentialFields": [{"key": "apiKey", "label": "服务密钥", "required": true}]
}
```

首批研究任务都引用 `research-model`；仓库不提供虚构供应商、账户、密钥或默认模型。部署方应先确认服务支持的协议、地址、模型和所需凭据，再把填好的项加入文件的 `items`；需要保留本地工具选择时一起复制默认两项。普通用户按业务名称明确选择，核对账户/范围/保存位置后输入密钥。密钥只由资源加密存储处理，不能进入该文件、描述、scope 或日志；成功保存后浏览器密码框清空，留空更新保留既有凭据。
