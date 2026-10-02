#!/usr/bin/env bash
# ==============================================================================
# Helper Script to Sync/Reset PostgreSQL Passwords on VPS
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load .env if present
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    # shellcheck disable=SC1091
    source "${PROJECT_ROOT}/.env"
fi

PROD_SSH_HOST="${PROD_SSH_HOST:-${1:-}}"
PROD_SSH_USER="${PROD_SSH_USER:-${2:-root}}"
PROD_SSH_PORT="${PROD_SSH_PORT:-22}"
PROD_SSH_KEY="${PROD_SSH_KEY_PATH:-~/.ssh/id_rsa}"

POSTGRES_PASS="${PROD_POSTGRES_PASSWORD:-}"
SUPERSET_RO_PASS="${PROD_POSTGRES_READONLY_PASSWORD:-}"

if [[ -z "${PROD_SSH_HOST}" ]]; then
    read -rp "Enter VPS Host IP/Domain: " PROD_SSH_HOST
fi

if [[ -z "${POSTGRES_PASS}" ]]; then
    read -rsp "Enter Production PostgreSQL (postgres) Password: " POSTGRES_PASS
    echo ""
fi

if [[ -z "${SUPERSET_RO_PASS}" ]]; then
    read -rsp "Enter Production Superset Read-Only (superset_ro) Password: " SUPERSET_RO_PASS
    echo ""
fi

echo "======================================================================"
echo " Connecting to VPS ${PROD_SSH_USER}@${PROD_SSH_HOST}:${PROD_SSH_PORT} to sync Postgres passwords..."
echo "======================================================================"

SSH_OPTS=()
if [[ -f "${PROD_SSH_KEY}" ]]; then
    SSH_OPTS+=("-i" "${PROD_SSH_KEY}")
fi

ssh "${SSH_OPTS[@]}" -p "${PROD_SSH_PORT}" "${PROD_SSH_USER}@${PROD_SSH_HOST}" bash -s <<EOF
set -e
PG_CONTAINER=\$(docker ps --format '{{.Names}} {{.Image}}' | grep -iE 'postgres' | awk '{print \$1}' | head -n 1)

if [ -z "\${PG_CONTAINER}" ]; then
    echo "❌ Error: Could not find running PostgreSQL container on VPS."
    docker ps
    exit 1
fi

echo "✅ Found PostgreSQL container: \${PG_CONTAINER}"
echo "Updating 'postgres' user password..."
docker exec -i "\${PG_CONTAINER}" psql -U postgres -c "ALTER USER postgres WITH PASSWORD '${POSTGRES_PASS}';"

echo "Ensuring 'superset_meta' database exists..."
docker exec -i "\${PG_CONTAINER}" psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'superset_meta'" | grep -q 1 || \
docker exec -i "\${PG_CONTAINER}" psql -U postgres -c "CREATE DATABASE superset_meta;"

echo "Ensuring 'superset_ro' user exists and has correct permissions..."
docker exec -i "\${PG_CONTAINER}" psql -U postgres -c "
DO \\\$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'superset_ro') THEN
        CREATE USER superset_ro WITH PASSWORD '${SUPERSET_RO_PASS}';
    ELSE
        ALTER USER superset_ro WITH PASSWORD '${SUPERSET_RO_PASS}';
    END IF;
END
\\\$\$;
"

echo "Granting permissions on database 'warehouse'..."
docker exec -i "\${PG_CONTAINER}" psql -U postgres -d warehouse -c "
GRANT CONNECT ON DATABASE warehouse TO superset_ro;
CREATE SCHEMA IF NOT EXISTS warehouse;
GRANT USAGE ON SCHEMA warehouse TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO superset_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse GRANT SELECT ON TABLES TO superset_ro;
"

echo "======================================================================"
echo " ✅ PostgreSQL passwords and permissions successfully updated on VPS!"
echo "======================================================================"
EOF
