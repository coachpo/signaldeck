#!/bin/bash
set -euo pipefail

export PORT="${PORT:-8080}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export SIGNALDECK_RUNTIME_MODE="${SIGNALDECK_RUNTIME_MODE:-production}"
role="${1:-app}"
if [ "$#" -gt 0 ]; then shift; fi
case "$role" in
  app|dispatcher|worker)
    # Reuse the API configuration contract before starting any long-lived process.
    python -c 'from app.core.config import get_settings; get_settings()'
    ;;
  # Plugin roles are independent services that never load the Core configuration;
  # each runs from its own frozen virtual environment.
  finance)
    exec finance-python -m uvicorn finance_plugin.main:create_app --factory \
      --host 0.0.0.0 --port 8000 --no-access-log "$@"
    ;;
  notes)
    exec notes-python -m uvicorn notes_plugin.main:create_app --factory \
      --host 0.0.0.0 --port 8000 --no-access-log "$@"
    ;;
  digital-oracle)
    exec digital-oracle-python -m uvicorn oracle_plugin.main:app \
      --host 0.0.0.0 --port 8000 --no-access-log "$@"
    ;;
  *) exec "$role" "$@" ;;
esac

case "$role" in
  dispatcher) exec python -m app.workers.command_dispatcher "$@" ;;
  worker) exec python -m app.workers.artifact_worker --serve "$@" ;;
esac

mkdir -p /run/nginx
python /opt/signaldeck/gateway/generate.py
envsubst '${PORT} ${BACKEND_PORT}' \
  </etc/nginx/templates/default.conf.template \
  >/etc/nginx/conf.d/default.conf
nginx -t

pids=()
shutdown() {
  trap '' TERM INT
  kill -TERM "${pids[@]}" 2>/dev/null || true
  wait "${pids[@]}" 2>/dev/null || true
}
trap 'shutdown; exit 0' TERM INT

uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" --no-access-log "$@" &
pids+=("$!")
nginx -g 'daemon off;' &
pids+=("$!")

# Losing either half makes the app unavailable; let the container policy restart it.
if wait -n; then status=1; else status=$?; fi
shutdown
exit "$status"
