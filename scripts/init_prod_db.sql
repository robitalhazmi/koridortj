-- ==============================================================================
-- KoridorTJ — Production PostgreSQL Initialization Script (Coolify Managed DB)
-- ==============================================================================
-- Run this script once on your production PostgreSQL instance in Coolify.
-- It configures the secondary superset_meta database, core analytical schemas,
-- and the read-only 'superset_ro' role used by Apache Superset & Token Service.
-- ==============================================================================

-- 1. Create Superset metadata database
SELECT 'CREATE DATABASE superset_meta'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'superset_meta')\gexec

-- 2. Switch to the warehouse database
\c warehouse

-- 3. Create analytical star schema namespaces
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE SCHEMA IF NOT EXISTS staging;

-- 4. Create dedicated read-only role for Superset and Token Service
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'superset_ro') THEN
      CREATE ROLE superset_ro WITH LOGIN PASSWORD 'superset_ro_prod_password';
   END IF;
END
$do$;

-- 5. Grant read-only privileges to superset_ro
GRANT CONNECT ON DATABASE warehouse TO superset_ro;
GRANT USAGE ON SCHEMA warehouse TO superset_ro;
GRANT USAGE ON SCHEMA staging TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA staging TO superset_ro;

ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse GRANT SELECT ON TABLES TO superset_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT SELECT ON TABLES TO superset_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA warehouse GRANT SELECT ON TABLES TO superset_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA staging GRANT SELECT ON TABLES TO superset_ro;
