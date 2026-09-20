# 单应用镜像部署

应用镜像 `ghcr.io/coachpo/signaldeck` 包含前端静态资源、Nginx、Core API 和三个业务插件：`app` 容器运行 Nginx 与 API，`dispatcher`、`worker`、`finance`、`notes`、`digital-oracle` 是同一镜像的独立角色，各插件在镜像内有自己的冻结锁文件和虚拟环境；PostgreSQL 和 Temporal 独立运行。服务器部署使用 [`compose.production.yml`](compose.production.yml)，根 `docker-compose.yml` 与 `start.sh` 只用于源码本地运行，适用边界见 [`STATUS.md`](../STATUS.md#部署与使用)。服务器不编译源码；固定 Core worker 首次安装某个制品的依赖时需要访问锁文件中的公共下载地址，之后复用保留的执行环境和 uv 缓存。

维护中的 capy 实例不按本文操作，而是由部署仓库的 `deploy.sh` 和 `.agents/skills/` 下的三个运维 skill 管理，见 [capy 适配说明](../.agents/skills/signaldeck-ops-inspect/references/capy.md)。

## 发布与镜像版本

发布流程见[贡献指南](../CONTRIBUTING.md#发布)。每个 `vX.Y.Z` 标签在 GHCR 发布一个镜像 `ghcr.io/coachpo/signaldeck`，是不附 provenance/SBOM 的 `linux/arm64` 单平台 manifest。标签为 `vX.Y.Z`、`X.Y.Z`、`X.Y`、`sha-<完整提交 SHA>` 和 `latest`，`latest` 只表示最近一次发布。手动运行 [`Docker Images`](../.github/workflows/docker-images.yml) 不选择服务，只发布 `manual-<完整提交 SHA>` 标签。

部署时把应用镜像固定为 `ghcr.io/coachpo/signaldeck:vX.Y.Z@sha256:<digest>`，digest 可用 `docker buildx imagetools inspect ghcr.io/coachpo/signaldeck:vX.Y.Z` 查看。插件角色用独立的 `SIGNALDECK_PLUGIN_IMAGE` 固定到自己的标签或 digest，可以与 `SIGNALDECK_IMAGE` 不同，普通 `pull` 因而不会把运行中的插件 endpoint 原地换成新发布。插件自身的版本号（`plugins/<插件>/VERSION`）是发布描述中的 `releaseId`，不是镜像标签。

Public 的 GHCR 包可匿名拉取；私有包需在服务器用具有 `read:packages` 的 classic PAT 执行 `docker login ghcr.io -u <用户名>`。公开仓库不会让镜像包自动公开。

## 首次部署

需要 arm64 宿主机、Docker Compose **2.20 或以上**（生产 Compose 使用 `depends_on.required`），且该发布的镜像已发布。`compose.production.yml` 以绑定挂载使用同目录的数据库与 Temporal 初始化脚本和 Temporal 动态配置，因此服务器检出与镜像相同的发布标签；配置和密钥保存在检出目录之外：

```bash
git clone https://github.com/coachpo/signaldeck.git ~/signaldeck
cd ~/signaldeck
git checkout vX.Y.Z
python3 docker/create_env.py \
  --app-image "ghcr.io/coachpo/signaldeck:vX.Y.Z@sha256:<digest>" \
  --plugin-tag "sha-$(git rev-parse HEAD)"
```

`create_env.py` 按 [`production.env.example`](production.env.example) 写入权限 0600 的 `~/.config/signaldeck/production.env`，生成五个独立数据库密码和资源加密 key，不输出密钥；文件已存在时拒绝覆盖。`--plugin-tag` 只接受 `sha-` 加 40 位小写十六进制，固定三个插件角色共用的 `SIGNALDECK_PLUGIN_IMAGE`；`--app-image` 必填，只接受 `<镜像>:vX.Y.Z`、`<镜像>:vX.Y.Z@sha256:<digest>` 或 `<镜像>@sha256:<digest>`，`latest` 等浮动标签会被拒绝。以后更新沿用同一个 env 文件和项目名，不重新生成密码或 key。

```bash
sdcompose() {
  docker compose -p signaldeck \
    --env-file "$HOME/.config/signaldeck/production.env" \
    -f docker/compose.production.yml "$@"
}
sdcompose config --quiet
sdcompose pull
sdcompose up -d
sdcompose wait bootstrap
sdcompose ps --all
```

Compose 依次初始化独立数据库、Temporal schema 和 default namespace，启动执行服务，准备插件页面挂载，最后由 bootstrap 登记缺失的插件发布和默认工具资源。一次性初始化服务结束后显示 `Exited (0)` 属正常；`wait bootstrap` 只表示登记步骤结束，不代表模型或外部 provider 可用。数据库、Temporal RPC 和插件端口都不发布到宿主机，只有 app 绑定 `127.0.0.1` 上的 `APP_PORT`（默认 8089）；从其他机器访问时执行 `ssh -N -L 8089:127.0.0.1:8089 <主机>` 后打开 `http://localhost:8089`，或接入可信反向代理。

新实例没有工作流，添加方式见[独立数据导入与分发](../docs/工作流解耦方案.md#独立数据导入与分发)。模型凭据只在应用的资源设置中填写，不写入 env 文件、镜像或工作流 YAML。

## 日常更新

在同一检出目录切换到新发布的标签，沿用原 env 文件和项目名。Core 的 `create_all` 只创建缺失的表、不修改已有表（规则见[数据模型](../docs/data-model.md)），因此切换前先用新镜像对现有数据库做只读兼容检查；退出码 1 表示不兼容，不要切换：

```bash
git fetch --tags && git checkout vX.Y.Z
new="ghcr.io/coachpo/signaldeck:vX.Y.Z@sha256:<digest>"
SIGNALDECK_IMAGE="$new" sdcompose run --rm --no-deps -T --entrypoint python app \
  -m app.infrastructure.schema_compatibility
```

检查通过后把 env 文件中的 `SIGNALDECK_IMAGE` 改为同一引用，再执行 `sdcompose pull` 和 `sdcompose up -d`。app、dispatcher、worker 以及 plugin-mounts、bootstrap 随 `SIGNALDECK_IMAGE` 一起切换；三个插件角色仍按 `SIGNALDECK_PLUGIN_IMAGE` 固定，数据卷不变。`stop` 和 `down` 保留命名卷；**不要使用 `down -v`**，它会删除全部数据卷。

插件升级不能只改旧服务的镜像标签再 `up`：运行和页面挂载绑定插件 endpoint 与制品 digest，新发布须作为新服务和新上游与旧服务并存，挂载初始化也拒绝把已登记的上游改绑到另一个制品。规则见[独立接入与升级](../docs/writing-extensions.md#独立接入与升级)。

## 配置与持久化

| 配置 | 说明 |
| --- | --- |
| `SIGNALDECK_IMAGE` | app、dispatcher、worker、plugin-mounts 和 bootstrap 共用的应用镜像，固定为带 digest 的发布引用。 |
| `SIGNALDECK_PLUGIN_IMAGE` | finance、notes 和 digital-oracle 角色共用、与应用独立固定的同一镜像；模板由 `SIGNALDECK_PLUGIN_TAG` 派生。 |
| `COMPOSE_PROFILES`、`SIGNALDECK_PLUGINS` | 启用的插件，模板为 `finance,notes,digital-oracle`；两者须一致，同时设为空只启动通用平台。 |
| `AGENT_PLATFORM_ENCRYPTION_KEY` | 资源凭据加密 key；更换后已保存的凭据无法解密。 |
| `APP_PORT` | 应用端口，默认 8089，只绑定 `127.0.0.1`。 |
| `EDGAR_CONTACT_EMAIL`、`FRED_API_KEY` | 模板中以注释占位，需要时在私有 env 文件中取消注释并填写；Compose 把前者传给 Finance 和 Oracle，后者只传给 Oracle，用途见[插件说明](../plugins/README.md#build-and-run)。 |

数据库密码、由其派生的数据库 URL 和 `TEMPORAL_ADDRESS` 保持生成值；env 文件只供 Compose 读取，不要作为 shell 脚本 `source`。浏览器经同源 `/api` 访问 API，Nginx 网关的请求体上限为 25 MiB。

保留全部项目卷：`capy-postgres` 保存五个 PostgreSQL 数据库，`target-artifacts`、`target-core`、`target-core-environments` 和 `target-uv-cache` 保存产物、固定 Core 制品、执行环境与可重新下载的依赖缓存，`plugin-mounts` 保存插件页面身份。卷名由 Compose 项目名限定；不要更换项目名或重命名卷键，否则实例会改用新的空卷。备份须包含这些卷和检出目录外的 env 文件（含数据库密码与加密 key）；[备份 skill](../.agents/skills/signaldeck-backup-restore/SKILL.md) 只支持部署仓库布局，不适用于本布局。

Temporal Server 1.31.2 使用 PostgreSQL 主库和 visibility 库，schema 目标固定为 1.19/1.14，不使用 start-dev。default namespace 的已完成执行历史保留 7 天；Core 数据库中的运行记录和产物不按这个期限删除。重复初始化保留已有 namespace 设置；升级 Temporal 及其 schema 需按[官方自托管说明](https://docs.temporal.io/self-hosted-guide/deployment)单独验证。Temporal 没有 TLS 或认证，只在本项目内网使用。

## 健康检查与本地验证

```bash
curl --fail http://127.0.0.1:8089/ready
curl --fail http://127.0.0.1:8089/health
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  http://127.0.0.1:8089/api/workflow-packages
sdcompose run --rm --no-deps --entrypoint temporal \
  temporal-namespace operator cluster health
```

`/ready` 经 Nginx 检查 API 与 PostgreSQL，数据库不可用时返回 503；`/health` 返回 API 状态和发布版本；不带凭据的工作流列表请求应返回 200。dispatcher 和 worker 没有 HTTP 探针，这些检查也不代替一次实际工作流运行：用 `sdcompose logs --tail=100 app dispatcher worker bootstrap plugin-mounts` 查看日志，并核对运行终态、结果和证据。

本地构建并隔离验证镜像：

```bash
docker build -t signaldeck:local .
backend/.venv/bin/python docker/verify_deployment.py --app-image signaldeck:local
```

验证器只使用本机 Unix socket Docker 上下文，以随机项目名、端口和密码启动 `compose.production.yml`，不读取仓库 `.env`，不调用模型或外部 provider，结束时只删除本次自有的容器、网络和卷。它启用全部三个插件角色，核对无口令访问、数据库角色隔离、插件挂载与登记、一次真实 Notes 任务、SIGTERM 平滑停止、容器重建后的计划、Temporal 历史、Core 制品与产物，以及执行服务离线时的历史读取。`--plugin-image <镜像>` 让插件角色使用另一个镜像，默认与 `--app-image` 相同。何时运行见[贡献指南](../CONTRIBUTING.md#检查测试与构建)。
