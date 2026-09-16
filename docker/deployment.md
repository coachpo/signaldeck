# 拆分镜像部署

本说明对应 [`compose.production.example.yml`](compose.production.example.yml)：前端 Nginx、Core API、dispatcher 和 worker 分别运行，后三者使用同一 backend 镜像。根 `Dockerfile`、根 Compose 和 `start.sh` 仅用于本地/演示；其中 Temporal `start-dev` 不能作为生产服务。当前支持边界仍是[可信内网、单一操作者](../STATUS.md#部署与使用)，本说明不代表目标实例已经通过部署验收。

## 前提与构建

需要 Docker Compose v2，以及已准备好的 PostgreSQL 16 和 Temporal。数据库地址和 Temporal 地址必须从容器内可达；容器内的 `localhost` 不指向宿主机。当前 Temporal client 使用默认 `default` namespace，未配置 TLS 或认证，需使用可信网络上的服务并预先确保该 namespace 存在。

Core 数据库和角色需预先创建，角色须能在自己的数据库中创建表。启动使用 `create_all`，只创建缺失表，不升级已有表；已有数据的兼容和处置以[数据政策](../STATUS.md#数据与兼容性)为准。有状态插件使用独立数据库和角色。

在仓库根目录构建本地拆分镜像：

```bash
docker build -f backend/Dockerfile -t signaldeck-backend:local backend
docker build -f frontend/Dockerfile -t signaldeck-frontend:local frontend
```

镜像使用各自锁文件。也可在配置中指定已取得的完整镜像名，例如 `ghcr.io/your-namespace/signaldeck-backend:your-tag`；部署时选择明确 tag 或 digest，backend、dispatcher、worker 必须一致。本说明不要求推送或发布镜像。

worker 第一次处理每个 Core 制品时，会用 uv 按该制品的锁文件安装固定 Python 环境；它需要访问锁文件中的依赖下载地址。镜像已构建、API 已健康都不证明该安装已成功。保留执行环境和 uv 缓存可供后续复用。

## GitHub Actions → GHCR → capy

[`Docker Images`](../.github/workflows/docker-images.yml) 在推送 `main`、`v*` 标签或手动运行时构建并发布五个镜像：`signaldeck-backend`、`signaldeck-frontend`、`signaldeck-finance`、`signaldeck-notes`、`signaldeck-digital-oracle`，命名空间为 `ghcr.io/<仓库所有者>/`。全部包含 `linux/amd64` 和 `linux/arm64`；PR 只构建。手动运行可选择 `all` 或单个服务；需要一套同提交镜像时选择 `all` 并确认五个构建全部成功。

Finance、Notes 的构建上下文是仓库根目录（包含共享前端 UI），Oracle 使用 `plugins`，Core 和 frontend 使用各自目录。镜像 tag 是仓库 Git tag 或 `sha-<完整提交 SHA>`，不同于插件自己的发布版本号；`main` 和 `latest` 会随构建更新。需固定构建产物时使用 Actions 输出的各镜像 digest。Actions 使用仓库的 `GITHUB_TOKEN`，无需 capy SSH 密钥。

以下步骤在修改已提交、推送且镜像发布成功后执行。在 capy 新建检出，或使用已有检出并切换到对应的部署版本：

本节的 `split.env` 适用于已有 PostgreSQL/Temporal。capy 首次安装且没有这些服务时，完成检出后使用下方「capy 专用基础设施」的 `capy.env` 和叠加配置。

```bash
ssh capy
mkdir -p ~/apps
git clone https://github.com/coachpo/signaldeck.git ~/apps/signaldeck
cd ~/apps/signaldeck
mkdir -p ~/.config/signaldeck
chmod 700 ~/.config/signaldeck
(umask 077; set -C; cat docker/ghcr.env.example > ~/.config/signaldeck/split.env)
```

已有配置直接编辑，避免覆盖。填写 [`ghcr.env.example`](ghcr.env.example) 中的五个镜像引用、独立数据库、Temporal 地址及两项密钥。首次部署前必须准备好下节的基础设施；已有 Prism 数据库不是 SignalDeck 数据库。2026-09-16 只读检查确认 capy 是 ARM64、支持 Docker Compose，8087/8088 已由 Prism 使用，未发现运行中的 Temporal 容器；示例选用当时未监听的 8089，启动前仍需检查端口。

GHCR 首次发布的包默认为私有，公开仓库不会自动使镜像公开。公开包可匿名拉取；私有包在 capy 使用具备 `read:packages` 的 classic PAT 执行 `docker login ghcr.io -u <GitHub用户名>`，在交互提示中输入 token。参见 [GitHub Container registry 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。

```bash
sdcompose() {
  docker compose --project-name signaldeck-split \
    --env-file "$HOME/.config/signaldeck/split.env" \
    -f docker/compose.production.example.yml "$@"
}
sdcompose config --quiet
sdcompose pull
sdcompose up -d --wait
sdcompose ps
```

需要插件时，为 `pull` 和 `up` 都添加相同的 profiles，例如 `sdcompose --profile finance --profile notes --profile digital-oracle pull`。启用 Finance/Notes 前填写各自数据库和角色；插件登记与页面挂载按下文完成。后续更新 Core/frontend 仍使用 `pull`、`up -d --wait`，插件升级须遵守下文保留旧发布和独立 endpoint 的要求。

从本机执行 `ssh -N -L 8089:127.0.0.1:8089 capy`，再访问 `http://localhost:8089`；或接入既有可信反向代理。按下方启动验证检查数据库、认证和实际工作流，不能只检查页面能否打开。

## capy 专用基础设施

[`compose.capy.yml`](compose.capy.yml) 叠加拆分示例，为单机可信内网部署提供独立 PostgreSQL 16、Temporal Server 1.31.2 及初始化容器。它不使用 `start-dev`，不复用 Prism 数据库或网络，不向宿主机发布数据库和 Temporal 端口。单机配置不提供高可用；Temporal 未启用 TLS/认证，仅供本项目 Compose 内网访问。

PostgreSQL 初始化三个业务数据库/角色，以及 Temporal 专用角色和两个数据库。Temporal 的官方固定版本工具初始化主库 schema 1.19、visibility schema 1.14；schema 和 `default` namespace 就绪后才启动 dispatcher/worker。重复启动不覆盖数据或重建 namespace；已有 namespace 的设置保持。新 namespace 的已完成执行历史保留 7 天，Core PostgreSQL 中的历史记录及产物不按此期限删除。升级 Temporal 镜像及 schema 版本需单独验证，不修改 tag 后直接套用旧库。依据：[官方自托管说明](https://docs.temporal.io/self-hosted-guide/deployment)与[官方 schema 初始化示例](https://github.com/temporalio/samples-server/blob/main/compose/scripts/setup-postgres.sh)。

在仓库根目录一次性创建仓库外配置，生成彼此独立的随机凭据，已有文件会被拒绝覆盖：

```bash
python3 - <<'PY'
import os
import secrets
from pathlib import Path

target = Path.home() / '.config/signaldeck/capy.env'
target.parent.mkdir(parents=True, exist_ok=True)
target.parent.chmod(0o700)
keys = {'POSTGRES_PASSWORD', 'CORE_DB_PASSWORD', 'FINANCE_DB_PASSWORD',
        'NOTES_DB_PASSWORD', 'TEMPORAL_DB_PASSWORD',
        'AGENT_PLATFORM_ENCRYPTION_KEY', 'SIGNALDECK_API_TOKEN'}
lines = []
for line in Path('docker/capy.env.example').read_text().splitlines():
    key = line.partition('=')[0]
    lines.append(f'{key}={secrets.token_hex(32)}' if key in keys else line)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write('\n'.join(lines) + '\n')
PY
```

编辑 `capy.env` 的 `SIGNALDECK_IMAGE_TAG` 为已经全部发布成功的版本或完整 `sha-…`；五个镜像共用该标签。数据库 URL 从密码变量派生，不要 `source` 此文件。保留原密码与加密 key；重生成配置不会修改已有 PostgreSQL 角色密码。

```bash
sdcompose() {
  docker compose -p signaldeck-capy \
    --env-file "$HOME/.config/signaldeck/capy.env" \
    -f docker/compose.production.example.yml -f docker/compose.capy.yml \
    --profile finance --profile notes --profile digital-oracle "$@"
}
sdcompose config --quiet
sdcompose pull
sdcompose up -d --wait --wait-timeout 180
sdcompose run --rm bootstrap
sdcompose ps --all
```

`temporal-schema` 和 `temporal-namespace` 成功后显示 `Exited (0)` 是正常状态；`bootstrap` 使用原有通用 API 登记缺失插件与本地连接默认值，保留已有配置。首次显示统一插件页面，还需从本次镜像读取精确描述并生成挂载：

```bash
mkdir -p "$HOME/.config/signaldeck/releases"
sdcompose run --rm --no-deps --entrypoint python finance \
  -m plugin_runtime.describe finance_plugin.main:create_app > "$HOME/.config/signaldeck/releases/finance.json"
sdcompose run --rm --no-deps --entrypoint python notes \
  -m plugin_runtime.describe notes_plugin.main:create_app > "$HOME/.config/signaldeck/releases/notes.json"
test ! -e "$HOME/.config/signaldeck/plugin-mounts.json" && \
  python3 docker/prepare_plugin_mounts.py "$HOME/.config/signaldeck/releases"
```

随后在 `capy.env` 添加 `SIGNALDECK_PLUGIN_MOUNTS_FILE`，值为刚生成文件的绝对路径，再运行 `sdcompose up -d --wait`。以上挂载生成步骤仅用于首次安装；已有文件和历史发布的升级按下文处理。工作流 YAML 仍需通过专家制作或导入，模型凭据通过资源表单配置。Oracle 外部 provider 凭据仍按插件说明提供。

健康验证沿用下节，将 curl 端口改为 8089；Temporal 还可执行 `sdcompose run --rm --no-deps --entrypoint temporal temporal-namespace operator cluster health`。备份需覆盖命名卷中的五个 PostgreSQL 数据库、Core 产物/制品卷和仓库外配置；普通 `down` 保留数据，禁止把 `down -v` 当更新命令。

本地隔离验证入口（需要已构建的三个应用镜像和贡献指南中的 backend 环境）：

```bash
backend/.venv/bin/python docker/verify_capy_stack.py \
  --backend-image signaldeck-backend:local \
  --frontend-image signaldeck-frontend:local \
  --notes-image signaldeck-notes:1.3.0
```

该脚本使用随机项目名、端口和密码，创建并清理自己的测试容器及卷，验证数据库权限隔离、任务执行、整栈重建后的 Temporal 历史/产物/计划和离线读取；不使用仓库 `.env` 或 capy 服务器。

## 配置

将实例配置放在仓库和 Docker build context 之外，限制文件权限。以下只创建占位文件，必须替换占位地址、口令和加密 key 后才能启动；数据库 URL 的用户名/密码特殊字符需要 URL 编码。Compose env 文件中的单引号使 `$` 保持字面值，不要将此文件作为 shell 脚本 `source`。

```bash
mkdir -p "$HOME/.config/signaldeck"
chmod 700 "$HOME/.config/signaldeck"
(umask 077; set -C; cat > "$HOME/.config/signaldeck/split.env" <<'ENV'
SIGNALDECK_BACKEND_IMAGE=signaldeck-backend:local
SIGNALDECK_FRONTEND_IMAGE=signaldeck-frontend:local
DATABASE_URL='postgresql+psycopg://replace-user:replace-password@postgres.example:5432/replace-core-db'
TEMPORAL_ADDRESS=temporal.example:7233
AGENT_PLATFORM_ENCRYPTION_KEY='replace-with-a-long-random-secret'
SIGNALDECK_API_TOKEN='replace-with-a-different-long-random-secret'
APP_PORT=8080
CORS_ALLOWED_ORIGINS=
ENV
)
```

已有配置文件应直接编辑，不重复执行上面的创建命令。加密 key 与 API 访问口令用途不同，分别生成并妥善保留。示例不会自动生成真实凭据；不要把密钥放入 `VITE_*`、镜像 build args、插件挂载文件或连接预设。不要将展开全部环境变量的 `docker compose config` 输出保存到日志；仅校验语法使用 `config --quiet`。

| 配置项 | 用途 |
| --- | --- |
| `SIGNALDECK_BACKEND_IMAGE` / `SIGNALDECK_FRONTEND_IMAGE` | 必填完整镜像引用。 |
| `DATABASE_URL` / `TEMPORAL_ADDRESS` | 必填 Core PostgreSQL URL 和 Temporal `host:port`。 |
| `AGENT_PLATFORM_ENCRYPTION_KEY` | 必填资源凭据加密 key；更换会使原密文无法读取。 |
| `SIGNALDECK_API_TOKEN` | 必填 API 访问口令，浏览器首次访问 API 时输入。 |
| `APP_PORT` | 宿主机端口，默认 8080；仅绑定 `127.0.0.1`。 |
| `CORS_ALLOWED_ORIGINS` | 默认空；前端同源 `/api` 代理无需 CORS。直接跨源访问 API 时填逗号分隔的精确来源。 |
| `SIGNALDECK_PLUGIN_MOUNTS_FILE` | 可选既有文件的绝对路径；默认使用随 Compose 提供的空登记。文件缺失直接拒绝挂载。 |

前端生产 API 默认 `/api`，由 Nginx 代理到 `backend:8000`，backend 不发布宿主机端口。`VITE_API_BASE_URL` 仅在构建时生效，启动容器时设置它不会更改静态页面。非本机访问应通过已有的可信入口；改变公网暴露范围须重新评估当前产品和部署边界。

拆分与本地网关的请求体上限均为 25 MiB；业务 API 仍执行自己的限制，例如 Finance 报告文件最多 2 MiB。

## 启动与验证

以下命令从仓库根目录执行。固定独立项目名可避免与本地演示栈混用；确认配置只指向目标环境后再执行启动：

```bash
sdcompose() {
  docker compose --project-name signaldeck-split \
    --env-file "$HOME/.config/signaldeck/split.env" \
    -f docker/compose.production.example.yml "$@"
}
sdcompose config --quiet
sdcompose up -d --wait
sdcompose ps
curl --fail http://127.0.0.1:8080/health
sdcompose exec -T backend python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=5).read().decode())'
curl --silent --output /dev/null --write-out '%{http_code}\n' http://127.0.0.1:8080/api/workflow-packages
```

修改 `APP_PORT` 时同步修改 curl 地址。前端 `/health` 只检查 Nginx，后端 `/health` 只检查 API 存活，后端 `/ready` 才检查 PostgreSQL，期望 `{"status":"ok","database":"ok"}`。前端没有 `/ready` 代理，不能用该地址判断后端就绪。最后一个未带口令的 API 请求应为 `401`；在浏览器输入口令后确认任务页正常读取。

dispatcher 和 worker 没有容器健康探针，`up --wait` 不代表执行链路就绪。查看 `sdcompose logs --tail=100 dispatcher worker`，确认无持续连接/安装失败，并在隔离本地环境执行一项使用受控资源的工作流，核对终态、输出和调用证据；有模型或外部服务的流程需要独立确认访问与费用。本仓库的相关检查入口见[贡献指南](../CONTRIBUTING.md#检查测试与构建)。

空平台无需示例 YAML 或插件即可启动。拆分示例不会自动导入 `demo`、安装插件或配置资源；可通过专家制作或通用导入 API 添加包。普通模式的非敏感连接预设按[连接选择合同](../docs/writing-extensions.md#普通模式的连接选择)配置，需要自行给 backend 添加对应环境变量和只读文件挂载；仅在宿主机设置路径不会自动挂入此拆分示例。

## 可选插件与数据保留

插件的构建命令和配置见 [`plugins/README.md`](../plugins/README.md)。拆分示例提供 `finance`、`notes` 和 `digital-oracle` profiles；例如使用 `sdcompose --profile notes up -d --wait` 前，先构建 Notes 镜像并在实例 env 中设置 `NOTES_DATABASE_URL`。Finance 对应 `FINANCE_DATABASE_URL`；可用 `SIGNALDECK_NOTES_IMAGE`、`SIGNALDECK_FINANCE_IMAGE`、`SIGNALDECK_ORACLE_IMAGE` 指定镜像。Oracle 的外部服务配置由插件文档说明。

启用 profile 只启动服务，不会自动向 Core 登记。通过通用插件目录安装精确发布描述，按[统一插件页面合同](../docs/writing-extensions.md#统一插件页面)将同一挂载文件提供给 backend 和 frontend。更新文件后重新创建这两个容器以载入映射；API 和插件认证代理通过 Docker DNS 重新解析后端地址，后端容器 IP 变化无需手动重启前端。旧 Run 引用的插件制品与 endpoint 必须继续保留，不能原地换成新发布。

Compose 命名卷保存 `/data/artifacts`、`/data/core`、`/data/core-environments` 和 `/data/uv-cache`，由 API、dispatcher、worker 共用。保留同一项目名以继续使用原卷；升级不能清空产物、固定 Core 制品或执行环境。另行保留 PostgreSQL、Temporal 历史、实例配置和原加密 key，插件数据库由插件分别保存。保留和恢复要求以[架构说明](../docs/架构说明.md)和[数据模型](../docs/data-model.md)为准。

`sdcompose stop` 停止服务，`sdcompose down` 移除容器/网络但保留命名卷。不要使用 `down -v` 删除实例数据。需要空白本地验证时使用新的项目名、独立数据库、独立 Temporal 和不冲突端口，不连接或重置已有实例。
