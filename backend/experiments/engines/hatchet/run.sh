#!/usr/bin/env bash
set -euo pipefail
probe_dir="$(cd "$(dirname "$0")" && pwd)"
export SD_HATCHET_STATE="$(mktemp -d /tmp/signaldeck-hatchet.XXXXXX)"
export SD_HATCHET_CLIENT="$SD_HATCHET_STATE/client.json"
printf 'Evidence: %s\n' "$SD_HATCHET_STATE"
uv venv --python 3.13.13 "$SD_HATCHET_STATE/venv"
uv pip sync --python "$SD_HATCHET_STATE/venv/bin/python" "$probe_dir/requirements.lock"
"$SD_HATCHET_STATE/venv/bin/python" "$probe_dir/engine.py" > "$SD_HATCHET_STATE/engine.log" 2>&1 &
engine_pid=$!
trap 'kill -TERM "$engine_pid" 2>/dev/null || true; wait "$engine_pid" || true' EXIT
for _ in {1..180}; do
  if test -f "$SD_HATCHET_CLIENT"; then break; fi
  if ! kill -0 "$engine_pid" 2>/dev/null; then cat "$SD_HATCHET_STATE/engine.log"; exit 1; fi
  sleep 1
done
test -f "$SD_HATCHET_CLIENT"
"$SD_HATCHET_STATE/venv/bin/python" "$probe_dir/run_probe.py" > "$SD_HATCHET_STATE/probe.log" 2>&1
cat "$SD_HATCHET_STATE/report.json"
