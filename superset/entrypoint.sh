#!/bin/bash
set -e

echo "============================================================"
echo " Starting KoridorTJ Superset Production Serving Node"
echo "============================================================"

echo "=== [1/4] Ensuring PostgreSQL Database Exists ==="
python /app/pythonpath/ensure_db.py

echo "=== [2/4] Running Superset Database Migrations ==="
superset db upgrade

echo "=== [3/4] Initializing Superset Security & Roles ==="
superset init

echo "=== [4/4] Configuring Admin & Guest Role Permissions ==="
python /app/pythonpath/init_public_role.py

echo "============================================================"
echo " ✅ Superset Provisioning Complete — Starting Web Server"
echo "============================================================"

exec /usr/bin/run-server.sh
