#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-signaldeck-target-local}"
export SIGNALDECK_DATA_DIR="${SIGNALDECK_DATA_DIR:-$ROOT_DIR/.signaldeck-target}"
export SIGNALDECK_LOCAL_UID="${SIGNALDECK_LOCAL_UID:-$(id -u)}"
export SIGNALDECK_LOCAL_GID="${SIGNALDECK_LOCAL_GID:-$(id -g)}"
export SIGNALDECK_PLUGINS="${SIGNALDECK_PLUGINS-finance,digital-oracle,notes}"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  printf 'Docker with Docker Compose is required.\n' >&2
  exit 1
fi

# Reuse the registry path for status/logs/refresh as well as startup.
if [[ -z "${SIGNALDECK_PLUGIN_MOUNTS_FILE:-}" && -f "$SIGNALDECK_DATA_DIR/plugin-mounts.json" ]]; then
  export SIGNALDECK_PLUGIN_MOUNTS_FILE="$SIGNALDECK_DATA_DIR/plugin-mounts.json"
  generated_registry=1
else
  generated_registry=0
fi
cd "$ROOT_DIR"
compose=(docker compose --project-name "$COMPOSE_PROJECT_NAME" -f docker-compose.yml)
IFS=',' read -r -a plugins <<<"$SIGNALDECK_PLUGINS"
for plugin in "${plugins[@]:-}"; do
  if [[ -n "$plugin" ]]; then
    compose+=(--profile "$plugin")
  fi
done

case "${1:-up}" in
  stop|down)
    action="$1"
    shift
    if [[ $# -gt 0 ]]; then
      printf 'Use %s without extra arguments; target data is retained.\n' "$action" >&2
      exit 1
    fi
    printf 'Stopping project %s; target data will be retained.\n' "$COMPOSE_PROJECT_NAME"
    exec "${compose[@]}" "$action"
    ;;
  refresh-plugins)
    exec "${compose[@]}" run --rm -e SIGNALDECK_BOOTSTRAP_REFRESH=1 bootstrap
    ;;
  status)
    exec "${compose[@]}" ps
    ;;
  logs)
    shift
    exec "${compose[@]}" logs -f "$@"
    ;;
  up)
    if [[ $# -gt 0 ]]; then shift; fi
    ;;
  --detach|-d)
    ;;
  *)
    printf 'Usage: ./start.sh [up [--detach] | stop | down | status | logs [service] | refresh-plugins]\n' >&2
    exit 1
    ;;
esac

mkdir -p "$SIGNALDECK_DATA_DIR"/{postgres,temporal,artifacts,core,core-environments,uv-cache}
SIGNALDECK_DATA_DIR="$(cd "$SIGNALDECK_DATA_DIR" && pwd)"
export SIGNALDECK_DATA_DIR

"${compose[@]}" build
# An explicitly supplied registry is deployment-owned. Otherwise derive mounts
# from the built images before Core or Nginx starts; no plugin/database is started.
if [[ -z "${SIGNALDECK_PLUGIN_MOUNTS_FILE:-}" || "$generated_registry" == 1 ]]; then
  export SIGNALDECK_PLUGIN_MOUNTS_FILE="$SIGNALDECK_DATA_DIR/plugin-mounts.json"
  if [[ ! -f "$SIGNALDECK_PLUGIN_MOUNTS_FILE" ]]; then
    cp docker/plugin-mounts.empty.json "$SIGNALDECK_PLUGIN_MOUNTS_FILE"
  fi
  descriptor_dir="$(mktemp -d "$SIGNALDECK_DATA_DIR/plugin-descriptors.XXXXXX")"
  trap 'rm -rf "$descriptor_dir"' EXIT
  "${compose[@]}" run --no-deps --rm -T --entrypoint python app \
    /opt/signaldeck/prepare_plugin_mounts.py --factories "$SIGNALDECK_PLUGINS" >"$descriptor_dir/factories"
  while read -r plugin factory; do
    if ! "${compose[@]}" run --no-deps --rm -T --entrypoint python "$plugin" \
      -m plugin_runtime.describe "$factory" >"$descriptor_dir/$plugin.json" </dev/null; then
      rm -f "$descriptor_dir/$plugin.json"
      printf 'Plugin page unavailable: %s; Core remains usable.\n' "$plugin" >&2
    fi
  done <"$descriptor_dir/factories"
  SIGNALDECK_PLUGIN_MOUNTS_REVISION="$("${compose[@]}" run --no-deps --rm -T \
    -v "$SIGNALDECK_DATA_DIR:/mounts" --entrypoint python app \
    /opt/signaldeck/prepare_plugin_mounts.py "/mounts/$(basename "$descriptor_dir")")"
  rm -rf "$descriptor_dir"
  trap - EXIT
else
  SIGNALDECK_PLUGIN_MOUNTS_REVISION="$("${compose[@]}" run --no-deps --rm -T --entrypoint python app \
    /opt/signaldeck/prepare_plugin_mounts.py --revision /etc/signaldeck/plugin-mounts.json)"
fi
# A changed registry recreates the combined Core/gateway, refreshing file bind
# inodes and generated Nginx locations even when the app image is unchanged.
export SIGNALDECK_PLUGIN_MOUNTS_REVISION

printf 'Starting target project %s.\n' "$COMPOSE_PROJECT_NAME"
printf 'Data: %s\n' "$SIGNALDECK_DATA_DIR"
printf 'SignalDeck: http://localhost:%s\n' "${APP_PORT:-8080}"
printf 'Plugin pages: available inside SignalDeck when enabled.\n'
printf 'Ctrl+C stops services; named target data is retained.\n'
exec "${compose[@]}" up "$@"
