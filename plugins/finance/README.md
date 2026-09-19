# Finance 报告工作区

Finance 独立拥有报告、格式和编译器。页面默认普通模式：历史报告与使用已有格式。`?report=<slug>` 或 `?reportId=<id>` 精确读取一份报告，数字 ID 由插件的 `/api/reports/by-id/{id}` 解析；刷新保留此入口，失效标识显示读取错误。`reports_create` 和 `research_reports_create` 声明结果链接 `report`，把 `tool.output.id` 绑定为 `reportId` 参数，工作流结果由此直达报告。下载使用 `/api/reports/{slug}/download`，内容是已保存的 Markdown。报告阅读显示创建/更新时间、生成来源和已保存的作者、说明、标签、证券、研究类型及研究日期。任务报告的显示名称去掉插件生成的唯一后缀，存储身份保持不变。正文的缺失/未知/循环引用以恢复提示单独说明，不把有缺失的报告描述成完整研究。研究报告的证据、编译和争议合同见[插件接入](../../docs/writing-extensions.md#financeoracle-研究合同)。

历史查询在服务端执行：`GET /api/reports?q=...&source=...&ticker=...&tag=...&reviewType=...&sort=newest&limit=16&offset=0`。`q` 是名称、公开 slug 或正文的字面子串；`sort` 支持 `newest`、`oldest`、`name`，使用 id 保证同值顺序稳定。响应为数组。页面每页 15 条并多取一条判断下一页，不将当前页过滤冒充全库搜索。

普通用户选已有格式、填业务信息、预览后生成报告。必填字段使用浏览器就地提示。预览中有缺失、未知、无效或循环引用时不能生成。生成携带 `expectedContent` 和 `expectedCompiled`，服务端在保存之前重新编译比较；格式或动态报告引用已变化则返回 `409 preview_changed`，要求重新预览。成功创建新报告并直达其阅读入口，不改原报告。

专家模式提供新建格式、正文编辑、业务字段与报告引用控件、草稿预览、上传 Markdown、普通报告编辑与删除。制作区位于试用区之前；先保存格式，再核对预览并生成新报告。Agent 报告始终不可修改和删除，API 保护与模式无关。切换模式只改变页面展示，按条目保留此页面内的编辑草稿与输入，既不保存也不生成报告；离开或刷新页面有未保存草稿、未生成的填写信息时浏览器提示。草稿和填写值只在页面内存中，不写入浏览器持久存储。

保存、生成、上传和删除期间，工作区显示处理中并暂时禁用编辑、模式及条目切换；操作结束后恢复。保存失败时保留草稿，供修正后重试；无法确认写入结果时，页面保留草稿并要求先查看列表确认是否已保存，再决定是否重试。

## 业务字段与引用

作者直接填写显示名称并选择是否必填，页面自动生成字段身份。正文通过 `⟦公司名称⟧` 这样的可读标记放置填写项，可改名或再次插入，不要求作者了解内部声明语法。普通用户填写的表单使用这些显示名称。格式中已有的声明和引用按下文的底层声明语法执行；未编辑的格式逐字往返，正文中的代码保持原样，编辑页面不提供原始声明编辑入口。

报告引用通过控件选择：最新报告、某证券或标签的最新报告、指定报告、按最新优先的位置、全部报告列表、本次填写的信息。可选择正文、名称、创建日期或摘要；证券和标签支持固定文字或本次填写项。`/api/templates/placeholders` 为每份报告返回引用所用的存储名称 `name`（任务报告含插件生成的后缀）和供显示的 `label`；任务报告的名称及摘要引用显示业务名称。本次信息列表使用已声明显示名。

页面生成的底层声明写在格式正文中：`<!-- input: key | 显示名 | required -->` 或 `<!-- input: key | 显示名 | optional -->`，正文用 `{{inputs.key}}` 引用。声明不出现在编译结果中；可选字段未填写时为空，引用未声明的键按必填处理。

## 验证

在仓库根目录运行，需要已安装的 backend 测试依赖和 frontend Playwright Chromium：

```sh
node plugins/finance/tests/authoring.mjs
TEST_DATABASE_URL=postgresql+psycopg://signaldeck:signaldeck@127.0.0.1:<port>/postgres \
  PYTHONPATH=plugins/finance:plugins/runtime \
  backend/.venv/bin/python -m pytest plugins/finance/tests/test_finance_ux.py -q -s
(cd backend && uv run pytest tests/test_finance_api.py tests/test_independent_plugins.py -q)
```

`TEST_DATABASE_URL` 指向账户可创建和删除数据库的 PostgreSQL，例如 backend 测试容器 `signaldeck-target-test-postgres-volume` 的映射端口（`docker port signaldeck-target-test-postgres-volume 5432/tcp`），数据库设置见[贡献指南](../../CONTRIBUTING.md#测试数据库与-e2e-环境)。未设置时，Finance 测试只查找 `SIGNALDECK_TEST_POSTGRES_DIR` 模式下的容器 `signaldeck-target-test-postgres`。测试创建 UUID 命名的数据库，结束时只删除该库。浏览器测试启动 Finance 前自动构建共享 UI（需 frontend 已安装锁定依赖），检查 375/768/1024/1440px 并把截图写入 Git 忽略的目录；API 测试不需要浏览器产物。CI 不运行 `plugins/finance/tests/`。
