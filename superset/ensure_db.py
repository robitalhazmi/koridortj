"""Database probe and auto-creation script for Superset metadata database."""

import os
import sys
import time

import psycopg2

host = os.getenv("POSTGRES_HOST", "postgres")
port = int(os.getenv("POSTGRES_PORT", "5432"))
user = os.getenv("POSTGRES_USER", "postgres")
password = os.getenv("POSTGRES_PASSWORD", "postgres_dev_password")
superset_db = os.getenv("POSTGRES_DB_SUPERSET", "superset_meta")

print(f"Checking PostgreSQL at {host}:{port} as user '{user}'...")
connected = False
last_err = None

for i in range(30):
    for default_db in ["postgres", "warehouse", superset_db]:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=default_db,
                connect_timeout=3,
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (superset_db,))
                exists = cur.fetchone()
                if not exists:
                    print(f"Database '{superset_db}' not found. Creating it now...")
                    cur.execute(f'CREATE DATABASE "{superset_db}";')
                    print(f"✅ Created database '{superset_db}'.")
                else:
                    print(f"✅ Database '{superset_db}' is ready.")
            conn.close()
            connected = True
            break
        except Exception as e:
            last_err = e
    if connected:
        break
    print(f"[{i + 1}/30] Waiting for PostgreSQL at {host}:{port}... ({last_err})")
    time.sleep(2)

if not connected:
    print(f"❌ Could not reach PostgreSQL at {host}:{port} after 60s. Last error: {last_err}")
    sys.exit(1)
