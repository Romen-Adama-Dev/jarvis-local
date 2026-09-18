#!/bin/sh
# Base de datos de OpenProject (perfil pm) dentro del PostgreSQL de Jarvis: rol y base
# "openproject" con la contraseña que generó init. Idempotente; también actualiza la
# contraseña si se cambió en .env.
set -eu

export PGHOST=postgres PGUSER="${POSTGRES_USER:-jarvis}" PGDATABASE="${POSTGRES_DB:-jarvis}"
PGPASSWORD="$(cat /run/jarvis/postgres_password)"
export PGPASSWORD
op_password="$(cat /run/jarvis/openproject_db_password)"

until pg_isready -q; do sleep 2; done

psql -v ON_ERROR_STOP=1 -v op_password="$op_password" <<'SQL'
SELECT format('CREATE ROLE openproject LOGIN PASSWORD %L', :'op_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'openproject') \gexec
ALTER ROLE openproject WITH LOGIN PASSWORD :'op_password';
SELECT 'CREATE DATABASE openproject OWNER openproject ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'openproject') \gexec
SQL
echo "base de datos openproject lista"
