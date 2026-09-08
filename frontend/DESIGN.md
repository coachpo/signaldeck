# SignalDeck 设计系统

## 目的

SignalDeck 是一个用于 Workflow Package、Agent 定义、资源绑定、Scheduled Task、Run 和 Plugin 目录的高密度管理界面。Finance 的 Template 和 Report 由独立插件页面拥有。设计系统在不改变产品行为的前提下保持这些页面一致。当前视觉语言是紧凑企业后台：灰白画布、细分隔线、约 14px 正文、统一 4–6px 圆角、表格优先和清晰键盘 focus。普通模式默认使用任务、结果与设置；专家模式增加制作和诊断入口，切换只改变展示，不改写业务配置或卸载当前草稿。

## 系统层次

- `src/styles/theme.css` 是 token source of truth。自定义 surface、间距、布局、shadow、motion、z-index、control sizing 和状态值使用 semantic Tailwind class 与 `--ui-*` token。
- `src/components/ui` 包含 shadcn/Radix primitive，保持 presentational，不放 route 或 API logic。
- `src/components/shared` 包含可复用 SignalDeck UI：page shell、toolbar、state panel、status chrome、table frame、dialog 和 management-list helper。
- feature folder 与 page 拥有 domain copy、route params、hooks、mutation、toast、navigation 和 validation behavior。

## Token

产品颜色使用现有 semantic token：`background`、`foreground`、`card`、`muted`、`accent`、`primary`、`destructive`、`border`、`positive`、`negative`、chart 和 sidebar colors。`text-positive` 与 `text-negative` 只用于清晰的金融变动。

翻新的 surface model 使用 `bg-ui-canvas`、`bg-ui-surface`、`bg-ui-surface-elevated`、`bg-ui-surface-grouped`、`bg-ui-surface-inset`、`bg-ui-surface-chrome`、`border-ui-separator`、`text-ui-text-secondary`、`text-ui-text-tertiary`、`bg-ui-accent-soft` 和 `shadow-ui-*`。它们映射到 `--ui-*` token，保持 light/dark 行为一致。

组件需要 Tailwind semantic utility 没有的值时使用 `--ui-space-*`、`--ui-shadow-*`、`--ui-z-*`、`--ui-motion-*`、`--ui-breakpoint-*`、`--ui-layout-*` 和 `--ui-size-*`。不要创建第二个 token 文件。

## 布局规则

- `Layout` 负责 app shell、sidebar、breadcrumb、scroll mode、full-height mode 和 route width。
- inventory route 使用 `InventoryPageShell`、`PageContextBar`、`ResourceToolbar`、可选 `ResourceFilterBar` 和 route-owned content。
- full-height editor 与 console 使用 `WorkspacePageShell`。
- 可检查的 source/detail 工作区使用 `WorkspacePageShell`，由 feature 组合 source 与详情布局；结构化值和原始 JSON 分别复用 `StructuredValueInspector` 与 `ExactJsonPreview`。
- 避免嵌套 page shell 和 route-local top-level layout wrapper。

## 组件规则

- Button 使用 `Button`；icon button 必须有 accessible label。
- button 内的 icon 尽量使用 `data-icon`。
- destructive confirmation 使用 `ConfirmDeleteDialog`。
- selected-count delete/clear bar 使用 `ResourceBulkActionsBar`。
- row overflow menu 使用 `ResourceActionsMenu`；调用方仍拥有 menu item、callback、navigation 和 destructive variant。
- selectable management table 使用 `ResourceSelectionCheckbox`。
- 普通 resource list 使用 `useResourceSelectionState` 管理 selected ids、selected items、selected count、全选/部分选择和 clear selection。
- inventory search 使用 `ResourceToolbar.search`，active filter 使用 `ResourceFilterBar`。
- route-level empty/error/loading 使用 `InventoryStatePanel`；inline notice 使用 `InlineStatePanel`；card-like empty state 使用 `EmptyStatePanel`。这些是 solid grouped/elevated surface，不使用 dashed container。
- table 使用 `ResourceTableFrame` 包裹 route-owned table markup；route 自己负责 columns、sorting 和 pagination。
- status 使用 `ResourceStatusBadge` 和 `ResourceStatusStrip`，不要在 route 中直接拼 colored span。

## 表单与对话框

submit handler、mutation、navigation 和 toast 留在 page 或 owning feature component。shared form shell 接收 values、callback、label、description 和 validation message。

创建/编辑 dialog 使用 `EntityDialogShell`；只有确认动作的 destructive flow 使用 `ConfirmDeleteDialog`。

## 样式规则

- 优先使用 semantic class 和翻新的 surface token：`bg-ui-canvas`、`bg-card/95`、`bg-ui-surface-grouped`、`bg-ui-surface-inset`、`text-foreground`、`text-muted-foreground`、`border-border/70`、`shadow-ui-xs`、`shadow-ui-md` 和 `text-destructive`。
- 优先使用 `flex` 或 `grid` 配合 `gap-*`；不要新增 `space-x-*` 或 `space-y-*`。
- 方形 control 优先使用 `size-*`。
- 不引入新的 UI library、styling framework、route-local theme 或装饰性 variant。
- 管理页面在 375px、768px、1024px 和 1440px 宽度保持紧凑、可读和稳定。
- 不新增 route-local `rounded-md border bg-muted/20`、`bg-muted/30`、dashed empty container 或一次性 `shadow-sm`/`shadow-md` page chrome；使用 shared component 或 `shadow-ui-*` token。dashed stroke 只用于 chart marker 等数据可视化 affordance。

## 迁移检查清单

- 保持 route behavior 和 data flow 不变。
- 先替换复制的 page chrome，再替换 shared shell。
- 随后替换复制的 search/filter/bulk/state/table/dialog pattern。
- 只把 presentational behavior 移入 shared component。
- 所有 import 迁移后删除 obsolete local helper。
- 先运行 focused test，再运行 lint、typecheck、unit test 和 build。
