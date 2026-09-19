# 编写独立插件

SignalDeck 插件是独立发布、独立进程的业务服务。Core 通过数据库保存的发布描述和 MCP Streamable HTTP 调用插件，不在 `backend/app` 内注册 Python 业务代码；登记插件描述不会部署业务服务。Finance、Digital Oracle 和 Notes 的构建、配置与本地运行见 [`plugins/README.md`](../plugins/README.md)。

## 单一工具契约

工具身份为 `publisher/plugin/tool`，前缀必须是所属插件，例如 `signaldeck/finance/reports_create` 和 `example/notes/create`。发布的 `ToolDefinition` 同时用于目录、模型工具声明、dispatch、输入校验和输出校验；模型声明和插件实现不得另行维护约束不同的 schema。

每个工具声明 owner、description、inputSchema、outputSchema、`effect: read|write`、resourceRequirements、timeoutSeconds 和 maxAttempts，输入输出都必须是 object schema。有效工具由启用的发布、Agent 的 tools 选择及其 resource grants 共同决定：确定性 Agent 所选工具必须在其 tools grant 中，模型 Agent 只能看见授权工具；Gateway 在每次调用前仍校验授权与参数，不依赖模型遵守指令。

合同的 Core 依据是 [`tool_contracts.py`](../backend/app/domain/tool_contracts.py) 和 [`schema_contract.py`](../backend/app/domain/schema_contract.py)，插件侧 wire 与 dispatch 实现见 [`plugins/runtime/plugin_runtime`](../plugins/runtime/plugin_runtime/)。

## 固定协议与 schema 子集

MCP protocol 固定为 `2025-11-25`。Schema dialect 为 JSON Schema 2020-12，子集标识为 `signaldeck.schema/1`：

| 范围 | 支持关键字 |
| --- | --- |
| 通用 | `$schema`、单一 `type`、`title`、`description`、`enum`、`const` |
| object | `properties`、`required`、`unevaluatedProperties: false`、`minProperties`、`maxProperties` |
| array | `items`、`minItems`、`maxItems`、`uniqueItems` |
| string | `minLength`、`maxLength` |
| integer / number | `minimum`、`maximum`、`exclusiveMinimum`、`exclusiveMaximum`、`multipleOf` |
| boolean / null | 通用关键字 |

所有 object 隐式闭合，发送给外部校验器时显式补全 `unevaluatedProperties: false`。不支持的关键字直接拒绝而不是丢弃；`additionalProperties`、`allowAdditionalProperties`、`patternProperties`、组合/引用及多类型 schema 不在合同内。`$schema` 只能是 2020-12 dialect，array 必须声明 `items`，`required` 只能列出 `properties` 中的字段。`$artifact` 保留给平台内部产物引用，不能作为业务字段。可选字段用省略表达，不擅自增加 nullable 联合类型；日期由业务 adapter 校验后输出 ISO 字符串，金额、数量和市场价值输出十进制字符串。

schema/1 拒绝 `default` 和 `examples`。需要这两个注解的 schema 节点显式声明 `x-signaldeck-schema: signaldeck.schema/2`；标记不向子节点继承，每个带注解的节点各自声明，便于单独作为字段合同校验。`examples` 必须是数组；每个示例和 `default` 都须通过该节点完整闭合 schema 的校验，对象值同样受闭合字段、`required` 与嵌套约束，因此 `default: null` 只在该节点本身接受 null 时合法，不能借默认值引入 nullable 联合。服务端不会据注解改写工具参数或 Workflow 输入；表单何时物化默认值见[输入与标题](工作流解耦方案.md#输入与标题)。

## 发布描述

发布描述 `PluginRelease` 包含：

- `pluginId`、`releaseId`、`artifactDigest`：插件及不可变制品身份；
- `endpoint`、可选 `pageUrl`：MCP 和业务页面的 HTTP(S) 地址，不允许 URL 凭据、query 或 fragment；页面也可使用下述受限的 `/apps/<mountKey>/` 相对基址；
- 可选 `ui`：闭合的 `signaldeck.pluginUi/1` 页面入口，要求同时提供 `pageUrl`；省略时不序列化，显式 null 拒绝；
- `protocolVersion`、`tools`、`contractDigest`：固定协议和完整工具定义；contract digest 是按工具身份排序后规范化工具声明的散列；
- `configSchema`：资源非敏感 scope 的固定合同；
- `supportsOperationQuery`、`supportsOperationDeduplication`：写恢复能力声明。

插件以 `GET /release` 提供描述，`GET /health` 返回 `{status, releaseId}`。Core 通过 `POST /api/plugins` 登记描述，`PATCH /api/plugins/{publisher}/{plugin}` 修改 enabled；同一插件与制品身份不能登记不同描述（`release_conflict`）。目录读取只返回保存的描述和已有 operation 健康观测，不连接插件；禁用的无关插件不参与 launch 解析。

每次调用的 `_meta["signaldeck/release"]` 携带四字段精确身份：pluginId、releaseId、artifactDigest、contractDigest。MCP adapter 验证协议、工具集合与发布绑定，插件也拒绝身份不符的业务调用。制品摘要在进程启动时对插件目录和共享 runtime 下的全部文件计算，包括 VERSION、代码、web assets、Dockerfile、锁文件和随包文档，只排除 `__pycache__`、`.venv` 和 `.git`；Finance 和 Oracle 还绑定已解析的非敏感 provider 设置。因此修改随包文档或这些设置同样会产生新的制品身份。

### 声明结果页面链接

工具可选声明 `resultLinks`，每项为闭合的 `{version: "signaldeck.resultLink/1", key, label, path, query}`，同一工具内 key 唯一，label 非空。`query` 把非空 URL 参数名绑定到该工具 output schema 中存在的 `tool.output.<字段>` 标量引用；`path` 只能是安全相对路径（允许空串），不能以 `/` 开头，不能包含 scheme、authority、query、fragment、反斜杠、控制字符或 `.`、`..` 段。发布的 `pageUrl` 提供页面基址，Core 只按确认的工具输出绑定和编码参数，不理解报告或笔记参数。

resultLinks 属于工具 contract digest，新增或修改链接须发布新制品，不改动已冻结的发布；页面路径与参数由插件自己的发布声明，Core 不推断业务路由。Workflow 如何选择、绑定并在历史中读取这些链接见[插件链接](工作流解耦方案.md#插件链接)。

## 统一插件页面

插件保持独立进程、业务 API、数据库和页面所有权。主站只提供常驻布局和通用页面宿主，Nginx 负责固定上游转发；Core 不代理业务数据，也不从插件 ID 推导上游。

发布可以声明一个入口：

```json
{"ui": {"version": "signaldeck.pluginUi/1", "title": "资料"}}
```

`title` 为非空业务名称，最长 120 字符；未知字段、版本和显式 null 均拒绝。进入页面目录的发布，其 `pageUrl` 路径须精确为 `/apps/<mountKey>/`，可以是 HTTP(S) 绝对 URL 或该相对基址；没有 `ui` 的发布不进入目录，其 `pageUrl` 作为普通链接打开。页面声明不进入工具 contractDigest，但随完整不可变发布保存和冻结，修改它必须发布新制品。

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

根对象与每个挂载均闭合。挂载键为 1–64 个小写字母、数字、下划线或连字符，首字符为字母或数字；同一文件不允许重复键或重复的插件制品绑定。上游只允许 HTTP(S) origin，不带凭据、路径、query、fragment 或 Nginx 指令。只有部署方登记的可信插件获得同源挂载，登记插件描述不会自动创建代理。挂载键终身绑定同一插件制品，升级时不能改指向另一个版本。

`GET /api/plugin-pages` 只联结已保存的发布、当前启用状态和部署文件，返回 `{mountKey, pluginId, artifactDigest, title, pageUrl, enabled}` 数组，不访问插件。`pageUrl` 为相对主站的入口；`enabled` 只标记当前启用的发布，决定是否进入菜单。已登记的历史发布和已停用发布仍可通过深链接打开；没有保存描述、页面路径不匹配或没有 `ui` 的挂载不进入目录。未配置文件时目录为空。app 镜像启动时网关生成器读取同一文件，文件不可读或非法时 app 容器（Nginx 与 API）无法启动；运行中的 API 读到不可读或非法的文件时，该目录返回 503 `plugin_mounts_unavailable`，其他接口和历史读取不受影响。

| 路径 | 所有者与行为 |
| --- | --- |
| `/apps/<mountKey>/…` | 主站浏览器路由，承载插件内容及返回来源入口 |
| `/_plugins/<mountKey>/…` | 网关运输路径，转发插件页面、静态资源及业务 API |
| `/api/…` | Core HTTP API，保留运行/命令身份与错误合同 |

插件的静态资源、请求和下载使用自己的传输基址，不能使用指向 Core 的根 `/api`。网关只转发 `/`、`/ui/`、`/assets/` 和 `/api/`，前三者只允许 GET 和 HEAD；公开业务 API 和下载无需访问口令，转发时清除 Authorization 与 Cookie 请求头并隐藏上游的 Set-Cookie，MCP、发布描述和健康检查不经插件路径开放。上游按请求解析，未启用或离线的插件不会让 Nginx 无法启动。同源插件共享浏览器信任，iframe 不是不可信代码的沙箱。

已访问的插件实例留在本标签页内，切换路由只隐藏内容；打开另一业务详情由插件解释路径，不通过重设 iframe src 销毁页面。停用或目录更新不销毁旧实例，新菜单指向新发布。页面刷新重新装载深链接，未保存输入不承诺刷新恢复。Run 结果始终使用冻结的 pageUrl/resultLinks，不随当前目录改写；旧服务下线时显示明确的不可用状态并保留 Core 已确认的结果，不把旧地址重定向到新版本。

嵌入桥接消息的根为 `{protocol: "signaldeck.pluginUi/1", type, ...}`，每类消息只接受列出的字段。双方必须同时校验同源 origin、指定父/子窗口 source 和消息结构，发送时指定精确 origin。

| 方向 | type 与字段 | 用途 |
| --- | --- | --- |
| 插件 → 主站 | `ready` | 内容入口已装载，主站随后同步当前位置及偏好 |
| 插件 → 主站 | `state`：`dirty`, `busy` 布尔值 | 刷新/关闭提醒及禁止破坏性重载 |
| 插件 → 主站 | `navigate`：`path`，可选 `replace`，可选 `target: "platform"` | 请求宿主变更历史；平台目标仅用于返回来源 |
| 主站 → 插件 | `preferences`：`theme`, `expertMode`，可选 `returnTo` | 同步 light/dark/system、专家展示及返回上下文 |
| 主站 → 插件 | `location`：`path` | 按插件自有语义恢复路径、query 和 fragment |

iframe 从传输根入口启动，以 `embedded=1` 明确启用嵌入模式；主站在 ready 后发送业务位置。嵌入子页面使用 replaceState，用户可见历史由主站写入；独立模式继续使用自身导航。路径不得跳出当前挂载。消息不携带业务正文、草稿内容或凭据，插件自行保存编辑内存和处理忙碌时的业务导航。

## 资源、凭据与业务数据

Agent 的 resources 是显式授权集合，工具的 resourceRequirements 必须是其子集。工具资源配置固定所属 pluginId、scope、maxConcurrentCalls 和 requestsPerSecond；launch 验证 owner 和 configSchema，插件在自身业务查询中继续执行 scope 约束。现有插件的资源与 scope 见[插件说明](../plugins/README.md#resource-scopes)。

MCP `_meta["signaldeck/context"]` 携带 runId、nodeId、invocationId、operationId、deadline、toolGrants、resourceGrants 和 resourceBindings（本工具所需资源的非敏感 scope）。工具资源的凭据加密保存在资源中，只在最终网络调用时按冻结 revision 解析为发往插件 endpoint 的 HTTP 请求头，键名不能是 `MCP-*`、`traceparent`、`tracestate` 或 `baggage`；凭据不得出现在工具参数、模型消息、描述、scope、快照、证据、日志、错误或插件响应中。插件自己的 provider 凭据只在插件部署的 I/O 边界读取，同样不得返回；现有插件的变量见[插件说明](../plugins/README.md#build-and-run)。

Core 的 MCP 请求只传播 W3C `traceparent`，不发送 baggage 或 tracestate（追踪机制见[架构说明](架构说明.md)）；插件接入自己的追踪时只记录安全身份，不把工具参数、scope、凭据、输出或异常文本写入 span 属性。

Core 与插件只交换值合同，不交换 ORM、Session 或万能 Context。有状态插件使用自己拥有的数据库和角色，不回退到 Core 数据库；Core 不创建、读取或代理这些业务表，现有插件的表见[数据模型](data-model.md#插件业务数据)。业务 API 与页面属于插件，新增业务能力不需要在 Core 增加 router 或导航定义。

## 写操作与恢复

发送网络请求前，Core 保留 operation 和 attempt。插件必须如实声明 `effect`，不能把写操作声明为 read 来获得自动重试或缓存。写响应丢失、超时或取消时可能已有外部效果，Core 保留 `unknown`，并用同一个 operationId 查询或去重。Core 对同一 operation 的互斥不能替代插件在自身事务中的去重；查询返回 `not_found` 必须能证明该操作没有产生效果，不能把仍在处理或暂时不可见当作不存在。

Finance 的 Agent 报告写入和 Notes 写入在同一 PostgreSQL 事务中保存业务效果和不可变的 operation result，operation advisory lock 防止并发重复；相同 operationId 携带不同参数、工具或资源 scope 时拒绝。`signaldeck/operations/query` 在事务进行中返回 `unknown`，提交后返回原成功结果，确认回滚或不存在后返回 `not_found`，并再次校验调用的工具授权与 scope。这种去重只覆盖插件自己的事务效果，不能宣称任意外部远程写恰好执行一次。Agent 产出的 Finance 报告与 Notes 记录不可覆盖，后续修改产生新的业务记录和操作。

取消使用标准 MCP `notifications/cancelled`：`requestId` 必须匹配当前活动的 `tools/call`，协议和会话身份与该调用一致；共享 runtime 保留会话内的请求关联，使通知能到达正在执行的调用。插件应尽力停止对应工作，但同步 provider 调用或已提交事务可能继续完成，收到通知或 HTTP 断开都不能证明效果已回滚。Core 只在有界时间内尝试发送通知，失败时保留原 operationId 和未确认的写效果，不触发盲目重写。

读操作默认取新数据；跨 Run 缓存只由 Agent 显式声明并由 Core 处理，插件不得在新 Run 的 provider 失败时悄悄返回先前 Run 的值。

## Notes 来源与检索合同

`example/notes/create` 的闭合输入可选 `sourceKind: original|derived` 和 `sourceNoteIds`；省略类别记为 `unclassified`，不按标题或正文推断。来源 ID 为不重复、最多 50 个、每个 1–200 字符的字符串，只有 derived 可带非空引用。插件在当前 `notes-workspace` 授权 collection 内核实每个 ID 都指向已存在的不可变笔记，缺失或跨集合引用使整次写入被拒绝；这种确认只表示引用在授权集合中权威存在，不表示模型读过或核实了来源内容。笔记、来源旁表与操作回执同一事务提交，失败不留下部分写入；存储见[数据模型](data-model.md#插件业务数据)。

笔记输出包含 `sourceKind: original|derived|unclassified` 和 `sourceNoteIds`。search 的可选 `includeDerived` 省略时为 true；显式 false 只排除 derived，保留 original 和 unclassified 笔记。search 的顶层 `sourceNoteIds` 恰好对应本次返回的笔记，工作流可把这些已确认引用显式映射给派生笔记，不让模型编造 ID。

## Finance/Oracle 研究合同

研究证据使用闭合 `schemaVersion: "1"` 值对象。必需身份为 `evidenceId`、`sourceId`、`kind`、`title`、`retrievedAt`；数值以十进制字符串和值单位表达，事实期间、来源 URL/定位、申报与派生引用分别保留。`publishedAt` 和日精度 `publicationDate` 互斥；FRED 的 `availableByDate` 单独表达已知版本可用上界，不能填充成发布时间。`verified` 不代表独立审计，用户材料不能自行提升为已核实来源。两个插件各自实现同一公开值合同，不相互导入业务实现。

Finance `fundamentals_lookup` 接受可选 `asOfDate`、`cutoffAt`，返回财务事实、证据、缺口和覆盖记录。Oracle 的 `source_documents_lookup`、`prediction_events_lookup`、`research_macro_evidence` 分别读取有定位原文、指定预测合约及显式宏观序列。证券代码与同时提供的 CIK 必须匹配，否则不采用其他发行人的申报。来源限制见[插件说明](../plugins/README.md#research-source-boundaries)。

Finance 的 `research_evidence_merge` 保存完整证据和来源覆盖，同时提供最多 64 条、24,000 JSON 字符的 `analysisEvidence` 投影及截断标志；每条截短文字有独立标记，数字、单位、期间和原编号保持不变。模型不能用投影覆盖完整集合。显式请求 `includeValuation` 时，按收盘价与申报股数计算的估值只是未核实估计，覆盖记录标明期间股数变化未对账。`research_report_compile` 接收完整证据与模型提出的 claims/thresholds，只按有限公式、相容单位/期间和明确阈值来源校验；结构合法但语义非法的单条模型论断被排除并显示缺口，不修补原值，不取消对外层、来源、数组上限的校验。narrative/comparison 分别为未经事实校验的解释与历史文字对比，规范正文由插件生成。去重来源记录数不是独立事实数、印证强度或置信度。

`research_reports_create` 接收规范 `name/content` 和可选 `snapshotId`，以调用身份和完整 resource scope 写入 Journal；与普通报告一样不可覆盖。只读 `ReportRead.metadata.researchSnapshotId` 不能由普通创建/上传请求伪造。`monitor_begin`、`monitor_observe`、`monitor_report_attach` 均声明 write，其原子性、基线、精确报告绑定和表由[数据模型](data-model.md#插件业务数据)维护；它们不授权读取 Core 私有状态。`research_scope_freeze`、市场采集、合并与报告编译为 read，市场采集要求 `finance-market-data` 并校验允许的证券。

## Finance 研究争议合同

`research_report_compile` 的输入可省略 `discussion`。传入时把各阶段原始记录编入同一规范正文；省略时报告不含争议章节，也不产生相应缺口。普通 `reports_create` 不受影响。

`discussion` 是闭合对象，包含以下可省略阶段。阶段对象内对应集合也可省略：阶段不存在或为 `{}` 都表示未提供该阶段，产生资料缺口；有集合则按实际记录校验，不能用空集合冒充失败阶段。空论点集合单独说明未提供论点。

| 阶段 | 集合与上限 | 条目字段 |
| --- | --- | --- |
| `bullCase`、`bearCase` | `arguments`，每方最多 3 条 | `argumentId`、`statement`、`evidenceIds` |
| `bullResponse`、`bearResponse` | `responses`，每方最多 3 条 | `argumentId`、`disposition`、`rationale`、`evidenceIds` |
| `riskReview` | `assessments`，最多 6 条 | `argumentId`、`assessment`、`rationale`、`evidenceIds` |
| `adjudication` | `decisions`，最多 6 条 | `argumentId`、`disposition`、`rationale`、`evidenceIds` |

条目字段均必填。论点编号长度 1–80，论点及理由长度 1–1000，每条最多引用 10 个证据编号，编号长度 1–160。证据数组可以为空；提供的引用必须属于本次截止、证券及派生依赖检查后可用的证据集合。线上合同不接受显式 null、未知字段或超出数量/长度上限的结构。

回应的 `disposition` 为 `accepted`、`partially_accepted`、`rejected` 或 `unresolved`，且必须逐项回应对方原始论点。风险 `assessment` 为 `supported`、`weakened` 或 `unresolved`；裁决 `disposition` 为 `retained`、`revised`、`withdrawn` 或 `unresolved`。风险与裁决分别覆盖全部原始论点。编号重复、未知/错误方目标、遗漏处置及不可用证据进入业务可读的 `dataGaps`，不会删除原始记录；合法的明确未决本身不是结构错误。

各阶段由调用方分别提交原始输出，不能由裁决模型重新编造完整过程。编译器保证记录完整性与引用资格，不判断论证是否有说服力，也不验证预测方向。所有定性内容标为未核实；含数字或阈值的定性文字触发缺口检测，数值论断必须走 `claims/thresholds` 的校验路径。争议章节写入报告的 `content`，保存、读取、下载和监测报告绑定都使用同一正文。

## Finance K 线事件合同

只读工具 `signaldeck/finance/price_events_lookup` 按闭合规则在拆股和分红复权后的美股日线上识别 K 线事件，可扫描指定证券或整个自选股范围，并按需生成中文摘要。它需要 `finance-market-data`，`symbols` 和相对强弱的 `benchmark` 都必须在 `allowedSymbols` 内。结果只描述已完成交易日的价格事实，不预测走势，不做回测，也不构成交易建议。

输入包含 1–20 条 `detectors`，可选 1–5 个 `symbols`、`asOfDate`（纽约日期；省略为当前时间，未来日期拒绝）、`windowSessions`（1–120，默认 20，只报告最近这些交易日内的事件）和 `includeDigest`（默认 false）。省略 `symbols` 时按自选股扫描：扫描 `allowedSymbols` 中的全部证券（代码去掉首尾空格并转大写后去重），至多 50 只，超过时以 `price_events_watchlist_too_large` 拒绝，没有授权证券时以 `price_events_no_granted_symbols` 拒绝（插件侧代码，经 MCP 调用时 Core 只记录 `plugin_operation_error`，见[插件说明](../plugins/README.md#resource-scopes)）；结果只列出有事件的证券。发布合同把本工具的 `timeoutSeconds` 设为 120 秒，覆盖逐只读取 50 只证券的耗时。每条规则只接受下表所列参数，省略时取默认值；多余参数、越界取值或缺少 `benchmark` 直接拒绝，完全相同的规则去重。小数参数使用十进制字符串。三种中性规则以外都可设 `direction: up|down` 只保留一侧；多条相对强弱规则必须使用同一个基准。

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

参考实现和验证入口为 [`plugins/notes`](../plugins/notes/)、[`test_independent_plugins.py`](../backend/tests/test_independent_plugins.py)、[`test_tool_gateway_target.py`](../backend/tests/test_tool_gateway_target.py) 和 [`test_plugin_wire_contracts.py`](../backend/tests/test_plugin_wire_contracts.py)；平台验收标准见[产品说明](产品说明.md#验收标准)。

## 普通模式的连接选择

Core 的 `GET /api/connection-presets` 读取部署方提供的非敏感配置文件，供普通任务就地选择连接。该入口只验证配置格式，不部署服务、不探测在线状态，也不会仅因存在预设而改写资源。

API 进程读取 `SIGNALDECK_CONNECTION_PRESETS_FILE` 指向的文件：未设置时列表为空，文件不可读或格式非法时返回 503 `connection_presets_unavailable`。根 Compose 把宿主机同名变量指向的既有文件只读挂载到容器内的 `/etc/signaldeck/connection-presets.json`，并让 API 读取该路径，本地默认文件见 [README](../README.md#快速开始)；生产 Compose 不挂载预设文件，列表为空。

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

模型项的 `resourceId` 由所选工作流的公开声明确定，平台不预置名单；仓库不提供供应商、账户、密钥或默认模型。部署方先确认服务支持的协议、地址、模型和所需凭据，再把填好的项加入 `items`；替换本地文件时如需保留工具选择，一并复制默认的两项。密钥由用户保存资源时单独输入并加密存储，不能写入该文件、描述、scope 或日志。
