#!/bin/sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${APP_DB_USER:?APP_DB_USER is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"

if [ "$APP_DB_USER" = "$POSTGRES_USER" ]; then
  echo "APP_DB_USER must differ from POSTGRES_USER" >&2
  exit 1
fi
if [ "$APP_DB_PASSWORD" = "$POSTGRES_PASSWORD" ]; then
  echo "APP_DB_PASSWORD must differ from POSTGRES_PASSWORD" >&2
  exit 1
fi

export PGPASSWORD="$POSTGRES_PASSWORD"

psql \
  --host "${PGHOST:-/var/run/postgresql}" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=1 \
  --set database="$POSTGRES_DB" \
  --set owner_user="$POSTGRES_USER" \
  --set app_user="$APP_DB_USER" \
  --set app_password="$APP_DB_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'app_user', :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'app_user', :'app_password'
)
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database', :'app_user')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user')
\gexec

SELECT format(
  'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I.%I TO %I',
  schemaname, tablename, :'app_user'
)
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename !~ '^audit_logs(?:_|$)'
ORDER BY tablename
\gexec

SELECT format(
  'GRANT SELECT, INSERT ON TABLE %I.%I TO %I',
  schemaname, tablename, :'app_user'
)
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename ~ '^audit_logs(?:_|$)'
ORDER BY tablename
\gexec

SELECT format(
  'GRANT USAGE, SELECT ON SEQUENCE %I.%I TO %I',
  sequence_schema, sequence_name, :'app_user'
)
FROM information_schema.sequences
WHERE sequence_schema = 'public'
ORDER BY sequence_name
\gexec

SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO %I',
  :'owner_user', :'app_user'
)
\gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I',
  :'owner_user', :'app_user'
)
\gexec

SELECT format(
  'REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM %I',
  :'app_user'
)
\gexec
SQL
