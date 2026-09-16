FROM node:26-alpine@sha256:ef24c5053d50fdc3e4e56eb4e7ddb7861874ab0fdc797046ba897581deb8e868 AS frontend-builder

ARG VITE_API_BASE_URL=/api
ARG VITE_GIT_RUN_NUMBER=local
ARG VITE_GIT_REVISION=unknown

WORKDIR /app

RUN apk add --no-cache libc6-compat curl \
    && npm install -g pnpm@10.30.1

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN VITE_API_BASE_URL="$VITE_API_BASE_URL" \
    VITE_GIT_RUN_NUMBER="$VITE_GIT_RUN_NUMBER" \
    VITE_GIT_REVISION="$VITE_GIT_REVISION" pnpm run build

FROM python:3.13.13-slim@sha256:aa938a849bcb82dce8f49480f056ab82bf5c1c3ebc294f0430f37b6820e7f286 AS runtime

LABEL org.opencontainers.image.title="SignalDeck" \
      org.opencontainers.image.description="SignalDeck application, dispatcher and immutable Core worker"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    SIGNALDECK_RUNTIME_MODE=production \
    PORT=8080 \
    BACKEND_PORT=8000 \
    SIGNALDECK_CORE_PYTHON_VERSION=3.13.13 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash nginx gettext-base ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/conf.d/default.conf /etc/nginx/sites-enabled/default
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /uvx /bin/
COPY backend/pyproject.toml backend/uv.lock backend/README.md backend/VERSION ./
RUN UV_NO_CACHE=1 uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY --from=frontend-builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker/plugin-mounts.empty.json /etc/signaldeck/plugin-mounts.json
COPY docker/entrypoint.sh /entrypoint.sh
COPY frontend/gateway /opt/signaldeck/gateway
COPY docker/bootstrap_plugins.py docker/prepare_plugin_mounts.py docker/initialize_plugin_mounts.py docker/plugin-defaults.json /opt/signaldeck/

RUN chmod +x /entrypoint.sh \
    && mkdir -p /run/nginx \
    && chown -R www-data:www-data /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, sys, urllib.request; port = os.environ.get('PORT', '8080'); url = f'http://127.0.0.1:{port}/ready'; sys.exit(0 if urllib.request.urlopen(url, timeout=3).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["app"]
