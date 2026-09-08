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

当前 Core Workflow Package API 的行为由 [`test_platform_api.py`](../backend/tests/test_platform_api.py) 覆盖，Finance 自有 Templates/Reports HTTP 面由 [`test_independent_plugins.py`](../backend/tests/test_independent_plugins.py) 覆盖；Logfire 挂载检查位于 [`test_runtime_config_health.py`](../backend/tests/test_runtime_config_health.py)。[`test_core_api.py`](../backend/tests/test_core_api.py) 对实际已 instrumentation 的 `/api/runs` 检查公开 OpenAPI 的 GET-only 方法集合，并验证 POST 返回 405。

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
  tests/test_platform_api.py::test_definition_editor_uses_canonical_immutable_source \
  tests/test_independent_plugins.py::test_finance_owned_crud_compile_upload_and_immutable_agent_reports \
  tests/test_runtime_config_health.py::test_create_app_instruments_fastapi_with_logfire \
  tests/test_core_api.py::test_run_catalog_is_get_only_with_logfire_instrumentation)
```

这些检查分别验证 Core 包编辑、独立 Finance 业务 HTTP 闭环、Logfire instrumentation 注册，以及实际 GET-only 路由的 405/partial-route-match 行为。方法集合使用公开 `app.openapi()["paths"]`，不依赖 `app.routes` 的平铺形态或私有 `_IncludedRouter`。解除封顶前必须在待升级的完整依赖组合上重新运行这些检查。

## 已完成的镜像调整

[`Dockerfile`](../Dockerfile) 和 [`frontend/Dockerfile`](../frontend/Dockerfile) 的 Node 26 构建阶段均使用 `npm install -g pnpm@10.30.1`。镜像依赖规则见 [`开发规范.md`](开发规范.md#依赖与镜像规则)；根组合镜像的额外构建检查见 [`CONTRIBUTING.md`](../CONTRIBUTING.md#检查测试与构建)。
