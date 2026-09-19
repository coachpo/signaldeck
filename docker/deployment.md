# 单应用镜像部署

正式应用镜像为 `ghcr.io/coachpo/signaldeck`，包含前端静态资源、Nginx 和 Core 后端。`app` 容器运行 Nginx/API，`dispatcher` 和 `worker` 使用同一镜像的对应角色；PostgreSQL、Temporal 和业务插件仍独立运行。唯一正式 Compose 入口是 [`compose.production.yml`](compose.production.yml)。根 `docker-compose.yml` 和 `start.sh` 保留源码本地开发用途。

当前适用边界仍是可信内网、单用户、单机部署。应用和公开业务 API 无需访问口令，只向可信网络开放应用端口，不提供高可用或公网服务承诺。服务器无需编译应用源码；固定 Core worker 首次安装某个制品的依赖时仍需访问锁文件中的公共下载地址。后续复用保留的执行环境和缓存。

## 发布与镜像版本

镜像只由 [`release.sh`](../CONTRIBUTING.md#发布) 创建的 `v*` 标签发布。[`Docker Images`](../.github/workflows/docker-images.yml) 先等待该标签提交上的 CI 全部通过，未通过即拒绝发布；随后在原生 ARM runner 上构建应用镜像与三个独立插件镜像，只出 `linux/arm64` 单 manifest，不附带 provenance/SBOM，标签为 `vX.Y.Z`、`X.Y.Z`、`X.Y`、`sha-<完整提交 SHA>` 和 `latest`。推送 main 和 PR 不发布镜像，四个镜像的构建与单机部署冒烟由 CI 的 `container-images` job 覆盖。手动运行可选 `app` 或任一插件，只发布 `manual-<sha>` 标签，不移动 `latest`。Actions 使用仓库 `GITHUB_TOKEN`，无需服务器 SSH 密钥。

日常应用更新使用明确的发布版本，建议固定为 `ghcr.io/coachpo/signaldeck:vX.Y.Z@sha256:<digest>`；`latest` 指向最近一次发布。插件须独立固定到已发布的完整 SHA 标签、版本标签或 digest；这样普通 `pull` 不会将历史 endpoint 原地换成新插件。插件发布版本号与 Git 镜像标签不是同一概念。

capy 上的实例由部署仓库 `coachpo/curse` 的 `signaldeck/` 栈及其 `deploy.sh` 管理，不使用本文的检出目录。巡检、备份与恢复演练、发布和带门禁的部署分别由 [`signaldeck-ops-inspect`](../.agents/skills/signaldeck-ops-inspect/SKILL.md)、[`signaldeck-backup-restore`](../.agents/skills/signaldeck-backup-restore/SKILL.md) 和 [`signaldeck-release-deploy`](../.agents/skills/signaldeck-release-deploy/SKILL.md) 执行。

GHCR 镜像设为 Public 后可以匿名拉取；私有镜像需在服务器用具有 `read:packages` 的 classic PAT 执行 `docker login ghcr.io -u <用户名>`，在交互提示输入 token。公开仓库不意味着镜像包自动公开。参见 [GitHub Container registry 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。

## 首次部署

需要 Docker Compose **2.20 或以上**，并确认四个镜像已发布成功。配置和密钥保存在仓库/build context 之外，项目名与卷独立于 Prism。以下是新实例命令，已有检出/配置不重复创建：

```bash
ssh capy
mkdir -p ~/apps
git clone https://github.com/coachpo/signaldeck.git ~/apps/signaldeck
cd ~/apps/signaldeck
git checkout vX.Y.Z

# 检出的发布提交的四个镜像必须已经发布成功。
python3 docker/create_env.py --plugin-tag "sha-$(git rev-parse HEAD)"
```

`create_env.py` 按 [`production.env.example`](production.env.example) 生成 `~/.config/signaldeck/production.env`，自动生成五个独立数据库密码和一个资源加密 key，权限为 0600；已有文件拒绝覆盖，不输出密钥。默认应用跟随最近一次发布（`latest`），三个插件固定到指定 SHA；可加 `--app-image ghcr.io/coachpo/signaldeck:<版本>` 固定应用。

检查配置中的 `APP_PORT`，默认 8089。此前只读检查发现 capy 的 8087/8088 被 Prism 占用；启动前仍需核对当前端口。保留同一个项目名和原配置文件，不要为更新重新生成密码。

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

Compose 自动初始化独立数据库、Temporal schema 和 default namespace，随后启动执行服务，准备插件页面挂载并登记缺失插件。初始化服务完成后 `Exited (0)` 是正常状态；`wait bootstrap` 只表示登记步骤结束，不代表外部模型/provider 可用。数据库、Temporal RPC 和插件端口均不发布到宿主机；仅 app 绑定 `127.0.0.1:8089`。

本机访问可执行 `ssh -N -L 8089:127.0.0.1:8089 capy`，然后直接打开 `http://localhost:8089`；也可接入已有可信反向代理。应用镜像不包含示例工作流，默认 Compose 不挂载或导入工作流数据。空平台通过专家制作或公开导入 API 添加 Workflow；`demo/` 仅供阅读和用户手工选取示例，不参与平台部署或验证。模型凭据通过资源表单保存，不能放到 YAML、镜像构建参数或前端环境变量中。

## 日常更新

保持在同一检出目录、使用同一份 env 和项目名。应用跟随最近一次发布（`latest`）时通常只需：

```bash
sdcompose pull
sdcompose up -d
```

应用的三个角色会使用同一个新镜像；固定版本的插件和已有数据库保持原制品/数据。应用固定版本时，先修改 `SIGNALDECK_IMAGE`，再执行上述命令。升级前核对是否另含数据库或 Temporal schema 变化：Core 的 `create_all` 只创建缺失表，不升级已有表，也不保证旧程序可读取新数据。`SIGNALDECK_IMAGE` 指向新镜像后，`sdcompose run --rm --no-deps -T --entrypoint python app -m app.infrastructure.schema_compatibility` 可在切换前只读核对现有库，退出码 1 表示不兼容。普通 `stop`/`down` 保留命名卷，**不要运行 `down -v` 更新实例**。

插件升级是单独操作：保留旧镜像、服务 endpoint 和旧页面挂载，再为新发布配置独立服务/上游并登记。自动挂载初始化保留历史记录，拒绝将同一上游原地绑定到另一个制品。不能只把旧服务的插件 tag 改为新版本再 `up`；具体身份与升级约束见[插件接入](../docs/writing-extensions.md#统一插件页面)。

## 配置与持久化

| 配置 | 用途 |
| --- | --- |
| `SIGNALDECK_IMAGE` | app、dispatcher、worker 和初始化工具共用的应用镜像。 |
| 三个 `SIGNALDECK_*_IMAGE` 插件变量 | 各插件的独立固定镜像引用。 |
| `COMPOSE_PROFILES` / `SIGNALDECK_PLUGINS` | 默认启用三个插件；选用部分插件时两者保持一致；同时设为空可启动通用平台。 |
| 五个数据库密码变量 | 分别用于 bootstrap、Core、Finance、Notes、Temporal 角色，由脚本生成随机 hex 值。 |
| 三个数据库 URL / `TEMPORAL_ADDRESS` | 默认使用本项目内网服务名，URL 从密码变量派生。不要将 env 文件作为 shell 脚本 source。 |
| `AGENT_PLATFORM_ENCRYPTION_KEY` | 资源凭据加密 key；必须保留，更换会使原密文无法解密。 |
| `APP_PORT` | 默认 8089，仅绑定回环地址。 |
| `CORS_ALLOWED_ORIGINS` | 默认空；同源 `/api` 和插件代理不需要跨源配置。 |

Oracle 外部 provider 配置按[插件说明](../plugins/README.md)提供，运行涉及的外部调用另行确认凭据及费用。前端 API 固定使用同源 `/api`，Nginx 转发到同容器回环地址上的 API；只有 Nginx 对容器网络监听。网关请求体上限 25 MiB，业务 API 仍执行自己的限制。

保留全部项目卷：`capy-postgres` 保存五个 PostgreSQL 数据库，`target-artifacts`、`target-core`、`target-core-environments` 和 `target-uv-cache` 保存产物、固定 Core 制品、执行环境与依赖缓存；`plugin-mounts` 保存插件页面身份。卷名由 Compose 项目名限定，沿用已有卷键以避免无意切换存储。备份还需包含仓库外 env 文件。

Temporal Server 1.31.2 使用 PostgreSQL 主库/visibility 库，固定 schema 目标为 1.19/1.14，不使用 start-dev。新 default namespace 已完成执行历史保留 7 天；Core 数据库中的运行记录和产物不按这个期限删除。重复初始化保留既有 namespace 设置；升级 Temporal 及其 schema 需单独验证。Temporal 无 TLS/认证，仅供本项目内网使用。依据：[官方自托管说明](https://docs.temporal.io/self-hosted-guide/deployment)。

已有拆分实例切换不能仅替换镜像变量：需保留原项目名、数据库、密钥及 Core/插件卷，先核对新旧挂载和 endpoint。仓库不会自动迁移或删除现有实例数据。

## 健康检查与本地验证

```bash
curl --fail http://127.0.0.1:8089/ready
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  http://127.0.0.1:8089/api/workflow-packages
sdcompose run --rm --no-deps --entrypoint temporal \
  temporal-namespace operator cluster health
```

`/health` 表示 API 存活并返回发布版本，`/ready` 通过 Nginx 检查 API 与 PostgreSQL，上述不带凭据的工作流列表请求应返回 200。这些检查不代替一次实际工作流；dispatcher/worker 没有 HTTP 探针。查看 `sdcompose logs --tail=100 app dispatcher worker bootstrap plugin-mounts`，确认执行终态、结果和证据，不能只看首页或容器 running。

本地构建与隔离验证：

```bash
docker build -t signaldeck:local .
docker build -f plugins/notes/Dockerfile -t signaldeck-notes:1.3.0 .
backend/.venv/bin/python docker/verify_deployment.py \
  --app-image signaldeck:local --notes-image signaldeck-notes:1.3.0
```

验证器使用本机 Docker、随机项目名/端口/密码，验证无需口令访问、数据库隔离、自动挂载/登记、真实 Notes 任务、SIGTERM、容器重建后的计划/Temporal 历史/制品/产物，以及执行服务离线后的历史读取，只清理本次自有测试资源。它不读取仓库 `.env`、不访问 capy，不使用真实模型服务。完整质量检查见[贡献指南](../CONTRIBUTING.md)。

可加 `--finance-image <已构建镜像>` 和 `--oracle-image <已构建镜像>` 同时验证另外两个插件的启动、登记与可用页面；不会调用真实外部 provider。
