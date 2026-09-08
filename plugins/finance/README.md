# Finance 报告工作区

Finance 独立拥有报告、格式和编译器。页面默认普通模式：历史报告与使用已有格式。`?report=<slug>` 或 `?reportId=<id>` 精确读取一份报告（数字 ID 在插件内通过 `/api/reports/by-id/{id}` 解析，不要求修改闭合的工作流回执）；刷新保留此入口，失效标识会显示读取错误。下载使用 `/api/reports/{slug}/download`，内容是已保存的 Markdown。报告阅读显示创建/更新时间、生成来源和来源证据；正文的缺失/未知/循环引用标记单独提示，不把有缺失的报告描述成完整研究。

历史查询在服务端执行：`GET /api/reports?q=...&source=...&ticker=...&tag=...&reviewType=...&sort=newest&limit=16&offset=0`。`q` 是名称、公开 slug 或正文的字面子串；`sort` 支持 `newest`、`oldest`、`name`，使用 id 保证同值顺序稳定。响应继续为数组。页面每页 15 条并多取一条判断下一页，不将当前页过滤冒充全库搜索。

普通用户选已有格式、填业务信息、预览后生成报告。必填字段使用浏览器就地提示。预览中有缺失或未知引用时不能生成。生成携带 `expectedContent` 和 `expectedCompiled`，服务端在保存之前重新编译比较；格式或动态报告引用已变化则返回 `409 preview_changed`，要求重新预览。成功创建新报告并直达其阅读入口，不改原报告。

专家模式显示新建格式、Markdown 编辑、字段/报告引用插入、草稿编译诊断/预览、上传 Markdown、普通报告编辑与删除。Agent 报告始终不可修改和删除，API 保护与模式无关。切换模式只改变页面展示，按条目保留此页面内的编辑草稿与输入，既不保存也不生成报告；离开页面有未保存草稿时浏览器提示。草稿不跨浏览器关闭持久保存。

## 业务字段

原有 `{{inputs.name}}` 引用继续有效，未声明字段按必填展示。需要中文标签与可选字段时，在格式内容中加入如下声明（编辑器辅助按钮可插入）：

```markdown
<!-- input: company | 公司名称 | required -->
<!-- input: notes | 补充说明 | optional -->
# {{inputs.company}}
{{inputs.notes}}
```

声明不增加数据库列或开放 schema。编译器移除这些声明，并为可选字段补空值；既有报告选择器语义保持。名称使用英文字母/下划线开头，后接字母/数字/下划线；显示名不含 `|`、换行和尖括号。示例见 [company-review.md](examples/company-review.md)。模板作者可复制内容到“新建格式”保存，安装不会覆盖任何已有格式。

## 验证

使用根目录已安装的 backend 测试依赖与 frontend Playwright Chromium：

```sh
PYTHONPATH=plugins/finance:plugins/runtime backend/.venv/bin/python -m pytest plugins/finance/tests/test_finance_ux.py -q -s
(cd backend && uv run pytest tests/test_finance_api.py tests/test_independent_plugins.py -q)
```

新测试创建 UUID 命名的独立 PostgreSQL 库，用真实 Finance HTTP 与浏览器验证业务表单、可选值、预览冲突、模式往返、深链接刷新、下载、第二页历史和失效报告。浏览器检查 375/768/1024/1440px 并输出 `output/playwright/finance-ux/` 截图。`TEST_DATABASE_URL` 可指定有建库权限的测试服务器；未指定时只复用文档规定的 `signaldeck-target-test-postgres` 测试容器端口。测试结束只删除自己创建的数据库。此验证不调用付费供应商，也不替代实际参与者无讲解观察。
