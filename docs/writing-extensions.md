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
- `endpoint`、可选 `pageUrl`：MCP 和业务页面地址，不允许 URL 凭据、query 或 fragment；页面也可使用下述受限 `/apps/<mountKey>/` 相对基址；
- 可选 `ui`：闭合 `signaldeck.pluginUi/1` 展示声明；缺省不进入旧发布序列化，显式 null 拒绝；
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

## 统一插件页面

插件保持独立进程、业务 API、数据库和页面所有权。主站只提供常驻布局和通用页面宿主，Nginx 负责固定上游转发；Core 不代理业务数据，也不从插件 ID 推导上游。

发布可以声明一个入口：

```json
{"ui": {"version": "signaldeck.pluginUi/1", "title": "资料"}}
```

`title` 为非空业务名称，最长 120 字符；未知字段、版本和显式 null 均拒绝。发布 `pageUrl` 的路径须精确为 `/apps/<mountKey>/`，可以是 HTTP(S) 绝对 URL 或该相对基址。没有 `ui` 的历史发布保持既有序列化和摘要，旧式页面继续按外链访问。工具 contractDigest 仍只绑定工具声明；页面合同随完整不可变发布保存、冻结，修改它必须发布新制品。

部署文件由 `SIGNALDECK_PLUGIN_MOUNTS_FILE` 指定，Core 与网关读取同一份内容：

```json
{
  "version": "signaldeck.pluginMounts/1",
  "mounts": [{
    "mountKey": "archive-release-1",
    "pluginId": "example/archive",
    "artifactDigest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "upstream": "http://archive-release-1:8000"
  }]
}
```

根对象与每个挂载均闭合。挂载键仅允许 1–64 个小写字母、数字、下划线或连字符，首字符为字母或数字；同一文件不允许重复键或重复插件制品绑定。上游只允许 HTTP(S) origin，不允许凭据、路径、query、fragment 或 Nginx 指令。只有部署方登记的可信插件可获得同源挂载能力，安装任意插件描述不会自动创建代理。挂载键终身绑定同一插件制品，不能在升级时改指向另一个版本。

`GET /api/plugin-pages` 仅联结已保存发布、当前启用状态和部署文件，返回 `{mountKey, pluginId, artifactDigest, title, pageUrl, enabled}` 数组，不访问插件。`pageUrl` 返回相对主站入口；`enabled` 只标记当前启用发布，决定是否进入菜单。已经登记的历史发布和已停用发布仍可通过深链接读取；没有保存描述、页面路径不匹配或没有 ui 的挂载不进入目录。未配置文件时目录为空；文件不可读或非法时页面目录返回受控错误，不阻止 Core 启动和历史读取。

| 路径 | 所有者与行为 |
| --- | --- |
| `/apps/<mountKey>/…` | 主站浏览器路由，承载插件内容及返回来源入口 |
| `/_plugins/<mountKey>/…` | 网关运输路径，转发插件页面、静态资源及业务 API |
| `/api/…` | Core HTTP API，保留运行/命令身份与错误合同 |

插件静态资源、请求和下载以自己的传输基址寻址，不能使用指向 Core 的根 `/api`。公开业务 API 和下载无需访问口令，网关剥离 Authorization 和 Cookie 后转发；MCP、发布描述及内部接口不经公开插件路径开放。上游按请求解析，未启用或离线插件不能导致整个 Nginx 无法启动。同源插件共享浏览器信任，iframe 不是不可信代码沙箱。

已访问插件实例留在本标签页内，切换路由只隐藏内容；打开另一业务详情由插件解释路径，不通过重设 iframe src 销毁页面。停用或更新目录不能销毁旧实例，新菜单指向新发布。页面刷新重新装载深链接，未保存输入不承诺刷新恢复。Run 结果始终使用冻结的 pageUrl/resultLinks，不追随当前目录改写；旧服务下线时保留明确不可用状态和 Core 已确认结果，不把旧地址重定向到新版本。

嵌入桥接消息的根为 `{protocol: "signaldeck.pluginUi/1", type, ...}`，每类消息只接受列出的字段。双方必须同时校验同源 origin、指定父/子窗口 source 和消息结构，发送时指定精确 origin。

| 方向 | type 与字段 | 用途 |
| --- | --- | --- |
| 插件 → 主站 | `ready` | 内容入口已装载，主站随后同步当前位置及偏好 |
| 插件 → 主站 | `state`：`dirty`, `busy` 布尔值 | 刷新/关闭提醒及禁止破坏性重载 |
| 插件 → 主站 | `navigate`：`path`，可选 `replace`，可选 `target: "platform"` | 请求宿主变更历史；平台目标仅用于返回来源 |
| 主站 → 插件 | `preferences`：`theme`, `expertMode`，可选 `returnTo` | 同步 light/dark/system、专家展示及返回上下文 |
| 主站 → 插件 | `location`：`path` | 按插件自有语义恢复路径、query 和 fragment |

iframe 从传输根入口启动，以 `embedded=1` 明确启用嵌入模式；主站在 ready 后发送业务位置。嵌入子页面使用 replaceState，用户可见历史由主站写入；独立模式继续使用自身导航。路径不得跳出当前挂载。消息不携带业务正文、草稿内容或凭据，插件自行保存编辑内存和处理忙碌时的业务导航。

网关采用现有 Nginx 的变量上游及请求时解析方式，页面桥接采用浏览器 postMessage；选择这些现有机制避免增加 Core 业务代理或远程组件装载。配置语义参考 [Nginx proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)，消息边界参考 [MDN postMessage](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage)。

## 资源、凭据与业务数据

Agent 的 resources 是显式授权集合；工具 resourceRequirements 必须是其子集。工具资源配置固定所属 pluginId、scope、maxConcurrentCalls 和 requestsPerSecond。launch 验证 owner 和 configSchema；插件在自身业务查询中继续执行 scope 约束。Notes 按 collection 保存/检索，Finance 按 allowedSymbols 限制市场查询。

MCP `_meta["signaldeck/context"]` 携带 Run/node/invocation/operation 身份、deadline、grant 及必要的非敏感 resourceBindings。凭据单独加密保存在资源中，仅最终 I/O adapter 解析固定 revision；不得放入工具参数、模型消息、描述、scope、快照、证据、日志或错误。插件自己拥有的 provider 凭据可以在插件部署 I/O 边界读取，例如 Oracle 的 FRED_API_KEY 和 EDGAR_CONTACT_EMAIL；不得返回这些值。

Oracle 的 FRED 适配器按请求日期窗口倒序读取观测值，多个序列均分本次总条数上限；`asOfDate` 同时约束观测结束日期和当时可知的数据修订。标题与单位来自 FRED 序列元数据，不把所有序列标成百分比或美元。返回的 `date` 是统计观察期，不代表发布日期；调用方仍须保留指标频率、季调和年化口径的区别。当前接口不会返回独立的发布时间字段。插件的 `DIGITAL_ORACLE_PROVIDER_TIMEOUT` 控制单次上游请求等待时间，默认 5 秒；本地 Compose 可通过同名环境变量配置，工作流与模型输入不携带该部署设置。

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

## Finance/Oracle 研究合同

研究证据使用闭合 `schemaVersion: "1"` 值对象。必需身份为 `evidenceId`、`sourceId`、`kind`、`title`、`retrievedAt`；数值以十进制字符串和值单位表达，事实期间、来源 URL/定位、申报与派生引用分别保留。`publishedAt` 和日精度 `publicationDate` 互斥；FRED 的 `availableByDate` 单独表达已知版本可用上界，不能填充成发布时间。`verified` 不代表独立审计，用户材料不能自行提升为已核实来源。两个插件各自实现同一公开值合同，不相互导入业务实现。

Finance 在 `fundamentals_lookup` 增加可选 `asOfDate`、`cutoffAt` 及财务事实、证据、缺口、覆盖记录。真实默认来源为 SEC，旧显式 deterministic 测试配置保持；新字段不回填旧 Run。Oracle 的 `source_documents_lookup`、`prediction_events_lookup`、`research_macro_evidence` 分别读取有定位原文、指定预测合约及显式宏观序列。证券代码与同时提供的 CIK 必须匹配，否则不采用其他发行人的申报。来源限制见[插件说明](../plugins/README.md#research-source-boundaries)。

Finance 的 `research_evidence_merge` 保存完整证据和来源覆盖，同时提供最多 64 条、24,000 JSON 字符的 `analysisEvidence` 投影及截断标志；每条截短文字有独立标记，数字、单位、期间和原编号保持不变。模型不能用投影覆盖完整集合。`research_report_compile` 接收完整证据与模型提出的 claims/thresholds，只按有限公式、相容单位/期间和明确阈值来源校验；结构合法但语义非法的单条模型论断被排除并显示缺口，不修补原值，不取消对外层、来源、数组上限的校验。narrative/comparison 分别为未经事实校验的解释与历史文字对比，规范正文由插件生成。去重来源记录数不是独立事实数、印证强度或置信度。

`research_reports_create` 接收规范 `name/content` 和可选 `snapshotId`，以调用身份和完整 resource scope 写入 Journal；与普通报告一样不可覆盖。只读 `ReportRead.metadata.researchSnapshotId` 不能由普通创建/上传请求伪造。`monitor_begin`、`monitor_observe`、`monitor_report_attach` 均声明 write，其原子性、基线、精确报告绑定和新增表由[数据模型](data-model.md#插件业务数据)维护；它们不授权读取 Core 私有状态。`research_scope_freeze`、市场采集、合并与报告编译为 read，市场采集仍要求 `finance-market-data` 并校验允许的证券。

## Finance 研究争议合同

Finance 1.2.0 的 `research_report_compile` 输入可省略 `discussion`。省略时沿用原报告内容与输出字段；传入时把各阶段原始记录编入同一规范正文，不新增存储表或专用页面。普通 `reports_create` 不受影响。

`discussion` 是闭合对象，包含以下可省略阶段。阶段对象内对应集合也可省略：阶段不存在或为 `{}` 都表示未提供该阶段，产生资料缺口；有集合则按实际记录校验，不能用空集合冒充失败阶段。空论点集合单独说明未提供论点。

| 阶段 | 集合与上限 | 条目字段 |
| --- | --- | --- |
| `bullCase`、`bearCase` | `arguments`，每方最多 3 条 | `argumentId`、`statement`、`evidenceIds` |
| `bullResponse`、`bearResponse` | `responses`，每方最多 3 条 | `argumentId`、`disposition`、`rationale`、`evidenceIds` |
| `riskReview` | `assessments`，最多 6 条 | `argumentId`、`assessment`、`rationale`、`evidenceIds` |
| `adjudication` | `decisions`，最多 6 条 | `argumentId`、`disposition`、`rationale`、`evidenceIds` |

条目字段均必填。论点编号长度 1–80，论点及理由长度 1–1000，每条最多引用 10 个证据编号，编号长度 1–160。证据数组可以为空；提供的引用必须属于本次截止、证券及派生依赖检查后可用的证据集合。线上合同不接受显式 null、未知字段或超出数量/长度上限的结构。

回应的 `disposition` 为 `accepted`、`partially_accepted`、`rejected` 或 `unresolved`，且必须逐项回应对方原始论点。风险 `assessment` 为 `supported`、`weakened` 或 `unresolved`；裁决 `disposition` 为 `retained`、`revised`、`withdrawn` 或 `unresolved`。风险与裁决分别覆盖全部原始论点。编号重复、未知/错误方目标、遗漏处置及不可用证据进入业务可读的 `dataGaps`，不会删除原始记录；合法的明确未决本身不是结构错误。

各阶段由调用方分别提交原始输出，不能由裁决模型重新编造完整过程。编译器保证记录完整性与引用资格，不判断论证是否有说服力，也不验证预测方向。所有定性内容标为未核实，含数字或阈值的定性文字继续触发现有缺口检测，必须走 `claims/thresholds` 的数值校验路径。争议章节进入原有 `content`；保存、读取、下载和监测报告绑定均沿用同一正文。升级遵循下方冻结发布规则，已有运行仍使用其原发布。

## Finance K 线事件合同

Finance 1.3.0 新增只读工具 `signaldeck/finance/price_events_lookup`，按闭合规则识别美股日线 K 线事件；1.4.0 改为读取分红复权价格，增加 7 条规则和 `minBaseSessions` 参数；1.5.0 增加自选股扫描和中文摘要。它需要 `finance-market-data`，`symbols` 和相对强弱的 `benchmark` 都必须在 `allowedSymbols` 内。结果只描述已完成交易日的价格事实，不预测走势，不做回测，也不构成交易建议。

输入包含 1–20 条 `detectors`，可选 1–5 个 `symbols`、`asOfDate`（纽约日期；省略为当前时间，未来日期拒绝）、`windowSessions`（1–120，默认 20，只报告最近这些交易日内的事件）和 `includeDigest`（默认 false）。省略 `symbols` 时按自选股扫描：扫描 `allowedSymbols` 中的全部证券（代码去掉首尾空格并转大写后去重），至多 50 只，超过时以 `price_events_watchlist_too_large` 拒绝，没有授权证券时以 `price_events_no_granted_symbols` 拒绝；结果只列出有事件的证券。发布合同把本工具的 `timeoutSeconds` 设为 120 秒，覆盖逐只读取 50 只证券的耗时。每条规则只接受下表所列参数，省略时取默认值；多余参数、越界取值或缺少 `benchmark` 直接拒绝，完全相同的规则去重。小数参数使用十进制字符串。三种中性规则以外都可设 `direction: up|down` 只保留一侧；多条相对强弱规则必须使用同一个基准。

| 规则 | 参数（默认值） | 事件条件 |
| --- | --- | --- |
| `new_high_low` | `lookback`(60)、`minBaseSessions`(1) | 收盘价高于前 N 个交易日的最高收盘价（up）或低于最低收盘价（down），持平不算 |
| `near_high_low` | `lookback`(250)、`withinPercent`("2") | 收盘价首次进入前 N 日最高收盘价下方 `withinPercent` 以内（up）或最低收盘价上方以内（down），前一日还在该范围外；越过极值属于 `new_high_low` |
| `drawdown` | `lookback`(60)、`minPercent`("10") | 收盘价首次较前 N 日最高收盘价回撤至少 `minPercent`（down），或较最低收盘价反弹至少 `minPercent`（up） |
| `breakout` | `lookback`(20)、`volumeRatio`("1.5")、`minBaseSessions`(1) | 收盘价突破前 N 日最高价或跌破最低价，且成交量不低于前 N 日均量的倍数；`"0"` 取消量能条件 |
| `failed_breakout` | `lookback`(20) | 最高价越过前 N 日最高价，但收盘回到其下方且低于前一日收盘（down）；或最低价跌破前 N 日最低价，但收盘回到其上方且高于前一日收盘（up） |
| `gap` | `minPercent`("1") | 开盘价高于前一日最高价或低于最低价，缺口幅度不小于阈值 |
| `large_move` | `minPercent`("4")、`atrMultiple`("2")、`window`(14) | 收盘涨跌幅不小于 max(`minPercent`, `atrMultiple` × 前一日 ATR 占收盘价的百分比) |
| `window_move` | `window`(5)、`sigmaMultiple`("3")、`minPercent`("0") | N 日累计涨跌幅首次达到 max(`minPercent`, `sigmaMultiple` × 这 N 日之前 60 个交易日的日收益率标准差 × √N)；两者至少一个大于 0 |
| `spike_reversal` | `minPercent`("4")、`atrMultiple`("2")、`window`(14)、`maxSessions`(10) | 符合 `large_move` 条件的单日大涨（大跌）后 `maxSessions` 日内，收盘价首次回到大涨（大跌）前一日收盘价之下（之上）；大涨被回吐是 down 事件 |
| `gap_fill` | `minPercent`("1")、`maxSessions`(10) | 缺口在 `maxSessions` 个交易日内首次回到缺口前价位，含缺口当日 |
| `island_reversal` | `maxSessions`(10) | 至多 `maxSessions` 个交易日的价格区间被前后两个缺口完全隔开 |
| `ma_cross` | `fastWindow`(50)、`slowWindow`(200)、`average`(`sma`/`ema`) | 快线上穿（up）或下穿（down）慢线 |
| `price_ma_cross` | `window`(50)、`average`(`sma`/`ema`) | 收盘价上穿或下穿均线 |
| `macd_cross` | `fastWindow`(12)、`slowWindow`(26)、`signalWindow`(9)、`reference`(`signal`/`zero`) | MACD 线穿越信号线或零轴 |
| `rsi_threshold` | `window`(14)、`upper`("70")、`lower`("30") | RSI 进入超买区（up）或超卖区（down） |
| `bollinger_break` | `window`(20)、`standardDeviations`("2") | 收盘价首次收在上轨之上或下轨之下 |
| `bollinger_squeeze` | `window`(20)、`standardDeviations`("2")、`lookback`(120) | 带宽低于前 N 日最小值（中性） |
| `range_contraction` | `lookback`(7) | 当日高低价幅是 N 个交易日内最窄的（中性） |
| `inside_bar` | 无 | 最高价低于前一日、最低价高于前一日（中性） |
| `engulfing` | `trendSessions`(5) | 当日实体完全覆盖前一日相反方向的实体（阳包阴 up，阴包阳 down），不能只是同一实体倒转 |
| `pin_bar` | `trendSessions`(5) | 下影线（up，锤子线）或上影线（down，射击之星）至少占当日高低价幅的三分之二 |
| `volume_spike` | `lookback`(20)、`volumeRatio`("2") | 成交量不低于前 N 日均量的倍数，方向取当日收盘涨跌 |
| `streak` | `minLength`(5) | 连续上涨或下跌收盘达到 N 日的当天 |
| `relative_strength` | `benchmark`（必填）、`lookback`(60)、`minBaseSessions`(1) | 收盘价与基准收盘价之比高于前 N 日最高值或低于最低值 |

`minBaseSessions` 只保留被突破的前 N 日极值至少在这么多个交易日之前形成的事件，用来去掉趋势中逐日重复的新高、突破和相对强弱；默认 1 表示不过滤，取值不能超过 `lookback`。`engulfing` 和 `pin_bar` 要求形态前一日的收盘价低于（up）或高于（down）`trendSessions` 个交易日之前的收盘价，`0` 取消趋势条件。

交易日按纽约日期划分，当日纽约时间 16:30 后才算完成，未完成的 K 线不参与计算。单次读取约两年、最多 500 个交易日。规则读取按拆股和分红复权的开高低收：复权因子取 provider 复权收盘价与收盘价之比，并以最后一个完成交易日为基准，所以最新价格等于 provider 价格，更早的价位按之后的分红相应下调。与所在段因子相差不足十万分之一的交易日沿用该段因子，避免浮点噪声把持平的价格拆成新高或新低。任一交易日缺少正的复权收盘价时，该证券退回只按拆股调整的价格，并给出 `price_events_dividend_unadjusted` warning；相对强弱的基准同样处理。事件 `direction` 表示事件本身的价格方向，例如向上缺口被回补是 down 事件。

输出包含 `asOfDate`、实际截止时间 `cutoffAt`、`windowSessions`、实际扫描的证券 `scannedSymbols`、这些证券中最新的已完成交易日 `latestSession`（没有可用交易日时省略）、截断前的命中总数 `matchedCount` 和 `warnings`；`includeDigest` 为 true 时另给出中文 Markdown 摘要 `digest`，按证券列出事件、所用规则、价格口径和提示，`latestSession` 早于 `asOfDate` 时注明当天休市或尚未收盘。每只证券给出价格口径 `priceBasis`（`dividend_adjusted` 或 `split_adjusted`）、交易日范围、最新状态 `state`（20/60/250 日收盘区间位置、SMA20/50/200 与均线排列、RSI14、ATR14 百分比、20 日量比、连涨或连跌天数）和按日期从新到旧排列的 `events`（每只最多 50 条，`eventCount` 为截断前数量）。每个事件回显生效的规则参数，给出按 `priceBasis` 计算的 `close`、`changePercent`、参考价位 `level/levelLabel` 和带单位的 `measures`，并给出 provider 原始收盘价 `rawClose`（已按拆股调整、未按分红调整，与 `market_data_ohlcv_lookup` 的 `close` 一致），以及关联日期。价格与派生值保留 4 位小数，交易日数和股数为整数。行情不可用、历史或成交量不足、基准缺少交易日、缺少分红复权、异常 K 线和截断都通过 warning 披露，不生成替代数据；价格非正的 K 线被剔除，其余异常 K 线保留并告警。

限制：只有日线；Yahoo 历史数据是当前版本，不是时点存档；分红复权依赖 provider 的复权收盘价，provider 未计入的公司行为仍可能表现为跳空；单根错误报价无法与真实波动自动区分。

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

模型资源标识由所选工作流的公开声明确定，不形成平台预置名单；仓库不提供虚构供应商、账户、密钥或默认模型。部署方应先确认服务支持的协议、地址、模型和所需凭据，再把填好的项加入文件的 `items`；需要保留本地工具选择时一起复制默认两项。普通用户按业务名称明确选择，核对账户/范围/保存位置后输入密钥。密钥只由资源加密存储处理，不能进入该文件、描述、scope 或日志；成功保存后浏览器密码框清空，留空更新保留既有凭据。
