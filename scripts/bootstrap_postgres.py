"""
PostgreSQL Bootstrap Script.
Idempotently creates required databases (airflow_meta, superset_meta, warehouse),
roles (ingestion_user, superset_ro), schemas, and stream tables.
"""

import os
import sys
import time

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def get_connection(dbname: str = "postgres", max_retries: int = 15, delay: int = 2):
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres_dev_password")

    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname,
                connect_timeout=5,
            )
            return conn
        except Exception as e:
            print(
                f"[Attempt {attempt}/{max_retries}] Waiting for PostgreSQL at {host}:{port}/{dbname} ({e})..."
            )
            time.sleep(delay)

    print(
        f"Error: Unable to connect to PostgreSQL at {host}:{port}/{dbname} after {max_retries} attempts."
    )
    sys.exit(1)


def bootstrap_databases():
    print("=== Step 1: Checking and Creating Databases ===")
    conn = get_connection(dbname="postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    required_dbs = [
        os.environ.get("POSTGRES_DB_AIRFLOW", "airflow_meta"),
        os.environ.get("POSTGRES_DB_SUPERSET", "superset_meta"),
        os.environ.get("POSTGRES_DB_WAREHOUSE", "warehouse"),
    ]

    for db in required_dbs:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
        if cur.fetchone():
            print(f" - Database '{db}' already exists.")
        else:
            print(f" + Creating database '{db}'...")
            cur.execute(f'CREATE DATABASE "{db}"')

    cur.close()
    conn.close()


def bootstrap_warehouse_objects():
    print("=== Step 2: Initializing Warehouse Schemas, Roles & Tables ===")
    warehouse_db = os.environ.get("POSTGRES_DB_WAREHOUSE", "warehouse")
    ingestion_user = os.environ.get("POSTGRES_INGESTION_USER", "ingestion_user")
    ingestion_pass = os.environ.get("POSTGRES_INGESTION_PASSWORD", "ingestion_dev_password")
    readonly_user = os.environ.get("POSTGRES_READONLY_USER", "superset_ro")
    readonly_pass = os.environ.get("POSTGRES_READONLY_PASSWORD", "superset_ro_dev_password")

    conn = get_connection(dbname=warehouse_db)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    # Schemas
    for schema in ["raw", "staging", "warehouse"]:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
    print(" - Schemas verified: raw, staging, warehouse")

    # Ingestion Role
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ingestion_user,))
    if not cur.fetchone():
        print(f" + Creating role '{ingestion_user}'...")
        cur.execute(f"CREATE ROLE {ingestion_user} WITH LOGIN PASSWORD '{ingestion_pass}';")
    else:
        print(f" - Role '{ingestion_user}' exists.")

    cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{warehouse_db}" TO {ingestion_user};')
    cur.execute(f"GRANT ALL ON SCHEMA raw, staging, warehouse TO {ingestion_user};")
    cur.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA raw, staging, warehouse GRANT ALL ON TABLES TO {ingestion_user};"
    )

    # Readonly Role
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (readonly_user,))
    if not cur.fetchone():
        print(f" + Creating role '{readonly_user}'...")
        cur.execute(f"CREATE ROLE {readonly_user} WITH LOGIN PASSWORD '{readonly_pass}';")
    else:
        print(f" - Role '{readonly_user}' exists.")

    cur.execute(f'GRANT CONNECT ON DATABASE "{warehouse_db}" TO {readonly_user};')
    cur.execute(f"GRANT USAGE ON SCHEMA staging, warehouse TO {readonly_user};")
    cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA staging, warehouse TO {readonly_user};")
    cur.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA staging, warehouse GRANT SELECT ON TABLES TO {readonly_user};"
    )
    cur.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {ingestion_user} IN SCHEMA staging, warehouse GRANT SELECT ON TABLES TO {readonly_user};"
    )

    # Stream table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS raw.taps_stream (
        trans_id VARCHAR(100) PRIMARY KEY,
        pay_card_id VARCHAR(100) NOT NULL,
        pay_card_bank VARCHAR(100),
        pay_card_name VARCHAR(255),
        pay_card_sex VARCHAR(10),
        pay_card_birth_date INT,
        corridor_id VARCHAR(100),
        corridor_name VARCHAR(255),
        direction INT DEFAULT 0,
        tap_in_stops VARCHAR(100),
        tap_in_stops_name VARCHAR(255),
        tap_in_stops_lat DOUBLE PRECISION,
        tap_in_stops_lon DOUBLE PRECISION,
        stop_start_seq INT,
        tap_in_time TIMESTAMP,
        tap_out_stops VARCHAR(100),
        tap_out_stops_name VARCHAR(255),
        tap_out_stops_lat DOUBLE PRECISION,
        tap_out_stops_lon DOUBLE PRECISION,
        stop_end_seq INT,
        tap_out_time TIMESTAMP,
        pay_amount NUMERIC(10, 2) DEFAULT 3500.00,
        is_simulated BOOLEAN NOT NULL DEFAULT TRUE,
        _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        _source_topic VARCHAR(100) DEFAULT 'taps.raw'
    );
    CREATE INDEX IF NOT EXISTS idx_raw_taps_stream_card ON raw.taps_stream (pay_card_id);
    CREATE INDEX IF NOT EXISTS idx_raw_taps_stream_corridor ON raw.taps_stream (corridor_id);
    CREATE INDEX IF NOT EXISTS idx_raw_taps_stream_tap_in_time ON raw.taps_stream (tap_in_time);
    """)
    print(" - Stream table 'raw.taps_stream' and indexes verified.")

    cur.close()
    conn.close()
    print("=== PostgreSQL Bootstrap Completed Successfully ===")


if __name__ == "__main__":
    bootstrap_databases()
    bootstrap_warehouse_objects()
