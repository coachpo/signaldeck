#!/bin/sh
set -eu

# Only the fresh PostgreSQL volume bootstrap runs this script.
psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 \
  --set temporal_password="$TEMPORAL_DB_PASSWORD" <<'SQL'
CREATE ROLE signaldeck_temporal LOGIN PASSWORD :'temporal_password';
CREATE DATABASE signaldeck_temporal OWNER signaldeck_temporal;
CREATE DATABASE signaldeck_temporal_visibility OWNER signaldeck_temporal;
REVOKE CONNECT ON DATABASE signaldeck_temporal FROM PUBLIC;
REVOKE CONNECT ON DATABASE signaldeck_temporal_visibility FROM PUBLIC;
GRANT CONNECT ON DATABASE signaldeck_temporal TO signaldeck_temporal;
GRANT CONNECT ON DATABASE signaldeck_temporal_visibility TO signaldeck_temporal;
\connect signaldeck_temporal_visibility
CREATE EXTENSION IF NOT EXISTS btree_gin;
SQL
