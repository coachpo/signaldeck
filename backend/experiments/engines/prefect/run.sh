#!/usr/bin/env bash
set -euo pipefail

probe_dir="$(cd "$(dirname "$0")" && pwd)"
probe_output="${1:-$(mktemp -d /tmp/sd-prefect-evidence.XXXXXX)}"
mkdir -p "$probe_output"
probe_output="$(cd "$probe_output" && pwd)"
if [[ -e "$probe_output/server.log" ]]; then
  echo "Use a new evidence directory; previous results will not be overwritten." >&2
  exit 2
fi
probe_venv="${SD_PREFECT_VENV:-$probe_output/venv}"
if [[ ! -x "$probe_venv/bin/python" ]]; then
  uv venv --python 3.13 "$probe_venv"
fi
uv pip sync --python "$probe_venv/bin/python" "$probe_dir/requirements.lock"
export PREFECT_HOME="$probe_output/server-home"
export PREFECT_SERVER_ANALYTICS_ENABLED=false
export PREFECT_LOGGING_LEVEL=INFO
probe_port="${SD_PREFECT_PORT:-44217}"
"$probe_venv/bin/python" -c \
  'import socket,sys; s=socket.socket(); s.bind(("127.0.0.1", int(sys.argv[1]))); s.close()' \
  "$probe_port"
export PREFECT_API_URL="http://127.0.0.1:$probe_port/api"
"$probe_venv/bin/prefect" server start --host 127.0.0.1 --port "$probe_port" --no-ui \
  >"$probe_output/server.log" 2>&1 &
probe_server_pid=$!
cleanup() {
  kill "$probe_server_pid" 2>/dev/null || true
  wait "$probe_server_pid" 2>/dev/null || true
}
trap cleanup EXIT
for _ in $(seq 1 120); do
  kill -0 "$probe_server_pid"
  if curl --silent --fail "$PREFECT_API_URL/health" >/dev/null; then
    break
  fi
  sleep 0.25
done
curl --silent --fail "$PREFECT_API_URL/health" >/dev/null
cd "$probe_dir"
for scenario in probe cancel_probe crash_ownership_probe auto_recovery_probe; do
  export SD_PREFECT_PROBE_ROOT="$probe_output/$scenario"
  "$probe_venv/bin/python" "$scenario.py" >"$probe_output/$scenario.log" 2>&1
  printf '%s: exit 0\n' "$scenario"
done
printf 'Evidence: %s\n' "$probe_output"
