-- Initialization script for PostgreSQL databases and users
-- Automatically executed on container startup by docker-entrypoint-initdb.d

-- Create airflow_meta database for Airflow state storage
SELECT 'CREATE DATABASE airflow_meta'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow_meta')\gexec

-- Connect to default/warehouse database
\c warehouse

-- Create core schemas
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS warehouse;

-- Create dedicated ingestion user if not exists
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'ingestion_user') THEN
      CREATE ROLE ingestion_user WITH LOGIN PASSWORD 'ingestion_dev_password';
   END IF;
END
$do$;

-- Grant privileges to ingestion user
GRANT ALL PRIVILEGES ON DATABASE warehouse TO ingestion_user;
GRANT ALL ON SCHEMA raw TO ingestion_user;
GRANT ALL ON SCHEMA staging TO ingestion_user;
GRANT ALL ON SCHEMA warehouse TO ingestion_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT ALL ON TABLES TO ingestion_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT ALL ON TABLES TO ingestion_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse GRANT ALL ON TABLES TO ingestion_user;

-- Create read-only role for Superset if not exists
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'superset_ro') THEN
      CREATE ROLE superset_ro WITH LOGIN PASSWORD 'superset_ro_dev_password';
   END IF;
END
$do$;

-- Grant read-only access to superset_ro
GRANT CONNECT ON DATABASE warehouse TO superset_ro;
GRANT USAGE ON SCHEMA warehouse TO superset_ro;
GRANT USAGE ON SCHEMA staging TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA staging TO superset_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse GRANT SELECT ON TABLES TO superset_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT SELECT ON TABLES TO superset_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE ingestion_user IN SCHEMA warehouse GRANT SELECT ON TABLES TO superset_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE ingestion_user IN SCHEMA staging GRANT SELECT ON TABLES TO superset_ro;

-- Create streaming raw table for real-time tap ingestion
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

