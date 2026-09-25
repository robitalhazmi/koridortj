# Deployment & Operations Guide — KoridorTJ

This guide documents the containerization architecture, production deployment procedures via **Coolify**, domain routing, security hardening, and resource budgets for the KoridorTJ platform.

---

## 1. System Architecture & Resource Sizing

All services run as isolated, containerized services managed by Docker Compose with strict memory and CPU limits.

### Resource Allocation Budget (Target: 4GB–8GB VPS)

| Service Name | Container Name | Memory Limit | CPU Limit | Exposure | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL 16** | `koridortj-postgres` | `512 MB` | `1.0` | Internal (`5432`) | Warehousing, Airflow metadata, Superset metadata |
| **Apache Kafka 3.7**| `koridortj-kafka` | `768 MB` | `1.0` | Internal (`9092`) | KRaft broker for real-time tap event streaming |
| **Airflow Scheduler**| `koridortj-airflow-scheduler` | `768 MB` | `1.0` | Internal | Scheduled DAG triggers & dbt execution |
| **Airflow Webserver**| `koridortj-airflow-webserver` | `512 MB` | `0.5` | Internal / Basic Auth (`8080`) | Pipeline monitoring UI |
| **Apache Superset** | `koridortj-superset` | `1024 MB` | `1.0` | Internal (`8088` backend) | BI visualizations & dashboard engine |
| **Token & Web API** | `koridortj-token-service` | `256 MB` | `0.5` | **Public HTTPS (`8000`)** | FastAPI gateway, guest token signer, web portal |
| **Replay Producer** | `koridortj-replay-producer` | `256 MB` | `0.5` | Internal | Continuous historical tap replay generator |
| **Stream Consumer** | `koridortj-tap-consumer` | `256 MB` | `0.5` | Internal | Pydantic validation & DLQ stream loader |
| **Total Overhead** | — | **~4.3 GB** | **~6.0 vCPUs (shared)** | — | Fits comfortably on a standard 8GB VPS (or 4GB VPS + swap) |

---

## 2. Coolify Deployment Blueprint

Coolify is an open-source, self-hosted PaaS alternative to Heroku/Vercel.

### Step 1: Create the Application Resource
1. Open your Coolify dashboard.
2. Select your Project & Environment (e.g. `Production`).
3. Click **+ New Resource** -> **Docker Compose**.
4. Select **Public GitHub Repository** and point to:
   ```text
   https://github.com/robitalhazmi/koridortj.git
   Branch: main
   Compose file: docker-compose.yml
   ```

### Step 2: Configure Production Environment Variables
In the Coolify resource **Environment Variables** tab, define production secrets:

```bash
# Database Secrets
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<STRONG_POSTGRES_PASSWORD>
POSTGRES_DB_WAREHOUSE=warehouse
POSTGRES_DB_AIRFLOW=airflow_meta
POSTGRES_DB_SUPERSET=superset_meta
POSTGRES_INGESTION_USER=ingestion_user
POSTGRES_INGESTION_PASSWORD=<STRONG_INGESTION_PASSWORD>
POSTGRES_READONLY_USER=superset_ro
POSTGRES_READONLY_PASSWORD=<STRONG_READONLY_PASSWORD>

# Airflow Security
AIRFLOW__CORE__FERNET_KEY=<GENERATED_FERNET_KEY>
AIRFLOW__WEBSERVER__SECRET_KEY=<GENERATED_SECRET_KEY>

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

### Step 3: Domain Routing & Traefik HTTPS Termination
Coolify automatically manages Traefik reverse proxy and Let's Encrypt certificates.

- **Public Web Portal & Token Service**:
  - Assign domain: `https://koridortj.yourdomain.com` -> routes to `token-service:8000`.
- **Public Embedded Superset Dashboard**:
  - Assign domain: `https://dashboard.yourdomain.com` -> routes to `superset:8088`.
- **Airflow Webserver (Private)**:
  - Leave unexposed or bind to internal VPN / Coolify basic auth on `https://airflow.yourdomain.com`.

---

## 3. Local Development Deployment

To spin up the complete platform locally:

```bash
# 1. Clone repository
git clone https://github.com/robitalhazmi/koridortj.git
cd koridortj

# 2. Configure environment
cp .env.example .env

# 3. Start core infrastructure
docker compose up -d postgres kafka

# 4. Initialize Airflow & Superset metadata
docker compose up -d airflow-init superset-init

# 5. Start webservers and services
docker compose up -d airflow-webserver airflow-scheduler superset token-service

# 6. (Optional) Start continuous streaming background workers
docker compose --profile streaming up -d
```

---

## 4. Operational Maintenance & Monitoring

### Resource Usage Monitoring
Check live CPU and memory utilization across all containers:
```bash
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

### Database Backup
Execute logical snapshot of the data warehouse:
```bash
docker compose exec -T postgres pg_dump -U postgres -d warehouse -Fc > backup_warehouse_$(date +%Y%m%d).dump
```

### Database Restore
```bash
docker compose exec -T postgres pg_restore -U postgres -d warehouse --clean < backup_warehouse_20260925.dump
```

### View Ingestion Logs
```bash
docker compose logs -f replay-producer tap-consumer
```
