# 编写静态扩展

SignalDeck extension 是随 backend 一起部署的静态 Python 组合契约。当前没有 marketplace、runtime discovery、安装 API、扩展 enable/disable 状态或 `/api/extensions` 路由。系统边界见[架构说明](架构说明.md)，本文说明扩展如何接入现有 API、工具执行和依赖记录。

## Contract 字段

扩展在自己的包中声明 `EXTENSION = Extension(...)`。[`Extension`](../backend/app/extensions/contract.py) 是 frozen dataclass；除 `key` 外，字段默认均为空：

- `key`：canonical owner key，例如 `signaldeck.finance`；
- `api_routers`：挂载在 `/api/v1` 下的 FastAPI router；
- `tool_declarations`：server-declared catalog contribution；`/api/tools` 只投影 key、display name 和 description；
- `runtime_tool_specs`：native 工具的参数 schema、parser、executor、guidance、排序和拒绝访问信息；
- `provider_factories`：命名 factory；当前 registry 调用其中的 `execution_provider_bundle` 并按 extension key 合并 provider payload，其他名称需要明确的调用方；
- `runtime_dependency_surfaces`：加入 package/run 依赖记录的运行依赖面标签；
- `package_private_mcp_tool_keys`：由扩展拥有的 package-private MCP tool key。

native tool key 必须带所属扩展前缀，例如 `signaldeck.finance.news.lookup`。catalog contribution 与 runtime spec 的 `owner_extension_key` 应指向同一 owner；OpenAI function name 必须等于 canonical key 的 `.` 替换为 `_` 后的结果，例如 `signaldeck_finance_news_lookup`。package-private MCP 使用自身声明的 tool name，由 ownership 表记录 owner，不套用 native function name 规则。

当前内置扩展：

- [`signaldeck.finance`](../backend/app/extensions/signaldeck_finance/__init__.py)：Templates/Reports router、finance provider、market data、news、social sentiment、insider data 和 report lookup 工具，以及 `web_search_exa` 的 package-private ownership；
- [`signaldeck.digital_oracle`](../backend/app/extensions/signaldeck_digital_oracle/__init__.py)：prediction markets、SEC filings、market sentiment、macro/rates、crypto derivatives、CFTC 和 options 工具；不贡献 API router、provider factory 或浏览器导航面。

## 注册、执行与依赖记录

[`registry.py`](../backend/app/extensions/registry.py) 在 `INSTALLED_EXTENSIONS` 中显式组合扩展。导入时分别拒绝重复的 extension key、catalog tool key、runtime spec key 和 package-private MCP tool key；MCP key 先去空格并转为小写。API composition 将扩展 router 挂到 `/api/v1`，工具 catalog 和 native runtime registry 分别消费自己的声明集合。

[`RuntimeToolRegistry`](../backend/app/agents/runtime_tools/registry.py) 还检查 native key、声明的 function name 和映射后的 function name 唯一性。工具只在被 capability profile 授予时进入模型可用工具集；dispatch 在解析参数和调用 executor 前检查名称与 grant。未知名称返回 `agent_tool_call_unsupported`，内置工具缺少 grant 返回 `agent_execution_access_denied`，不得将未知 native tool 静默改为 MCP 调用。

[`extension_dependencies.py`](../backend/app/services/extension_dependencies.py) 从 capability profile 的 native tool 和 agent 使用的 package-private MCP server 收集依赖，生成排序稳定的 `extensionKey`、`surfaces`、`fields`。已记录 owner 的扩展会加入其 `runtime_dependency_surfaces`。这些标签用于 package 和 run provenance；它们不包含 provider 实例、凭据或扩展 Python 代码副本。

## 配置与结果边界

配置 timeout、provider 顺序和启用开关时复用扩展 settings。凭据在 executor 中通过 `RuntimeToolContext.resolve_secret_value` 解析，不能写入工具声明、参数 schema 或 dependency surface。目前 finance 的 `alpha_vantage_api_key`、Digital Oracle 的 `fred_api_key` 和 `edgar_contact_email` 走 package-secret runtime 路径；Digital Oracle 的环境 settings 不保存这两个 secret。

provider 输出由对应类型和 mapper 归一化后返回。Digital Oracle 使用结构化 warnings 表达禁用、缺少配置、上游失败、空结果、部分覆盖和截断；缺少可选 `yfinance` 只影响 options 数据源。保留结果中的来源、范围和 warnings，并通过现有 warning helper 过滤敏感详情，不把 provider 异常或原始请求内容直接当作公开诊断。

## 添加扩展

1. 在 `backend/app/extensions/<name>/` 创建 backend package。
2. 定义 ownership、catalog contribution 和需要的 `RuntimeToolSpec`，保持 key、owner、function name、parser 和 executor 一致；按能力需要提供 router 或 provider bundle。
3. 在该 package 的 `__init__.py` 声明 `EXTENSION`，再在 `backend/app/extensions/registry.py` 将对象加入 `INSTALLED_EXTENSIONS`。
4. 根据实际贡献覆盖导入、唯一性、catalog/API projection、参数校验、grant、provider 故障和结果脱敏；涉及 package 依赖时同时验证 compiler 和 run provenance。

不要使用动态 `import_module` discovery 或 registrar side effect。现有验证入口包括 [`test_extension_contract.py`](../backend/tests/test_extension_contract.py)、[`test_tool_catalog_api.py`](../backend/tests/test_tool_catalog_api.py)、[`test_runtime_tools.py`](../backend/tests/test_runtime_tools.py) 和 [`test_execution_providers.py`](../backend/tests/test_execution_providers.py)；测试环境与命令见[贡献指南](../CONTRIBUTING.md)。

## 多种实现

不同扩展可以用不同 owner key 提供相似能力。以下第二个 key 是自建扩展的示例，需先实现并静态注册才可使用：

- `signaldeck.finance.news.lookup`
- `acme.research.news.lookup`

Workflow Package 在 capability profile 中选择一个或多个：

```yaml
capabilityProfiles:
  - key: news_research
    name: News Research
    toolKeys:
      - signaldeck.finance.news.lookup
```

切换实现是 manifest 选择，而不是平台 alias：

```yaml
capabilityProfiles:
  - key: news_research
    name: News Research
    toolKeys:
      - acme.research.news.lookup
```
