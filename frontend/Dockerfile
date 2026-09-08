FROM node:26-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS base

WORKDIR /app

RUN apk add --no-cache libc6-compat curl \
    && npm install -g pnpm@10.30.1

FROM base AS build

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
ARG VITE_API_BASE_URL=
ARG VITE_GIT_RUN_NUMBER=local
ARG VITE_GIT_REVISION=unknown
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_GIT_RUN_NUMBER=$VITE_GIT_RUN_NUMBER
ENV VITE_GIT_REVISION=$VITE_GIT_REVISION
RUN pnpm run build

FROM nginx:alpine@sha256:72ba65eb42c10344912a84ff42408db7d34f2feb642204570ab8fc5ffd29f1d3 AS runner

ENV PORT=3000
ENV BACKEND_UPSTREAM=127.0.0.1:8000

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O - "http://127.0.0.1:${PORT:-3000}/health" >/dev/null || exit 1
