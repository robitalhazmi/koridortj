#!/bin/bash
set -e

echo "=== Initializing Superset Metadata DB ==="
superset db upgrade

echo "=== Creating Admin User ==="
superset fab create-admin \
  --username "${SUPERSET_ADMIN_USERNAME:-admin}" \
  --firstname Admin \
  --lastname User \
  --email "${SUPERSET_ADMIN_EMAIL:-admin@koridortj.id}" \
  --password "${SUPERSET_ADMIN_PASSWORD:-admin}" || true

echo "=== Initializing Roles and Default Permissions ==="
superset init

echo "=== Superset Initialization Complete ==="
