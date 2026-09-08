#!/bin/sh
set -eu

export PORT="${PORT:-8080}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export SIGNALDECK_RUNTIME_MODE="${SIGNALDECK_RUNTIME_MODE:-local}"
case "$SIGNALDECK_RUNTIME_MODE" in
  production|prod|staging)
    echo 'Use the split backend/frontend images for production.' >&2
    exit 1
    ;;
esac

mkdir -p /run/nginx
# This image contains the API and web surface. Durable workers and command
# delivery run as separate Compose services from the same Core source closure.
envsubst '${PORT} ${BACKEND_PORT}' \
  </etc/nginx/templates/default.conf.template \
  >/etc/nginx/conf.d/default.conf
nginx -t
exec supervisord -n -c /etc/supervisor/supervisord.conf
