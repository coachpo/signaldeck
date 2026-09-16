# 本次测试精简独立复核

复核范围：`/Users/qingli/Documents/ChatGPT/signaldeck-test-ablation-20260916` 相对 `7c4bcbcf` 的 6 个测试文件、主报告、HTTP 结果、前端精确故障替换及完整/候选/最终矩阵。只读检查；未修改仓库、未执行重型测试，也不将记录复核冒称为独立重跑。

## 结论

未发现需要撤销本次精简的具体契约覆盖损失。此结论限于已检查断言、输入条件和记录中的故障样本，不主张全部潜在故障绝对等价。

- `backend/tests/test_auth_middleware.py`：合并前后的无 Origin 请求仍校验 401 和精确 JSON，有 Origin 请求仍校验 401 与允许来源响应头。两次 HTTP 请求均实际存在。每次新 fixture 的独立状态变为共享状态，主报告已明确说明这一限制；实际 BearerTokenMiddleware 不按请求更新认证状态，没有发现以独立 fixture 验证的额外现行合同被删除。matching token、非 ASCII 和 health 用例不变。
- `backend/tests/test_core_api.py`：原 app fixture 已使用 `create_app(init_database=False)`，因此两项改动没有新绕过原本存在的启动 lifespan。去掉的是 session_factory 引起的 PostgreSQL 建库和 PlatformStore/ScheduleStore 初始化。移除路由的 404 请求和合成 ApiError 的真实 HTTP handler 均不访问数据库；原断言不变。真实 `/api/runs` 200/405 和 Logfire 路径继续使用数据库 fixture。autouse API token/settings 隔离仍然适用。
- `resource-selection-checkbox.test.tsx`：被删用例使用未选中且未传 indeterminate 的标签；保留的 callback 用例同样以该状态渲染并通过指定可访问名称查找。另一用例还覆盖 true/mixed/false 三状态的名称查找。记录中 label、mixed、callback 三故障最终仍失败。
- `workspace-page-shell.test.tsx`：被删用例的 body 包含内容及 rail 不包含内容断言已存在于保留首例。保留无 rail 分支。不同标题、文字与 ReactNode 元素类型未参与被测组件分派，未见被移除的独立语义分支。drop-content、wrong-container、scroll 故障矩阵与保留断言相符。
- `inventory-page-shell.test.tsx`：最终合并后的无 filter 用例保留 Create action 输入、非空 toolbar、内容定位、toolbar 不包含内容、content 包含内容及顺序断言。有 filter、无 filter、无 toolbar 三分支仍在。原删减中的无 filter 内容漏检已通过最终断言和对应故障样本补回。title/summary 文案变更没有改变该组件的分派条件。
- `workflow-platform.test.ts`：原 6 项参数全部保留，新增带空白与换行的字符串；同一回调仍先断言 launch 再断言 schedule 的精确 parameters。实验拒绝删除 null、数值、数组等独有输入维度，与矩阵中候选存活故障一致。新增字符串修补本组 trim 样本漏检，没有弱化原断言。

## 证据交付需校准一处

主报告“故障失败节点与结果见 HTTP 原始记录”的表述超出 `backend-http-results.json` 当前内容：该文件只有 mutant/variant/repeat/seconds/returncode/summary，没有失败 nodeid 或失败断言，也未在交付目录找到 HTTP 精确替换说明。前端已有这些信息，HTTP 的 7/7 数字可从摘要核对，但外部复核者不能只凭该 JSON 排除故障运行的其他失败原因或准确重建同一故障。

建议将已有 HTTP 注入脚本中的精确替换、失败节点或日志位置纳入报告附属材料；如暂不能补齐，则至少改称“HTTP 执行摘要”，并明确原始失败明细未随报告交付。此项属于证据可复核性，不是已发现测试实现有误；无需因此撤销已核对保留的断言。

## 限制

未对全仓既有测试另做评审；未评价未实施精简的 E2E/插件/历史探针；后端全量正在执行，最终结果需由主任务补入。性能结论保持主报告当前措辞：尚未证明全量提速。UI role/ARIA/DOM 与模拟几何断言不等于完整可访问性或真实视觉体验验证。

## 审阅后证据修正

已从原实验日志提取失败 nodeid，补入 `backend-http-results.json`（14 个失败运行）和 `backend-effect-results.json`（5 个失败运行），并保留原日志文件名。该修正不改变测试或实验结果；源变异的精确替换、初始源 SHA256 和失败节点已补充到 `backend-http-evidence.json`、`backend-effect-evidence.json`；替换来自实际执行脚本的 AST，并非事后猜测。
