# 交接：依赖升级遗留问题

本文记录仓库内的依赖约束、已完成收尾和解除 FastAPI 封顶所需的证据。版本以本地 manifest 和锁文件为准；上游是否已有可用版本，应在实际升级时核验。

## 当前锁定状态

| 依赖 | 仓库状态 | 依据 |
| --- | --- | --- |
| FastAPI | 声明 `>=0.136.3,<0.137`，锁定 `0.136.3` | [`backend/pyproject.toml`](../backend/pyproject.toml)、[`backend/uv.lock`](../backend/uv.lock) |
| Logfire | 声明 `logfire[fastapi]>=4.37.0`，锁定 `4.37.0` | 同上 |
| OpenTelemetry SDK | 锁定 `1.40.0` | [`backend/uv.lock`](../backend/uv.lock) |
| FastAPI instrumentation | 锁定 `opentelemetry-instrumentation-fastapi==0.61b0` | 同上 |
| React Hooks ESLint 插件 | 声明 `^7.1.1`，锁定 `7.1.1` | [`frontend/package.json`](../frontend/package.json)、[`frontend/pnpm-lock.yaml`](../frontend/pnpm-lock.yaml) |

FastAPI 封顶仍在仓库中；当前锁文件尚未采用解除封顶要求的 OpenTelemetry 版本组合。这个状态不代表当前 PyPI 发布状态。

## 已完成：恢复 React Hooks 规则

[`frontend/eslint.config.js`](../frontend/eslint.config.js) 使用 `reactHooks.configs.recommended.rules`，已移除 `react-hooks/set-state-in-effect` 的 `warn` 覆盖。相关 effect 重构与规则恢复可追溯到本地提交 `6f40db5e`。

后续修改这些组件或升级 lint 插件时，保留规则的推荐级别，按 [`CONTRIBUTING.md`](../CONTRIBUTING.md#检查测试与构建) 运行受影响的前端检查。

## 遗留：FastAPI 封顶 `<0.137`

### 原因与现有保护

封顶注释及本地提交 `e5f6b4d1` 记录的故障链是：FastAPI 0.137 的 `include_router` 使用私有 `_IncludedRouter` 嵌套路由；旧版 FastAPI instrumentation 在 partial route match（例如 POST 到仅接受 GET 的路由）访问 `.path` 时会抛出 `AttributeError`。当时采用的修复门槛为 instrumentation `>=0.64b0`、OpenTelemetry SDK `>=1.43`，但 Logfire 4.37.0 的 SDK 约束阻止该组合。

[`backend/app/main.py`](../backend/app/main.py) 在创建应用时调用 [`instrument_fastapi_app`](../backend/app/core/telemetry.py)，因此 405 路由行为属于应用运行时回归边界。

[`backend/tests/test_api.py`](../backend/tests/test_api.py) 中两个路由挂载测试已经从公开的 `app.openapi()["paths"]` 读取路径集合，不依赖 `app.routes` 的平铺形态或私有 `_IncludedRouter`。

### 解锁条件与升级步骤

在后续依赖升级任务中，先核验目标 Logfire 版本的依赖元数据，确认它允许 SDK `>=1.43`，并确认整个依赖集合能够同时解析出 instrumentation `>=0.64b0`。仅看到某个 SDK 上限放宽不足以解除封顶。

满足上述前提后，将 [`backend/pyproject.toml`](../backend/pyproject.toml) 的 FastAPI 约束改为已核验的目标范围，再解析锁文件：

```bash
cd backend
uv lock --upgrade-package fastapi --upgrade-package logfire \
  --upgrade-package opentelemetry-instrumentation-fastapi
uv run --frozen python - <<'PY'
from pathlib import Path
import tomllib

names = {"fastapi", "logfire", "opentelemetry-sdk", "opentelemetry-instrumentation-fastapi"}
for package in tomllib.loads(Path("uv.lock").read_text())["package"]:
    if package["name"] in names:
        print(f'{package["name"]}: {package["version"]}')
PY
```

核对实际解析版本及完整锁文件 diff。移除封顶及其注释的完成条件是版本组合符合门槛、下列回归测试通过，并完成 [`CONTRIBUTING.md`](../CONTRIBUTING.md#检查测试与构建) 中适用的后端检查。

### 定向回归

数据库准备和依赖安装按 [`CONTRIBUTING.md`](../CONTRIBUTING.md#开发启动) 执行。以下命令在仓库根目录运行：

```bash
(cd backend && uv run pytest \
  tests/test_api.py::test_agent_platform_routes_mount_package_first_api \
  tests/test_api.py::test_finance_workspace_product_routes_remain_mounted_for_templates_and_reports \
  tests/test_tool_catalog_api.py::test_tools_catalog_route_is_get_only)
```

前两个测试验证 Workflow Package API 与 Templates/Reports API 挂载；最后一个测试验证 `POST /api/tools` 返回 405，且 OpenAPI 中该路径只提供 GET。升级后应保留这些公开行为断言。

## 已完成的镜像调整

[`Dockerfile`](../Dockerfile) 和 [`frontend/Dockerfile`](../frontend/Dockerfile) 的 Node 26 构建阶段均使用 `npm install -g pnpm@10.30.1`。镜像依赖规则见 [`开发规范.md`](开发规范.md#依赖与镜像规则)；根组合镜像的额外构建检查见 [`CONTRIBUTING.md`](../CONTRIBUTING.md#检查测试与构建)。
