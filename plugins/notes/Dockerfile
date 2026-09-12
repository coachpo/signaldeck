FROM node:26-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS plugin-ui
WORKDIR /source/frontend
RUN npm install -g pnpm@10.30.1
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./
RUN pnpm build:plugin-ui

FROM python:3.14.0-slim@sha256:0aecac02dc3d4c5dbb024b753af084cafe41f5416e02193f1ce345d671ec966e
COPY --from=ghcr.io/astral-sh/uv:0.9.8@sha256:08f409e1d53e77dfb5b65c788491f8ca70fe1d2d459f41c89afa2fcbef998abe /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /plugins/notes
COPY plugins/notes/pyproject.toml plugins/notes/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY plugins/runtime /plugins/runtime
COPY plugins/notes /plugins/notes
COPY --from=plugin-ui /source/plugins/runtime/plugin_runtime/web /plugins/runtime/plugin_runtime/web
ENV PYTHONPATH=/plugins/runtime:/plugins/notes PATH=/plugins/notes/.venv/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "notes_plugin.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
