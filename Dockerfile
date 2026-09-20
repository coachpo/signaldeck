FROM node:26-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS frontend-builder

ARG VITE_API_BASE_URL=/api
ARG VITE_GIT_RUN_NUMBER=local
ARG VITE_GIT_REVISION=unknown

WORKDIR /source/frontend

RUN apk add --no-cache libc6-compat curl \
    && npm install -g pnpm@10.30.1

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN VITE_API_BASE_URL="$VITE_API_BASE_URL" \
    VITE_GIT_RUN_NUMBER="$VITE_GIT_RUN_NUMBER" \
    VITE_GIT_REVISION="$VITE_GIT_REVISION" pnpm run build
# The plugin page bundle is written to /source/plugins/runtime/plugin_runtime/web.
RUN pnpm run build:plugin-ui

FROM python:3.13.13-slim@sha256:aa938a849bcb82dce8f49480f056ab82bf5c1c3ebc294f0430f37b6820e7f286 AS runtime

LABEL org.opencontainers.image.title="SignalDeck" \
      org.opencontainers.image.description="SignalDeck application, dispatcher, immutable Core worker and independent business plugins"

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

# Each plugin keeps its own frozen lock and virtual environment; they share only
# the source-distributed runtime, so their artifact digests stay independent.
COPY plugins/finance/pyproject.toml plugins/finance/uv.lock /plugins/finance/
COPY plugins/notes/pyproject.toml plugins/notes/uv.lock /plugins/notes/
COPY plugins/digital_oracle/pyproject.toml plugins/digital_oracle/uv.lock /plugins/digital_oracle/
RUN set -eu; \
    for project in finance notes digital_oracle; do \
        (cd "/plugins/$project" \
            && UV_NO_CACHE=1 uv sync --frozen --no-dev --no-install-project \
                --python /usr/local/bin/python3.13); \
        name="$(echo "$project" | tr _ -)"; \
        printf '#!/bin/sh\nexport PYTHONPATH=/plugins/runtime:/plugins/%s\nexec /plugins/%s/.venv/bin/python "$@"\n' \
            "$project" "$project" >"/usr/local/bin/$name-python"; \
        chmod +x "/usr/local/bin/$name-python"; \
    done

COPY backend/app ./app
COPY --from=frontend-builder /source/frontend/dist /usr/share/nginx/html
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker/plugin-mounts.empty.json /etc/signaldeck/plugin-mounts.json
COPY docker/entrypoint.sh /entrypoint.sh
COPY frontend/gateway /opt/signaldeck/gateway
COPY docker/bootstrap_plugins.py docker/prepare_plugin_mounts.py docker/initialize_plugin_mounts.py docker/plugin-defaults.json /opt/signaldeck/
COPY plugins/runtime /plugins/runtime
COPY --from=frontend-builder /source/plugins/runtime/plugin_runtime/web /plugins/runtime/plugin_runtime/web
COPY plugins/finance /plugins/finance
COPY plugins/notes /plugins/notes
COPY plugins/digital_oracle /plugins/digital_oracle

RUN chmod +x /entrypoint.sh \
    && mkdir -p /run/nginx \
    && chown -R www-data:www-data /usr/share/nginx/html

EXPOSE 8080 8000

HEALTHCHECK --interval=5s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, sys, urllib.request; port = os.environ.get('PORT', '8080'); url = f'http://127.0.0.1:{port}/ready'; sys.exit(0 if urllib.request.urlopen(url, timeout=3).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["app"]
