# Frontend src 测试盘点与风险初筛

范围：Vitest `src/**/*.{test,spec}.{ts,tsx}`，84 文件，基线执行428用例；静态标题含参数模板，不冒充完整展开节点。全量已执行的默认基线记录于 `/tmp/signaldeck-frontend-baseline.log`。

所有文件均纳入提取盘点与分组风险初筛；仅明确列出的候选读取完整断言/实现并开展故障对照，其余保留，不声称完成逐用例消融。

## api

HTTP 请求、camelCase/闭合写入、精确 JSON 根值、错误详情、认证重试与下载；mock fetch 保留真实 client/serialization，不能证明后端契约实现

### frontend/src/lib/api/task-experience.test.ts

- 32 行；5 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：preserves budget selections through preparation, historical reuse, presets, drafts and schedules；invalidates preparation identity and schedule dirty state when only budgets change
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/api/workflow-platform.test.ts

- 124 行；9 处 expect；6 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：submits canonical camelCase launch identity without changing parameter values；preserves a non-object parameter value in manual and scheduled writes: %j；keeps read-only synchronization projections out of closed schedule writes；does not turn read-only credential revisions into resource writes；encodes both parts of the qualified plugin identity；passes a stable schedule trigger identity without inventing a run
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/api.test.ts

- 385 行；42 处 expect；13 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：sends a successful GET request for listTemplates；sends the stored API token as a bearer token；prompts once for an API token after a 401 and retries the request；sends a successful POST request for createTemplate；preserves status, code, message, and validation details for 422 responses；drops malformed non-array details from JSON error envelopes；falls back to a generic request_failed error for 500 text responses；derives v1 and platform URLs from a configured versioned base；routes platform modules through the unversioned api base；encodes v1 path segments against the derived base URL；downloads the original bytes with the requested name %s and keeps the URL alive；defaults to same-origin /api/v1 outside dev when the env base is empty；keeps explicit VITE_API_BASE_URL behavior unchanged
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

## codec

schema/2 注解、必填/省略/null、精确 JSON 值与 round-trip；同路径各形态是不同数据契约，保留

### frontend/src/lib/platform-authoring/common/resource-ref.test.ts

- 58 行；9 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：parses key-only refs into typed ResourceRefs；parses key+version refs and formats them back；rejects invalid versions with current caller-facing wording；rejects blank input and exposes validation issues for shared callers；parses line-delimited refs and tracks indexed validation paths
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/platform-authoring/mapping-sources.test.ts

- 33 行；11 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：resolves a declared list item at an arbitrary index and preserves absent knowledge；finds distinct declared text choices, including later list positions；prevents field renaming from overwriting a sibling；keeps comparison operands and nonempty boolean groups when changing operators
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/platform-authoring/parameter-values.test.ts

- 50 行；12 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：preserves JSON root %s；initializes scalar and array schemas without an object wrapper；uses object defaults exactly without adding nested optional defaults；checks root scalar and array item types through the existing schema codec；does not silently replace nonfinite numbers or blank input with null
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/platform-authoring/schema/codec.test.ts

- 401 行；29 处 expect；14 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：writes title and description metadata for supported builder nodes；reads title and description metadata from supported JSON Schema nodes；parses already-decoded JSON Schema objects through the shared schema parser；returns structured parser failures for invalid already-decoded JSON Schema values；writes primitive builder defaultValue entries as JSON Schema defaults；round-trips nested object and array defaultValue entries through JSON Schema defaults；reads primitive JSON Schema defaults into builder defaultValue entries；rejects undeclared fields in closed object defaults；reports unsupported keywords with the current parser wording；decodes registry refs into key and version fields；requires per-node opt-in and never inherits the root marker；preserves marker, empty examples and constraint declarations without adding annotations elsewhere；validates examples and defaults against preserved constraints；keeps explicit null as an error for a non-nullable scalar rather than silently omitting it
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/platform-authoring/schema/input-values.test.ts

- 101 行；18 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：initializes every legal root and arbitrary constant without wrapping or supplementing it；validates compound choices structurally regardless of object key order；validates all supported numeric, text, collection and omission boundaries with labels
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/platform-authoring/schema/launch-input-state.test.ts

- 307 行；27 处 expect；12 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：creates canonical state for required and defaulted fields；keeps formatted JSON deterministic；rejects missing required fields before applying payloads；rejects unknown fields before applying supported object payloads；keeps optional fields and defaults absent in explicitly supplied payloads；rejects nested missing required fields and nested unknown fields；drops optional schema keys from the canonical payload after form removal；roundtrips explicit nullable nulls for primitive enum object and array wrappers；rejects non-nullable nulls before applying raw JSON to a draft；preserves unknown fields and nullable nulls when metadata rebinds the draft；keeps unsupported schemas on the raw JSON fallback path；parses only object raw JSON payloads
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/platform-authoring/schema/preview.test.ts

- 30 行；2 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：keeps titles out of synthesized string samples；builds initial run input values from required fields only
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/platform-authoring/schema/schema-template.test.ts

- 71 行；10 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：derives deterministic JSON from required and defaulted schema fields；resets back to the exact generated template text；starts unsupported or non-object schemas from an empty object template；parses only object JSON launch parameters；preserves explicit nulls in parsed launch parameter JSON
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

## form

递归控件、选择/空值/默认值、兄弟字段编辑与输入顺序；DOM 事件验证不可用纯函数覆盖替代

### frontend/src/components/platform-authoring/generated-form/schema-form.test.tsx

- 415 行；42 处 expect；10 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders the value-entry editor body without the authoring card shell；uses schema titles for field labels, falls back to property keys, and preserves value-entry payloads；shows optional field titles and descriptions before and after adding them；keeps absent optional defaults omitted until explicitly added；starts optional no-default fields as addable generated fields；removes optional no-default fields from the generated value after they are added；preserves explicit empty values instead of replacing them with schema defaults；uses enum descriptions while keeping the allowed option list constrained；uses discriminated union branch titles in the selector and branch descriptions in the selected editor；keeps selected union branches without descriptions on the existing object fallback copy
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/platform-authoring/generated-form/value-editor.test.tsx

- 320 行；33 处 expect；12 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：preserves exact omitted, empty and null values while editing an array sibling；makes compound choice contents visible and retains the chosen object exactly；allows free values to change form and restore their earlier contents；lets a missing boolean be explicitly answered no without adding other defaults；preserves nullable values across edits and restores the previous nonempty alternative；reports bounds and uniqueness in business language；keeps a cleared number empty through sibling edits instead of inserting zero；orders fields by declared hints without renaming keys or changing payload order；matches hints to the current object and array item rather than unrelated field names；accepts new multiline text without requiring a predeclared textarea hint；describes allowed empty values without confusing stored presence with user effort；treats nonempty-only choices as required even without a minimum length
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/platform-authoring/inspectors/structured-value-inspector.test.tsx

- 179 行；36 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders nested objects, arrays, and primitive values without editable controls；renders empty collections and sorts object keys deterministically；can preserve object insertion order in the compact tree presentation；renders multiline strings as raw JSON by default with a plain text view；gates markdown preview behind an explicit inspector opt-in
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/platform-authoring/schema-composer/json-schema-editor.test.tsx

- 121 行；10 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：edits business field names without changing saved keys, values or closed constraints；creates a null default with the correct annotation and no raw editor；edits compound default values without adding omitted sibling defaults；adds fields with meaningful names and lets the author mark them optional
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/launch-inputs.test.tsx

- 211 行；35 处 expect；7 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：edits scalar input directly and reports recoverable integer errors without truncation；edits array and null roots without inventing an object wrapper；preserves input and declared business labels when switching display modes；recovers valid unapplied drafts only after an explicit restore action；retains incomplete originals with download and explicit discard, preserving applied values；blocks incomplete fields with their declared titles and repairs them in place；downloads an unfinished original verbatim without clearing it
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/task-inputs.test.tsx

- 50 行；12 处 expect；7 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：uses declared labels and static hints after fields are renamed, preserving whitespace；preserves omitted defaults, nullable and unknown fields when editing siblings；edits arrays using the shared form without delimiter parsing；treats includeRisk/reportId/collection as ordinary data; only declared defaults seed drafts；discovers new package and workflow names including all legal roots；keeps array item defaults omitted while editing another item；matches JSON Schema Unicode code point length constraints
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

## result

冻结结果、unknown/取消语义、附件显式读取、历史分页、幂等重跑、草稿与导出；组件/API mock 不证明真实后端

### frontend/src/pages/platform/attention.test.tsx

- 28 行；9 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：keeps viewed unknown operations actionable and provides no-Run fire navigation
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/cache-provenance.test.tsx

- 31 行；6 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：links reused output to its originating run and preserves freshness timestamps
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/execution-diagnostic.test.tsx

- 55 行；19 处 expect；8 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：explains known quota errors without exposing implementation codes；does not reinterpret historical HTTP errors as quota or input errors；explains a reported output limit violation even with unknown model category；preserves an output limit diagnosis through an aggregate workflow failure；explains an unusable reply without implying that contacting the model failed；shows authentication handling and an exact recent evidence link；does not turn absent current-version observations into an online claim；explains %s independently from provider account quota
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/model-usage-panel.test.tsx

- 61 行；16 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：keeps absent provider counters unknown while explaining failed-attempt coverage；shows an explicitly reported zero and allows the model breakdown to be opened；offers a read retry after errors and labels today；shows independent effective output limits without changing omitted settings
- mock 边界：@/hooks/use-model-usage

### frontend/src/pages/platform/plugin-health.test.tsx

- 19 行；6 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：reports recorded failure and recovery without exposing identifiers or raw error codes；does not equate a lack of observations with availability；preserves uncertainty and tells the user to check effects before repeating
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-artifact-presentation.test.tsx

- 74 行；16 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：reads a large response through the frozen declared selector without exposing its envelope；exports only declared large content and preserves the user；does not interpret a tool envelope with selectors belonging to a differently mapped node；keeps unmatched selectors incomplete instead of exporting the raw response
- mock 边界：@/hooks/use-workflow-platform, @/lib/api/workflow-platform

### frontend/src/pages/platform/result-compare.test.tsx

- 77 行；22 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：retains original input and unknown status with identical text without exposing identifiers；requires explicit attachment reading even with a fixed selection URL；keeps empty results honest and uses explicit generic JSON section selection；selects a known result from server history without requiring its ID to be remembered；retains an earlier source selection when equal generic sections are grouped
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-content.test.tsx

- 38 行；14 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders boolean, null and business-like keys as literal generic values；keeps JSON string and invalid JSON bytes literal: %s；renders text attachments with shared Markdown；uses declared field titles without changing arbitrary business values or source text
- mock 边界：@/hooks/use-workflow-platform

### frontend/src/pages/platform/result-delivery.test.ts

- 80 行；28 处 expect；8 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：keeps declared sections in order and does not duplicate legacy body/receipt；supports historical body, receipt and generic output without business aliases；preserves %s, cancellation and provenance；exports read uncertainty without claiming an unconfirmed save；requires explicit artifact loading and records excluded/deferred content；exports a large confirmed JSON value with many code delimiters without argument overflow；has no pretend content for empty results and preserves fenced source bytes；exports receipt confirmation without a service envelope while keeping declared body unchanged
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-diff.test.ts

- 15 行；4 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：preserves both exact inputs in deterministic differences；bounds large comparisons without truncating either source
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-export.test.tsx

- 67 行；18 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：copies confirmed content and keeps clipboard failure recoverable；reads selected artifacts only and blocks delivery until loaded, with retry；reports failed downloads and allows retry；does not offer export for unconfirmed empty output；downloads a Markdown file containing provenance and confirmation status
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-history.test.tsx

- 42 行；11 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：loads package choices and preserves history context through a personal mark
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-metadata.test.tsx

- 64 行；14 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：reads without a write and submits only the explicit metadata field；retains a conflicting note draft and requires review of the newer version；retains an unsaved note across navigation and warns before refresh without browser persistence
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-rules.test.tsx

- 20 行；7 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：explains frozen conditions with field titles and preserves literal values；keeps nested fixed source code unchanged when showing mapping fallbacks
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-run-ux.test.tsx

- 117 行；21 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：opens an exact source operation through a readable link without showing execution envelopes；uses a frozen business title or effect label instead of protocol documentation: title=%s；inspects frozen input sources and confirmed upstream content without showing intermediate API values；uses the projected known failure in the execution header while leaving the model reply unpromoted；keeps %s step and operation status tones consistent
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-section-groups.test.tsx

- 100 行；23 处 expect；6 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：reads equal generic content once while retaining every source link and the original values；preserves separately authored sections even when their confirmed text is identical；uses exact typed equality without trimming strings or merging distinct list contents；copies and downloads the readable string once by default without quoting or fencing its text；retains deselected content while frozen display information finishes loading；waits for frozen display information before default delivery can include duplicates
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/result-view.test.tsx

- 501 行；72 处 expect；17 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：shows a confirmed receipt without exposing its raw service response and retains original input；explains a model failure while retaining the input-reuse and evidence destinations；shows body, missing information and provenance before technical evidence；preserves history filters through evidence selection, technical tabs and return；does not claim cancellation has stopped execution or unknown writes succeeded；reviews changed bindings before rerun and retains identity after an uncertain response；creates a fresh rerun command after moving to another result；keeps an uncertain rerun identity and binding while visiting its technical evidence；keeps uncertain reads visible and allows rerun without save verification；requires explicit verification before repeating an unknown write；opens only the explicitly projected frozen plugin link；recognizes the projected artifact reference and offers a download；reads a large JSON artifact without requiring technical evidence；refreshes from the first page with a new snapshot while retaining filters；keeps server filters and snapshot watermark when paging；keeps cancelled work distinct from failure and describes input reuse；recovers an uncertain rerun after refresh without persisting input or connection settings
- mock 边界：@/hooks/use-model-usage

## authoring

单一 YAML 文档、图依赖、映射、定义导入与评论保留、资源凭据与插件边界；读写断言各有合同

### frontend/src/pages/platform/budget-controls.test.tsx

- 59 行；15 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：keeps unlimited, service-controlled and inherited values distinct；batch edits preserve other per-agent fields and pending controls are locked；renders all budget modes and sources without protocol values or agent identities
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/connection-model.test.ts

- 18 行；6 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：normalizes a complete model address while retaining provider limits and unrelated saved settings；rejects unsupported or credential-bearing service addresses: %s；validates model names and execution limits before making a request；preserves arbitrary business scope while checking meaningful service limits
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/package-expert.test.tsx

- 123 行；36 处 expect；8 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：edits prompt, services and limits without replacing mappings, annotations or comments；adds reusable assistants, workflows and steps using generated identities；keeps an assistant in use and requires explicit confirmation before deleting an unused assistant；edits sources, dependencies, conditions and recovery with visible choices；retains imported comments and user instructions through source selection and repair；creates distinct new definitions and reports diagnostics without internal values；prevents deleting output sources but ignores literal text that happens to resemble a reference；supports zoom, keyboard movement and named steps while explaining all dependencies
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/package-mapping.test.tsx

- 86 行；16 处 expect；6 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：selects named source fields and any list position without displaying internal references；preserves a missing saved source until the user deliberately selects a replacement；keeps literal objects and composed objects distinct while editing a sibling value；does not confuse a business field named like a whole-object option with the whole object；reorders composed items without converting their nested values；edits a nested condition while retaining unrelated comparisons and all operator choices
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/package-presentation.test.tsx

- 87 行；16 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：does not materialize absent presentation settings before an explicit edit；changes a title without rewriting placeholders, section declarations or omitted options；creates distinct text hints and switches an input title through named fields；preserves unknown saved service links while another section changes；builds a named service result link and offers every supported result section
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/platform.test.tsx

- 361 行；52 处 expect；17 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：edits the same document without erasing nodes, comments or constraints；keeps unreadable imports without silently repairing or exposing source errors；adds a workflow through controls without replacing the other sections；uses the saved document rather than stale summary metadata；names authoring services from declared titles and safe effect labels without protocol descriptions；blocks editing when reading the saved workflow fails and offers recovery；shows all merged dependency sources and real terminal reasons；renders invocation ownership separately from the dependency graph；validates evidence deep links against the loaded run；inspects a planned node without inventing missing input or reporting an invalid evidence link；loads CAS text only on demand and clears an unrelated artifact selection；discovers nested CAS references without converting ordinary money strings；does not refill saved credential values and clears newly submitted credentials；does not echo credential values from rejected saves into diagnostics；takes business page links from enabled plugin releases and rejects executable URLs；edits exact string inputs without adding omitted optional values；refuses ambiguous duplicate keys instead of replacing a definition
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/plugins.test.tsx

- 37 行；11 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：imports an installation file, reviews capabilities and waits for explicit confirmation before registration；keeps a valid installation draft after an invalid file and provides a readable recovery
- mock 边界：@/hooks/use-workflow-platform

### frontend/src/pages/platform/resources.test.tsx

- 33 行；9 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：creates a named service through a form, manages its identity and clears credentials after save
- mock 边界：@/hooks/use-workflow-platform

### frontend/src/pages/platform/task-connections.test.tsx

- 104 行；25 处 expect；6 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：requires confirmation, preserves configuration, clears entered secrets and omits blank credentials；allows a missing model to be connected with an ordinary address and password form；keeps inputs and gives actionable local validation when the address is wrong；distinguishes loading and preset failures while preserving entered credentials；copies saved public connection settings without implying credentials were copied；retains the public draft across page remounts without browser storage
- mock 边界：@/hooks/use-workflow-platform, @/hooks/use-task-experience

### frontend/src/pages/platform/task-preparation.test.tsx

- 50 行；14 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：preserves arbitrary business values and avoids falling back to internal connection identifiers；shows current model observation without changing configuration readiness；identifies a budget-only change without describing it as a connection change；shows business scope and previous settings without exposing platform bindings or issues
- mock 边界：@/hooks/use-workflow-platform

### frontend/src/pages/platform/tasks.test.tsx

- 468 行；106 处 expect；19 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：shows the catalog authoring entry only in expert mode while keeping ordinary tasks；keeps a customized task discoverable in ordinary mode；restores and saves explicit preset input %j separately from a bookmark；retains an explicit historical null instead of the current schema default；shows effective settings automatically and starts with one user action；lets experts recheck ready settings without changing the ordinary task input；lets an automatic preparation failure be retried before starting；requires visible confirmation for automatically discovered binding changes；automatically exposes missing connections without starting or changing input；restores an uncertain submission after remount and retries the same identity without input edits；keeps business input and draft name through mode switches and editor return；lets an explicit binding rejection be repaired and prepared again；preserves explicit false and omitted schema/2 defaults when editing and saving a preset；commits pending identity before launch and restores it after a lost response in a new editor；does not send a launch if the pending draft cannot be persisted；restores an unfinished draft with its frozen schema and saves invalid text without launching；locks submission throughout pending persistence and keeps the lock across the recovery URL change；keeps a resumed unsaved draft locked while the launch response is still pending；keeps a %s input task discoverable from its catalog action
- mock 边界：@/lib/api/task-drafts, @/hooks/use-display-mode, @/hooks/use-results, @/hooks/use-workflow-platform, @/lib/api/task-experience, @/hooks/use-task-experience

## schedule

保留 cron/timezone/隐藏策略、同步与恢复、稳定触发身份；纯转换/组件/轮询层不可直接视为重复

### frontend/src/hooks/use-workflow-platform.test.tsx

- 68 行；12 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：invalidates run and schedule scopes after cancellation；polls only known active states, including a cancellation that is still running；updates failed schedule synchronization automatically after recovery and stops polling
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/schedule-calendar.test.ts

- 43 行；12 处 expect；6 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：round-trips %s without replacing untouched source；changes one selection while preserving other supported dimensions and notes；adds seconds and year controls without losing the five-field calendar；does not reinterpret invalid timing %s；preserves %s；retains the reference start when changing the interval
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/schedule-frequency.test.ts

- 31 行；5 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：preserves %s；retains unsupported timing %s；describes weekly timing without calculating dates
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/schedule-fire-history.test.tsx

- 64 行；8 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：distinguishes failed launch receipts from linked successful executions
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/schedule-list.test.tsx

- 37 行；4 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：retains an uncertain manual execution through leaving and returning
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/schedule-timing.test.tsx

- 85 行；15 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：preserves complex calendar and hidden policies while editing the timezone；marks an unavailable engine preview without changing the schedule；edits multiple execution hours without exposing an expression editor；shows authoritative pending preview without internal revisions or notes；edits a fixed interval and its reference time through ordinary controls
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/schedules.test.tsx

- 104 行；13 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：inherits business input and keeps one creation identity after an uncertain response
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

## shared

可复用组件语义、布局 token、ARIA 名称、键盘事件与容器隔离；jsdom 不验证真实像素/屏幕阅读器体验

### frontend/src/components/shared/console-section.test.tsx

- 39 行；7 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders heading, description, children, and isolated actions；applies tone and density classes deterministically
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/constraint-inspector.test.tsx

- 35 行；10 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders blocking, warning, and requirement states deterministically；renders ready state and empty buckets without route-specific copy
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/entity-dialog-shell.test.tsx

- 94 行；13 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：composes accessible dialog title, description, constraints, body, and footer；keeps fixed dialog chrome outside a viewport-constrained scroll body
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/error-boundary-fallback.test.tsx

- 41 行；10 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders app failures through an expanded responsive fallback layout
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/evidence-cluster.test.tsx

- 33 行；7 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders labeled evidence with tone badges and descriptions；renders deterministic empty and inline layouts
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/inline-state-panel.test.tsx

- 59 行；8 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders tokenized inline panel chrome with icon, copy, children, and custom class names；supports description-only danger copy without a title
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/inventory-page-shell.test.tsx

- 111 行；13 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders context, toolbar, filters, and content in the inventory order；leaves the filter region empty when callers have no active filter bar；leaves the toolbar region empty when callers move summary into compact route context；keeps route-owned content after shared controls instead of nesting controls in results
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/inventory-state-panel.test.tsx

- 70 行；10 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：keeps shared inventory copy inside tokenized state card chrome；keeps danger tone available for route-owned error copy；keeps long title-only error copy unclamped
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/markdown-content.test.tsx

- 20 行；9 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：preserves Markdown structure, ordered start, links and keyboard readable overflow；does not enable raw HTML or unsafe links
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/page-context-bar.test.tsx

- 177 行；24 处 expect；6 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders title, context metadata, status, and isolated actions；renders compact density as a flat unboxed header；places the H1 and description in the same responsive row；keeps toolbar status and actions in the right-side area；can place toolbar metadata between title copy and status when requested；allows a multi-action group to wrap within the available header width
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/resource-actions-menu.test.tsx

- 62 行；4 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders a consistently labelled row action trigger；keeps route-owned action callbacks in the caller；supports route-specific trigger variants and content sizing
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/resource-bulk-actions-bar.test.tsx

- 65 行；7 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders nothing when no resources are selected；renders selected-count summary and route-owned action callbacks；allows callers to provide a route-specific summary
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/resource-selection-checkbox.test.tsx

- 76 行；5 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：maps aggregate selection state to checked, mixed, and unchecked values；renders an accessible checkbox label；converts checked-state changes back to booleans for callers
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/resource-status-strip.test.tsx

- 66 行；9 处 expect；4 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders status items with deterministic tone badges；renders numeric zero values without showing empty falsy values；renders deterministic empty status copy；exports a reusable status badge helper for shared callers
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/resource-table-frame.test.tsx

- 51 行；3 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：wraps route-owned tables in a framed horizontally contained shell
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/resource-toolbar.test.tsx

- 95 行；9 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders compact search controls with caller-owned handlers；keeps filter affordances, actions, and selection summary presentational
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/shared/workspace-page-shell.test.tsx

- 85 行；16 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：places sticky context, optional rail, and scroll body in shell-owned regions；keeps consumer-owned workspace content inside the body region；renders without a left rail and keeps body as the only content region
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/plugin-ui/index.test.tsx

- 44 行；13 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders platform Markdown structures without executing HTML or fetching images；cancels without confirmation and returns focus to the invoking control；resolves a confirmed deletion exactly once
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

## shell

路由注册、导航、模式、错误与主题；导入 smoke 和用户操作合同不同，保留

### frontend/src/App.test.tsx

- 42 行；3 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：mounts the sonner toaster in the top-right with rich colors
- mock 边界：react-router, sonner, ./components/theme-provider, ./routes

### frontend/src/components/layout.test.tsx

- 68 行；11 处 expect；3 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：owns generic navigation without statically compiling finance pages；gives the definition editor a full-height route shell；does not restore historical product entry points
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/components/theme-provider.test.tsx

- 17 行；3 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：updates the visible theme when another tab changes its preference
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/not-found.test.tsx

- 62 行；16 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders the product-owned route fallback through a responsive full-page layout
- mock 边界：react-router

### frontend/src/pages/route-error.test.tsx

- 98 行；20 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders unexpected render failures through a readable responsive error layout；renders route response failures without the default router error UI
- mock 边界：react-router

### frontend/src/routes.test.tsx

- 107 行；2 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：renders every registered route without crashing
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

## other

显示偏好、查询键、hook 选择状态与日期/数值格式；不同边界和公共调用行为保留

### frontend/src/hooks/use-model-usage.test.tsx

- 23 行；6 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：uses the selected IANA local date on each side of midnight and DST；requests only the day summary when no run is selected
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/hooks/use-resource-filter-state.test.ts

- 73 行；10 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：filters caller-supplied items with normalized search text；lets callers combine search and arbitrary filter predicates
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/hooks/use-resource-selection-state.test.ts

- 76 行；18 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：toggles selected ids, item batches, and reset state；derives selected counts from the caller-supplied visible items
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/hooks/use-unsaved-work.test.tsx

- 19 行；2 处 expect；1 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：protects unsaved edits from refresh and releases protection after saving
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/display-preferences.test.ts

- 63 行；24 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：round trips preferences while retaining business links and existing timezone；retains only the validated platform origin across plugin navigation and refresh；rejects credentials, non-http URLs and return locations containing business paths；retains in-memory preferences if storage rejects writes；updates mounted expert controls when another tab changes display preferences
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/format.test.ts

- 98 行；20 处 expect；5 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：formats currency, decimals, and percentages across common inputs；formats ISO date and datetime strings；formats ISO instants in an explicit IANA timezone with a short zone suffix；formats compact numbers and preserves sign；returns safe fallbacks for invalid numeric input
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/lib/query-keys.test.ts

- 31 行；11 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：isolates resource families and keeps detail/list under one invalidation scope；keeps usage windows and execution update filters distinct within their scopes
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。

### frontend/src/pages/platform/feedback.test.tsx

- 25 行；7 处 expect；2 个静态测试声明（参数展开以运行结果为准）。
- 决策：保留，除实验报告明确列出的三处候选外未实验。
- 风险/行为节点：offers conflict recovery without exposing transport details；keeps uncertain operations cautious without revealing a provider exception
- mock 边界：未发现 vi.mock 模块替换；可能使用 vi.stubGlobal/组件 fixture，见原测试与 boundaries 提取。
