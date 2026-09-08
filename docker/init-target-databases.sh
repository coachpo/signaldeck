#!/bin/sh
set -eu

# The bootstrap administrator owns no application table. Each service receives
# only its database role, so plugins cannot read Core's private relations.
psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 \
  --set core_password="$CORE_DB_PASSWORD" \
  --set finance_password="$FINANCE_DB_PASSWORD" \
  --set notes_password="$NOTES_DB_PASSWORD" <<'SQL'
CREATE ROLE signaldeck_core LOGIN PASSWORD :'core_password';
CREATE ROLE signaldeck_finance LOGIN PASSWORD :'finance_password';
CREATE ROLE signaldeck_notes LOGIN PASSWORD :'notes_password';
CREATE DATABASE signaldeck_core OWNER signaldeck_core;
CREATE DATABASE signaldeck_finance OWNER signaldeck_finance;
CREATE DATABASE signaldeck_notes OWNER signaldeck_notes;
REVOKE CONNECT ON DATABASE signaldeck_core FROM PUBLIC;
REVOKE CONNECT ON DATABASE signaldeck_finance FROM PUBLIC;
REVOKE CONNECT ON DATABASE signaldeck_notes FROM PUBLIC;
GRANT CONNECT ON DATABASE signaldeck_core TO signaldeck_core;
GRANT CONNECT ON DATABASE signaldeck_finance TO signaldeck_finance;
GRANT CONNECT ON DATABASE signaldeck_notes TO signaldeck_notes;
SQL
