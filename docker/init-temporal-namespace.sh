#!/bin/sh
set -eu

attempt=0
until temporal operator cluster health >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then
        echo "Temporal cluster did not become ready" >&2
        exit 1
    fi
    sleep 1
done

if ! temporal operator namespace describe --namespace default >/dev/null 2>&1; then
    temporal operator namespace create --namespace default --retention 7d
fi
