# 插件与非默认实验入口盘点、局部消融（2026-09-16）

## 范围与执行

已读取根 AGENTS.md（会话）、CONTRIBUTING.md、plugins/README.md、plugins/finance/README.md、backend/experiments/ablation/README.md 和三引擎 README；plugins 与 experiments 下没有更近 AGENTS.md。没有修改仓库文件，没有删除测试，没有提交。Finance 测试使用文档允许的显式 TEST_DATABASE_URL 指向项目独立测试 PostgreSQL 的 25432；每项创建 UUID 数据库且清理。未操作运行中的应用数据。

| 入口 | 数量 / 默认 CI | 风险与覆盖判断 | 本轮执行 / 消融 |
|---|---|---|---|
| plugins/finance/tests/authoring.mjs | 1 个 Node 脚本，6 条顶层 assert；CI 未显式调用 | 原始声明精确往返、正文修改、代码区展示保护、中文必填声明、输入表达式、安全失败文案 | 基线通过；下述同故障完整/候选实验，候选否决 |
| plugins/finance/tests/test_finance_ux.py | 5 pytest 项；backend cwd 普通 pytest 不收集仓库外 plugins 测试；CI 未显式调用 | 历史字面子串/筛选/分页/稳定排序；可选输入/下载/报告 ID 与 slug/预览引用变更冲突/格式变更冲突/旧报告不变；编译诊断/404；业务标签与存储身份；真实浏览器 | 全 5 项通过，30.67s，一次基线；未改动，不声称 HTTP/浏览器完成测试消融 |
| plugins/finance/tests/browser.mjs | 上述第 5 pytest 调用的一条连续浏览器场景，不能再次计入 pytest 数量 | 真实 Finance HTTP + PostgreSQL + Chromium；普通/专家模式、必填有效性、草稿往返、生成/保存/上传/删除锁定、失败解锁、取消确认不写入、深链接/刷新/下载/第二页历史、404、Markdown结构、4视口宽度无横向溢出、私有字段不显示、pageerror | 浏览器 call 14.74s、构建/fixture setup 6.23s；随 5项基线通过；保留 |
| plugins/notes/tests/browser.mjs | backend/tests/test_notes_browser.py 包装 1 项，已包含 backend CI / backend agent 基线 | 初次加载禁用控件、主题/平台导航、响应布局、来源标题与正文、复制、返回/刷新、来源失败恢复 | 避免再次启动，由 backend agent 汇总；未消融，保留 |
| plugins/tests/image_smoke.py | 1 独立容器脚本，3 镜像；CI 未显式调用 | 真实打包依赖/入口、Finance HTTP 编译和 MCP 写/查、Notes MCP 写/查、Oracle 发布描述；与进程内测试有相似合同，但镜像包装是独有边界 | 未运行：要求 signaldeck-finance:sd-target-001、signaldeck-digital-oracle:sd-target-001、signaldeck-notes:sd-target-001 全部不存在；现有 local/ui-validation 不能冒充该冻结镜像；未完成消融，保留 |
| backend/experiments/ablation/test_cache_retry.py, test_limiter.py, test_ownership.py, test_dag.py | 5测试函数、11场景×2机制变体×5默认样本=110项；须 --run-ablation，默认不收集，CI未调用 | 缓存重复/唯一负对照、正常/暂时/持续失败重试、正常/突发限流、正常/重复重叠独占、分支/链DAG；真实 Gateway/PG/Temporal，机制有无的因果证据 | 补充执行：独立 worktree 中现有默认110项全通过，111.42s；每场景/变体5样本，source_drift=[]，exit_status=0，汇总器完整性校验通过。其“ablated”改变产品机制，并非移除测试，因此此结果仅为既有机制实验基线，不是测试集删减证明。所有场景和5次重复保留 |
| backend/experiments/engines/temporal/probe.py | 1入口，配套runtime/worker及独立hash锁文件；默认CI不跑 | 历史冻结目标 T06/A16 引擎比较：真实服务、SIGKILL恢复、调用级计数、冻结制品、动态schema、DAG、取消、deadline | 未重新运行/未测试消融；17233可能与 E2E 冲突；独立环境与实验性结果不能替代当前产品回归。保留 |
| backend/experiments/engines/prefect/run.sh | 4子探针 probe.py, crash_ownership_probe.py, auto_recovery_probe.py, cancel_probe.py；独立requirements.lock | 手动恢复与默认崩溃负对照、automation恢复、真实取消；不是4份重复恢复测试 | 未运行/未消融，需独立固定依赖和server；当前产品Temporal-only不意味着可删历史比较证据，保留 |
| backend/experiments/engines/hatchet/run.sh | 1 run_probe.py执行入口，engine.py/probe.py支撑；独立requirements.lock | 实际 sidecar/PG、durable/call workers、SIGKILL、动态schema、DAG/取消边界；退出0含预期负面发现 | 未运行/未消融；需独立引擎下载和运行环境，保留 |
| docker/verify_target_stack.py | 1 独立Compose验收脚本；CI未显式调用 | 真正多容器拓扑、不可变大产物digest/size、幂等启动、模型/报告/计划4条run、秘密投影、历史读取 | 未运行/未消融。需新隔离完整Compose栈和evidence输出；现有用户应用不能直接写入验收数据。保留，由主任务/auxiliary报告统一归类 |
| docker/inspect_target_ui.mjs | 1 独立浏览器验证，输入上项4run的compose.json | 冻结部署的节点图、调用树父子关系、快照、产物读取、凭据投影、Finance不可变报告；pageerror/外部请求检查 | 未运行/未消融，缺本轮隔离Compose evidence；已有静态英文Finance选择器不能推断现行通过。保留 |

截图说明：Finance 与 Notes 脚本以及 docker UI 检查输出截图，未发现这些入口包含像素基线差异比较或自动截图容差断言。页面语义role/label选择器验证部分可访问语义，Finance原生必填校验和布局无溢出验证局部行为；没有系统axe扫描。截图不是视觉回归通过，浏览器通过不是完整UI/UX体验验证。

## 实际同故障配对实验：Finance authoring

低成本脚本中，“原始字节精确往返”与“代码表达式在编辑器可见文本中不改写”看似被“修改正文再序列化”覆盖，因此临时同时去除这两条断言作为候选。其余4条断言不变。临时目录复制真实 authoring.js 和测试，变异仅发生在副本；每个变体/故障运行3次，同一故障用于完整6断言和候选4断言。临时副本通过 TemporaryDirectory 自动清理。

| 定向故障 | 完整6断言 | 候选4断言 | 检测归属 |
|---|---|---|---|
| mapProse 不再保护 inline code，使编辑器把代码里的 {{inputs.keep}} 变成可读token | 3/3 检出 | 0/3 检出 | 删除的 visible 断言独有；序列化可恢复token，所以只比较最终正文漏检 |
| 未修改草稿快路径返回 original.trim()，丢失原始尾换行 | 3/3 检出 | 0/3 检出 | 删除的精确往返断言独有；修改正文路径不经过此快路径 |
| addField 将 required 保存为 optional | 3/3 检出 | 3/3 检出 | 保留的声明断言 |
| financeError 直接返回服务端 code | 3/3 检出 | 3/3 检出 | 保留的安全失败文案断言 |

无故障完整/候选各3/3通过。组合移除后故障检出由4/4下降为2/4，拒绝候选，6断言全部保留。结果仅适用于这4个故障样本，不能推断绝对充分性。

无故障完整3次耗时中位数0.193s，候选0.238s；受到并发主套件宿主机负载影响，样本量少，不解释为候选变慢或任何性能收益；最终没有改动故不声称有前后优化。JSON保留各次原始耗时和错误输出。没有已有coverage配置或本轮插件coverage测量。

## 留存证据

- /tmp/signaldeck-finance-baseline.log：5 passed in 30.67s，逐项duration
- /tmp/signaldeck-finance-authoring.log：Node独立基线成功
- /tmp/signaldeck-authoring-ablation.json：10组（5故障状态×2变体）×3次，故障结果、全部原始耗时、stderr
- 实验脚本执行后删除，临时源码副本已清理；仓库未注入任何故障。

本范围实施精简：0文件/0测试/0断言。未运行入口和仅盘点范围不认定完成消融。跨层看起来重复的Finance HTTP、真实浏览器、镜像包装以及历史引擎探针保留，未将不能运行作为删除证据。


## 后续补充：既有机制实验完整执行

在 `/Users/qingli/Documents/ChatGPT/signaldeck-test-ablation-20260916/backend`，待其它 backend 写入及重型验证结束后执行：

```sh
uv run --frozen pytest experiments/ablation --run-ablation --ablation-samples=5 --ablation-output=/tmp/signaldeck-mechanism-baseline.json -q
uv run --frozen python experiments/ablation/summarize.py /tmp/signaldeck-mechanism-baseline.json /tmp/signaldeck-mechanism-summary.md
```

110 passed in 111.42s；110 outcomes 与110 measurements，11场景×2变体×5次，退出0，无失败/跳过。源码指纹前后无漂移（source_drift=[]），现有汇总器完整性与配对检查通过。这里只运行了现有机制实验；没有临时删减该组测试，所以不能声称本组完成测试集消融或证明其可删除。总体运行一次，各机制样本按照现有设计交替顺序重复5次；与 Finance 基线位于不同工作树，不作跨环境耗时比较。

结束后只读检查项目测试PG不存在 `signaldeck_test_*` 临时库；本次 pytest 及其 Temporal 子进程已退出，原有17233/17234两个孤儿E2E服务保持原样，未清理非本次拥有资源。PG容器仅复用，未停止。源码/测试未修改，没有新增变异残留。

原始证据：`/tmp/signaldeck-mechanism-baseline.log`、`/tmp/signaldeck-mechanism-baseline.json`、`/tmp/signaldeck-mechanism-summary.md`。
