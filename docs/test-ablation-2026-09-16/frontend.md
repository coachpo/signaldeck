# Frontend src 消融实验与测试精简结果

## 范围、环境、基线

- `frontend/vite.config.ts`: Vitest 4.1.11，jsdom，globals，CSS 关闭，匹配 `src/**/*.{test,spec}.{ts,tsx}`。CI frontend-quality 与 CONTRIBUTING 运行 lint/typecheck/build/test:run；E2E 属于独立代理。
- 84 个测试文件，8,160 行，静态 1,353 个 `expect` 调用；参数展开后的原始全量 428 用例。没有 Vitest 快照、已有变异框架或实际安装的 coverage provider，未生成/冒充覆盖率。
- 公共 fixture：`src/test/setup.ts`（ResizeObserver、matchMedia、IntersectionObserver、scrollIntoView、固定 DOM 尺寸）；`src/pages/platform/fixtures.ts`（packageFixture/runFixture）。测试大量 mock fetch/feature hook，真实 HTTP/backend、视觉像素和屏幕阅读器不是 jsdom 结论范围。
- Node 24.17.0；仓库根目录全局 pnpm 为11.15.1，最终在新工作树 frontend/ 明确执行 `pnpm --version` 为10.30.1，符合 packageManager 固定值。不同于 CI 操作系统及其资源环境。
- 原始 `pnpm test:run`：84 文件，427 passed / 1 failed，68.17s。失败 `result-history.test.tsx > loads package choices and preserves history context through a personal mark`（5,000ms timeout），任何前端改动前已存在。
- 初始 `pnpm test:run --maxWorkers=2` 在系统多任务资源争用期间出现不同超时；按统一队列终止，记录为 aborted，不作为完整失败/耗时样本。没有放宽超时、断言或 skip。
- 初始 UI full/reduced 前两次 33.450s/67.193s 亦受争用污染，不用于提速结论。日志保留为诊断证据。
- 全部文件风险初筛与静态行为节点见 `/tmp/signaldeck-frontend-risk-inventory.md`，机器盘点 `/tmp/signaldeck-frontend-inventory.json`，mock/storage/timer 边界 `/tmp/signaldeck-frontend-test-boundaries.txt`。仅下面列出的候选有消融实验；其他范围保留，不声称已消融。

## 已读约束

根任务 AGENTS 指令、frontend/AGENTS、frontend/src/pages/platform/AGENTS、frontend/src/lib/platform-authoring/AGENTS、CONTRIBUTING、产品 UI/解耦合同、前端开发规范、架构边界、DESIGN。风险包括公开包/Agent合同、输入显式值语义、UI 操作与布局可访问名称；不同层执行相同代码不视为可互换。

## 实验设计

隔离副本 `/tmp/signaldeck-front-frozen/frontend` 使用初始提交 `7c4bcbcf87adce626fcf6fe7dc1ef23e98538a02` 的完整 frontend 归档（原临时副本 src 与其逐字节一致），符号链接已安装 node_modules；临时故障只在副本，try/finally 原文恢复。脚本 `/tmp/signaldeck-frontend-experiment.py`。真实源码与用户修改不受故障影响。

UI 组完整10例，组合候选7例：
1. `resource-selection-checkbox.test.tsx` 删除独立 accessible-label 用例；剩余状态转换和交互通过 `getByRole(checkbox, name)` 本已验证调用方可访问名称。
2. `workspace-page-shell.test.tsx` 删除重复内容容器用例；首例已验证 body 包含用户内容、rail 不包含，另外无rail用例仍保留。
3. `inventory-page-shell.test.tsx` 把内容隔离、容器包含与 DOM 顺序断言合并进已有无filter用例，保留有filter/无filter/无toolbar三个分支；不把无filter断言仅合并到有filter输入，避免条件组合盲点。

同一11个UI故障逐一应用完整与组合精简组：丢失checkbox名称、丢失mixed状态、反转选择回调、丢失workspace内容、workspace内容落入rail、丢失workspace滚动类、丢失inventory内容、inventory内容落入toolbar、仅无filter时丢失内容、丢失toolbar、丢失filter。

API 组两文件（workflow-platform + task-experience），尝试把6种非对象参数组合减为 false/[]。对比 null被默认值替换、number变string、schedule非空数组被清空、只读schedule投影泄漏及trim字符串五故障。即使 null/0/数组进入相同 JSON 序列化代码，也验证不同契约；若精简遗漏故障则保留全部组合。

全组执行同样11+5样本，无故障control验证完整/候选均通过。记录每个故障 full/reduced 失败节点；原组未检出的故障只能表述为此局部测试组的样本覆盖缺口，不能据此证明整仓库无覆盖。


## 最终实现与结论

本次前端永久改动仅在独立工作树 `/Users/qingli/Documents/ChatGPT/signaldeck-test-ablation-20260916`，基础提交 `7c4bcbcf87adce626fcf6fe7dc1ef23e98538a02`；原共享工作区未写入这4个测试文件。无产品代码、配置、依赖或fixture修改，无skip、放宽超时/断言/容差、快照更新。

| 测试位置 | 精简/加强方式 | 保留的断言与实验依据 |
| --- | --- | --- |
| `frontend/src/components/shared/resource-selection-checkbox.test.tsx` | 3→2，删独立accessible-label重复用例 | 状态测试和交互测试本已通过角色+调用方名称定位checkbox；丢名称、丢mixed状态、反转回调三故障都仍检出 |
| `frontend/src/components/shared/workspace-page-shell.test.tsx` | 3→2，删重复内容容器用例 | 首例保留body包含/rail不包含及滚动/区域顺序；无rail分支保留；内容丢失/落入rail/失去滚动类三故障仍检出 |
| `frontend/src/components/shared/inventory-page-shell.test.tsx` | 4→3，将第四例包含/隔离/顺序断言合入无filter例 | 保留原第四例Create action输入；有filter/无filter/无toolbar三分支仍存在；五故障（含仅无filter丢内容）均检出 |
| `frontend/src/lib/api/workflow-platform.test.ts` | 拒绝把6种非对象参数减为false/[]；保留全组合，新增含前置空白及换行的根字符串 | 去参数候选漏检null默认替换、number转string、非空数组清空。新增字符串案例补齐此API局部组对trim故障的盲点，同时验证手动与schedule写入 |

共享UI完整组10例→最终7例，在同一11个样本下11/11检出；API两文件组13例→14例，原组4/5、候选精简组1/5，最终5/5。合计同16样本原组15/16→最终16/16。原API组没有检出trim故障的原因确实是缺少非空根字符串：临时direct probe用合法根字符串 `"  source text\n"` 调用真实launch transport，原实现通过、trim故障失败。该probe已移除，回归输入进入现有参数表。这里的检出率仅描述这两个局部组及16个样本，不能推广为整仓库变异分数或绝对等价证明。

共同移除已通过整个3文件UI组验证，并重新针对保留Create输入的确切最终候选执行全部11个UI故障；最终API表也重新执行全部5个API故障。字段格式收尾不改变故障组语义，格式后的完整测试及静态检查通过。

84文件全部纳入入口/配置/fixture/测试行为节点/风险初筛和完整执行。实际故障消融只覆盖上述3个UI文件和2个API文件；其余79文件均保留，未做故障消融，不宣称其覆盖等价。耗时较高的package-expert、schedule-timing、tasks、routes、result-view、platform、package-mapping、package-presentation等范围保留：它们验证编辑保持、异步恢复、路由注册或冻结结果等不同契约，不能凭同路径或耗时删除。UI类名断言也没有仅因绑定实现细节就删除，因为jsdom固定尺寸无法替代真实布局证据。

## 完整验证与性能数据

以下完整前后均在新独立工作树、同一产品源码及独立已安装依赖下运行，命令完全一致（含同一个JSON输出路径；每轮归档后再覆盖）：

`cd /Users/qingli/Documents/ChatGPT/signaldeck-test-ablation-20260916/frontend && pnpm test:run --maxWorkers=2 --reporter=json --outputFile=/tmp/signaldeck-frontend-measure.json`

| 项目 | 原版 | 最终 |
| --- | --- | --- |
| 文件 | 84 | 84 |
| 用例 | 428 | 426（删3个重复声明、加1个参数边界） |
| 第1轮墙钟 | 87.974s，全过 | 69.808s，全过 |
| 第2轮墙钟 | 57.503s，全过 | 85.388s，全过 |
| 中位墙钟（2轮） | 72.7385s | 77.598s |

全量没有证明运行时间改善，波动大于本次少量用例调整的预期收益；不得把前后均值/中位差直接归因精简。明确收益是去除重复的fixture/render/断言维护，同时增加一个真实发现的序列化边界。前述初始默认并发的result-history超时在冻结原版和精简版这4轮均未复现；这不证明不稳定性已彻底排除。

最终3文件UI组另做3对相同命令/环境的局部计时，中间一对颠倒full/reduced顺序：原版[5.787,5.978,4.124]s，中位5.787s；精简[5.567,5.465,2.498]s，中位5.465s。累计用例执行时间中位613.734ms→524.722ms（不含环境启动等成本）。局部墙钟下降0.322s，但样本少且波动明显，不能据此宣称稳定全量提速。

原版与最终 `pnpm lint`、`pnpm typecheck`、`pnpm build` 均通过。最后格式收尾后再次执行三项均通过。`git diff --check` 通过。未发现/安装现成覆盖率provider，未采集覆盖率；没有以行覆盖作为删减依据。Vitest范围无快照、axe/pa11y或真实视觉回归断言；可访问性结论仅限角色/名称/焦点/键盘等已有DOM断言，视觉和完整体验结论由各自已有自动化范围决定，不由这些单元测试推导。

## 可复核证据索引

- 实际展开的428原始节点：`/tmp/signaldeck-frontend-before-nodeids.json`；最终426节点：`/tmp/signaldeck-frontend-after-nodeids.json`；精确3删1增：`/tmp/signaldeck-frontend-node-delta.json`。
- 原始完整结果：`/tmp/signaldeck-frontend-before-full-1.json`、`/tmp/signaldeck-frontend-before-full-2.json`；最终完整结果：`/tmp/signaldeck-frontend-after-full-1.json`、`/tmp/signaldeck-frontend-after-full-2.json`。
- 全量执行命令、墙钟和失败列表：`/tmp/signaldeck-frontend-validation-results.json`。最终格式后门禁：`/tmp/signaldeck-frontend-final-quality.json`。
- 确切最终UI组3对计时原始JSON：`/tmp/signaldeck-frontend-final-timing-results.json`。
- 完整/候选/最终每个故障的失败节点：`/tmp/signaldeck-frontend-fault-matrix.json`；16个源变异的精确替换描述：`/tmp/signaldeck-frontend-experiment-spec.json`。
- 最终11 UI故障：`/tmp/signaldeck-frontend-final-ui-results.json`；最终5 API故障：`/tmp/signaldeck-frontend-final-api-results.json`；direct probe原/故障结果：`/tmp/signaldeck-frontend-trim-probe-original.json`、`/tmp/signaldeck-frontend-trim-probe-trim-fault.json`。
- 84文件风险与静态节点清单：`/tmp/signaldeck-frontend-risk-inventory.md`；每文件完整基线计数/执行时间：`/tmp/signaldeck-frontend-file-baseline.json`。
- 四个最终测试的初始/最终SHA256和行数：`/tmp/signaldeck-frontend-final-manifest.json`。

## 最终文件指纹

| 文件 | 最终SHA256 | 行数原→现 |
| --- | --- | --- |
| `frontend/src/components/shared/inventory-page-shell.test.tsx` | `cc2bb3bdcab6b617d540f8adf955d0868fd354837eaeb1bf79a10f443d962e82` | 111→98 |
| `frontend/src/components/shared/resource-selection-checkbox.test.tsx` | `15738b836a385ef3004ab271d64bad8e0084cd8a74d561b2d689073763b26cc2` | 76→62 |
| `frontend/src/components/shared/workspace-page-shell.test.tsx` | `26079d6acecff755682f4b758e967b4b26656e616a9fc552080976b80ee74e3e` | 85→67 |
| `frontend/src/lib/api/workflow-platform.test.ts` | `02635f4cde508727e47b70a149a11cda5fc92c472abf6aeb612252fa9b8f2717` | 124→132 |

已确认四个测试以外的frontend/src文件与基础提交逐字节一致；故障只在临时副本，最终副本源码恢复。临时probe、故障源码副本及实验Python脚本已清理，保留日志/JSON证据。
