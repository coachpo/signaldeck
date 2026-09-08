FROM python:3.14.0-slim@sha256:0aecac02dc3d4c5dbb024b753af084cafe41f5416e02193f1ce345d671ec966e
COPY --from=ghcr.io/astral-sh/uv:0.9.8@sha256:08f409e1d53e77dfb5b65c788491f8ca70fe1d2d459f41c89afa2fcbef998abe /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /plugins/finance
COPY finance/pyproject.toml finance/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY runtime /plugins/runtime
COPY finance /plugins/finance
ENV PYTHONPATH=/plugins/runtime:/plugins/finance PATH=/plugins/finance/.venv/bin:$PATH
EXPOSE 8000
CMD ["uvicorn", "finance_plugin.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
