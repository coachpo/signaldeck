# SignalDeck 设计系统

界面风格是简约紧凑的企业管理后台和工程师工具：灰白画布、细分隔线、约 14px 正文、统一 4–6px 圆角、表格优先和清晰的键盘 focus。所有模式和插件页面的界面内容遵守[产品界面合同](../docs/产品说明.md#产品范围)；本文件只规定视觉系统和组件用法。

## 系统层次

- `src/styles/theme.css` 是唯一的 token 来源，不创建第二个 token 文件。
- `src/components/ui` 是项目自有的 shadcn/Radix primitive，保持纯展示，不放路由或 API 逻辑。仓库没有 `components.json`，shadcn CLI 的 registry 命令不能直接使用。
- `src/components/shared` 放可复用的 SignalDeck UI（页面外壳、工具栏、状态面板、状态标记、表格框和对话框），同样只做展示：值、回调、标签、说明和校验信息由调用方传入。页面和 feature 目录拥有业务文案、路由参数、hooks、提交处理、mutation、toast、导航和校验。
- 插件页面通过 `src/plugin-ui` 构建入口复用主题、侧栏、Markdown、确认框和外观控件；插件自己的业务表单也只使用同一组语义 token，不另建主题。独立打开时显示完整布局，嵌入主站时只渲染业务内容，导航和外观由主站提供；嵌入协议见[统一插件页面](../docs/writing-extensions.md#统一插件页面)。

## Token

- 颜色使用语义 token：`background`、`foreground`、`card`、`muted`、`accent`、`primary`、`destructive`、`border`、`positive`、`negative`、chart 和 sidebar。`text-positive` 与 `text-negative` 只表达清晰的金融涨跌。
- Surface 使用 `bg-ui-canvas`、`bg-ui-surface`（及 `-elevated`、`-grouped`、`-inset`、`-chrome` 变体）、`border-ui-separator`、`bg-ui-accent-soft` 和 `shadow-ui-xs|sm|md|lg`，它们映射到 `--ui-*` 变量并保持 light/dark 一致。`--ui-text-secondary` 和 `--ui-text-tertiary` 没有对应的 utility class，只能通过 `var()` 引用。
- 语义 utility 表达不了的值使用 `--ui-*` 变量，例如 `--ui-space-*`、`--ui-radius-*`、`--ui-shadow-*`、`--ui-z-*`、`--ui-motion-*`、`--ui-layout-*` 和 `--ui-size-*`。

## 布局

- `Layout` 按路由 handle 负责 app shell、侧栏、面包屑、滚动模式和宽度。
- 管理列表路由使用 `InventoryPageShell`：它渲染 `PageContextBar`，可选组合 `ResourceToolbar` 和 `ResourceFilterBar`，自身不提供滚动，只能用于由 `Layout` 提供滚动区域的滚动模式路由。
- `fullHeight` 路由（`routes.ts` 中的 `fullHeight: true`，如工作流编辑、开始任务、重复安排和结果详情）没有 `Layout` 滚动区域，页面必须使用正文自带滚动的 `WorkspacePageShell`，否则首屏以外的内容无法到达。
- 不嵌套页面外壳，不在路由里另包顶层布局。

## 组件

| 场景 | 使用 |
| --- | --- |
| 按钮 | `Button`；图标按钮必须有可访问名称，按钮内的图标尽量加 `data-icon` |
| 破坏性确认 | `ConfirmDeleteDialog`，只用于确认动作 |
| 列表搜索与筛选 | `ResourceToolbar` 的 `search`；已生效的筛选用 `ResourceFilterBar` |
| 空、错误和加载状态 | 路由级用 `InventoryStatePanel`，行内提示用 `InlineStatePanel`，卡片式空状态用 `EmptyStatePanel`；三者都是实色卡片，不用虚线框 |
| 表格 | `ResourceTableFrame` 包裹路由自己的表格；列、排序和分页由路由负责 |
| 状态 | `ResourceStatusBadge` 和 `ResourceStatusStrip`，不在路由里直接拼彩色 span |
| Markdown 正文 | `MarkdownContent`（样式为 `theme.css` 的 `.markdown-preview`）：保留标题和列表层次，表格和代码块在自身区域滚动并可键盘聚焦，链接始终带下划线；链接和图片策略由各入口通过 `components` 决定。JSON 附件和结构化值按原值显示，不当作 Markdown |

## 样式

- 优先使用语义 class；布局用 `flex` 或 `grid` 配合 `gap-*`，不新增 `space-x-*` 或 `space-y-*`；方形控件用 `size-*`。
- 不引入新的 UI 库、样式框架、路由级主题或装饰性变体。
- 不在路由里自造 `rounded-md border bg-muted/20`、`bg-muted/30`、虚线空容器或一次性的 `shadow-sm`/`shadow-md` 页面外框，改用 shared 组件或 `shadow-ui-*`。虚线只用于图表标记等数据可视化。
- 管理页面在 375px、768px、1024px 和 1440px 宽度下保持紧凑、可读和稳定。
