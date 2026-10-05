# Deployment & Operations Guide — KoridorTJ

This guide documents the two-environment split (Local Dev/Compute vs. VPS Serving Layer), production deployment procedures via **Coolify**, domain routing, security hardening, and resource budgets for the KoridorTJ platform.

---

## 1. System Architecture & Resource Sizing

The pipeline is split into two environments to respect hardware constraints on a 1 vCPU / 2GB VPS:

1. **Local Dev / Compute (`docker-compose.dev.yml`)**: Airflow, Kafka, local dev Postgres, dbt, and streaming replay workers.
2. **VPS Serving Layer (`docker-compose.prod.yml`)**: Production Postgres (Coolify-managed resource), lean Superset (1 worker, no Celery/Redis), and guest-token embed service.
3. **Promotion Bridge (`scripts/promote_to_prod.sh`)**: SSH-tunneled `pg_dump` / `pg_restore` and dbt docs sync.

### VPS Resource Allocation Budget (Target: 1 vCPU / 2GB RAM)

| Service Name | Type | Memory Limit | CPU Limit | Exposure | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Production PostgreSQL 16** | Coolify Database Resource | `384 MB` | `0.5` | Internal (`5432`) | Production warehouse (`warehouse`) & Superset metadata (`superset_meta`) |
| **Apache Superset** | Compose (`docker-compose.prod.yml`) | `600 MB` | `1.0` | Internal (`8088` backend) | Serves pre-computed dashboards |
| **Token & Web API** | Compose (`docker-compose.prod.yml`) | `128 MB` | `0.5` | **Public HTTPS (`8000`)** | FastAPI gateway, guest token signer, web portal |
| **Total VPS Overhead** | — | **~1.1 GB** | **~1.0 vCPU** | — | Fits comfortably within 2GB RAM without swap exhaustion |

---

## 2. Coolify Deployment Blueprint

Coolify is an open-source, self-hosted PaaS alternative to Heroku/Vercel.

### Step 1: Create the Production PostgreSQL Database Resource
1. Open your Coolify dashboard.
2. Select your Project & Environment (e.g. `Production`).
3. Click **+ New Resource** -> **PostgreSQL**.
4. Configure database settings:
   - **Database Name**: `warehouse`
   - **User**: `postgres`
   - **Password**: `<STRONG_PROD_POSTGRES_PASSWORD>`
   - **Set Public Port (Optional for SSH tunnel)**: Leave private / internal to Docker network or accessible via SSH tunnel.
5. Click **Start** to spin up the database.
6. Run [`scripts/init_prod_db.sql`](../scripts/init_prod_db.sql) once via database terminal / psql to create the `superset_meta` database, schemas (`warehouse`, `staging`), and the `superset_ro` user.

### Step 2: Create the Serving Layer Application Resource
1. In the same Coolify environment, click **+ New Resource** -> **Docker Compose**.
2. Select **Public GitHub Repository** and point to:
   ```text
   https://github.com/robitalhazmi/koridortj.git
   Branch: main
   Compose file: docker-compose.prod.yml
   ```
3. Connect the application to the same Docker network as the PostgreSQL database resource.

### Step 3: Configure Production Environment Variables in Coolify
In the application's **Environment Variables** tab in Coolify:

```bash
# Database Secrets (Point to Coolify-managed Postgres resource)
PROD_POSTGRES_HOST=<COOLIFY_POSTGRES_INTERNAL_HOSTNAME_OR_IP>
PROD_POSTGRES_PORT=5432
PROD_POSTGRES_USER=postgres
PROD_POSTGRES_PASSWORD=<STRONG_PROD_POSTGRES_PASSWORD>
PROD_POSTGRES_DB_WAREHOUSE=warehouse
POSTGRES_DB_SUPERSET=superset_meta
PROD_POSTGRES_READONLY_USER=superset_ro
PROD_POSTGRES_READONLY_PASSWORD=<STRONG_READONLY_PASSWORD>

# Superset & JWT Security
SUPERSET_SECRET_KEY=<STRONG_SUPERSET_SECRET_KEY>
SUPERSET_GUEST_TOKEN_JWT_SECRET=<STRONG_JWT_SECRET>
SUPERSET_ADMIN_USERNAME=admin
SUPERSET_ADMIN_PASSWORD=<STRONG_ADMIN_PASSWORD>
SUPERSET_ADMIN_EMAIL=admin@koridortj.id

# Public URL Routing
SUPERSET_DOMAIN=https://dashboard.yourdomain.com
SUPERSET_DASHBOARD_ID=45d44fda-4e9c-4a88-894d-819f66fbfd33
```

### Step 4: Domain Routing & Traefik HTTPS Termination
- **Public Web Portal & Token Service**:
  - Assign domain: `https://koridortj.yourdomain.com` -> routes to `token-service:8000`.
- **Public Embedded Superset Dashboard**:
  - Assign domain: `https://dashboard.yourdomain.com` -> routes to `superset:8088`.
- **dbt Docs Static Catalog**:
  - Assign domain: `https://dbtdocs.yourdomain.com` -> routes to static file server or docs container.

---

## 3. Local Development & Promotion Workflow

```bash
# 1. Start local dev/compute stack
docker compose -f docker-compose.dev.yml up -d

# 2. Trigger pipeline run
docker compose -f docker-compose.dev.yml exec airflow-webserver airflow dags trigger gtfs_ingest
docker compose -f docker-compose.dev.yml exec airflow-webserver airflow dags trigger warehouse_build

# 3. Once test gate is verified green, promote finalized models to production:
./scripts/promote_to_prod.sh
```

---

## 4. Data Provenance & Governance Notice

- **Reference Transit Network**: Ingested directly from official PT Transportasi Jakarta open GTFS feeds (CC BY 4.0).
- **Passenger Tap Fact Data**: Synthetic / simulated transactions generated for portfolio analytics demonstration (`is_simulated = TRUE`).
- **Production Compliance**: All production endpoints, dashboards, and embedded web portal views enforce and display the simulated data disclaimer.

