FROM node:26-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS frontend-builder

ARG VITE_API_BASE_URL=/api

WORKDIR /app

RUN apk add --no-cache libc6-compat curl \
    && npm install -g pnpm@10.30.1

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN VITE_API_BASE_URL="$VITE_API_BASE_URL" pnpm run build

FROM python:3.13.13-slim@sha256:aa938a849bcb82dce8f49480f056ab82bf5c1c3ebc294f0430f37b6820e7f286 AS runtime

LABEL org.opencontainers.image.title="SignalDeck local/demo combined image" \
      org.opencontainers.image.description="Local/demo-only combined SignalDeck app; not a supported production artifact." \
      io.signaldeck.support="local-demo-only" \
      io.signaldeck.production-artifact="false"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    SIGNALDECK_RUNTIME_MODE=local \
    SIGNALDECK_ROOT_IMAGE_SCOPE=local-demo-only \
    PORT=8080 \
    BACKEND_PORT=8000 \
    SIGNALDECK_CORE_PYTHON_VERSION=3.13.13 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx supervisor gettext-base ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/conf.d/default.conf /etc/nginx/sites-enabled/default
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a /uv /uvx /bin/
COPY backend/pyproject.toml backend/uv.lock backend/README.md backend/VERSION ./
RUN UV_NO_CACHE=1 uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY --from=frontend-builder /app/dist /usr/share/nginx/html
COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/bootstrap_plugins.py docker/plugin-defaults.json /opt/signaldeck/

RUN chmod +x /entrypoint.sh \
    && mkdir -p /etc/supervisor/conf.d /var/log/supervisor /run/nginx \
    && chown -R www-data:www-data /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, sys, urllib.request; port = os.environ.get('PORT', '8080'); url = f'http://127.0.0.1:{port}/ready'; sys.exit(0 if urllib.request.urlopen(url, timeout=3).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
