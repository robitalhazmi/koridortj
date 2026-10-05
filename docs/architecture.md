# Architecture & System Design — KoridorTJ

KoridorTJ is designed as an end-to-end modern data engineering and business intelligence platform built on Jakarta's TransJakarta Bus Rapid Transit (BRT) network.

This document details the architectural principles, component topology, two-environment split, data flow lifecycles, and governance boundaries implemented across the platform.

---

## 1. Architectural Philosophy & Two-Environment Split

Production transit data pipelines require substantial compute resources for ingestion, event streaming, data quality validation, and ELT transformations. However, serving pre-computed dimensional models and dashboards to external stakeholders requires minimal, stable compute.

To optimize operational cost and respect hardware constraints on a 1 vCPU / 2GB RAM Virtual Private Server (VPS), KoridorTJ implements a **strict separation of concerns between Compute and Serving**:

```mermaid
flowchart TD
    subgraph DevEnv ["💻 Environment 1: Local Dev / Compute Stack (docker-compose.dev.yml)"]
        subgraph IngestionLayer ["1. Ingestion & Streaming Layer"]
            GTFS["Official TransJakarta GTFS Feed<br/>(routes, stops, trips, calendar)"]
            TapsBatch["Simulated Tap Dataset<br/>(37,900 Historical Trips)"]
            Producer["Replay Producer<br/>(Kafka KRaft: taps.raw)"]
            Consumer["Validation Consumer<br/>(Pydantic Checks)"]
            DLQ["Dead-Letter Topic<br/>(taps.deadletter)"]
        end

        subgraph OrchestrationLayer ["2. Workflow Orchestration (Apache Airflow)"]
            DAG1["DAG: gtfs_ingest<br/>(Weekly Reference Sync)"]
            DAG2["DAG: warehouse_build<br/>(Nightly dbt Run & Test)"]
        end

        subgraph DevWarehouse ["3. Local Dev Warehouse (PostgreSQL 16 & dbt Core)"]
            RawSchema["raw Schema<br/>• gtfs_routes, gtfs_stops<br/>• gtfs_trips, gtfs_calendar<br/>• taps, taps_stream"]
            StagingSchema["staging Schema<br/>• stg_routes, stg_stops<br/>• stg_trips, stg_calendar<br/>• stg_taps, stg_streaming_taps"]
            StarSchema["warehouse Star Schema<br/>• dim_routes, dim_stops<br/>• dim_corridors, dim_calendar<br/>• fact_taps"]
        end

        GTFS --> DAG1 --> RawSchema
        TapsBatch --> RawSchema
        TapsBatch --> Producer --> Consumer --> RawSchema
        Consumer -.->|Invalid Records| DLQ
        DAG2 --> StagingSchema --> StarSchema
    end

    subgraph PromotionBridge ["🚀 Promotion Bridge (scripts/promote_to_prod.sh)"]
        Gate["Pre-Promotion Quality Gate<br/>(80 dbt Tests Passing)"]
        Dump["pg_dump Conformed Models<br/>(--schema=warehouse)"]
        Tunnel["SSH Tunneled Restore<br/>(psql -v ON_ERROR_STOP=1)"]
        DocsGen["Static dbt Docs Sync<br/>(index.html, manifest, catalog)"]

        Gate --> Dump --> Tunnel
        Gate --> DocsGen
    end

    subgraph ProdEnv ["☁️ Environment 2: VPS Serving Layer (docker-compose.prod.yml)"]
        ProdDB["Production PostgreSQL 16<br/>(Coolify Managed Resource)<br/>• Schema: warehouse<br/>• Schema: superset_meta"]
        Superset["Apache Superset 4.0.1<br/>(Lean 1-Worker Node, superset_ro)"]
        TokenAPI["FastAPI Token Service<br/>(JWT HS256 Minting & Stats API)"]
        WebPortal["Public Web Portal<br/>• Live Analytics & KPIs<br/>• Embedded Superset Dashboard<br/>• Static dbt Docs (/dbt_docs/)"]

        ProdDB --> Superset
        ProdDB --> TokenAPI
        Superset -.->|Guest Token Embed| WebPortal
        TokenAPI -->|Guest JWT & Telemetry| WebPortal
    end

    StarSchema --> Gate
    Tunnel --> ProdDB
    DocsGen --> WebPortal
```

---

## 2. Environment Breakdown

### Environment 1: Local Dev / Compute Stack
- **Purpose**: Heavy batch processing, GTFS downloads, Kafka streaming simulation, Airflow scheduling, and dbt transformation runs.
- **Specification**: Executed locally via [`docker-compose.dev.yml`](../docker-compose.dev.yml).
- **Isolation Guarantee**: Dev workloads are completely isolated from production. No Airflow DAG or Kafka consumer connects to the VPS.
- **Container Footprint**:
  - `postgres-dev`: PostgreSQL 16 database hosting `raw`, `staging`, and `warehouse` schemas.
  - `kafka`: Apache Kafka 3.7 running in KRaft mode (no Zookeeper required).
  - `airflow-webserver` & `airflow-scheduler`: Apache Airflow 2.9 (LocalExecutor) orchestrating ETL tasks.
  - `producer` & `consumer`: Python workers replaying and validating streaming transit taps.

### Environment 2: VPS Serving Layer
- **Purpose**: Always-on, secure public serving of pre-computed analytical models, interactive Superset dashboards, and static dbt documentation.
- **Specification**: Hosted on a lightweight VPS (1 vCPU / 2GB RAM budget) orchestrated via **Coolify** and [`docker-compose.prod.yml`](../docker-compose.prod.yml).
- **Resource Constraints**:
  - PostgreSQL 16: Capped at `384 MB` RAM.
  - Superset (Lean Node): Single worker (`WEB_CONCURRENCY=1`), no Celery/Redis background queues, capped at `600 MB` RAM.
  - FastAPI Microservice: Capped at `128 MB` RAM.
  - Total VPS Memory Footprint: **~1.1 GB**, leaving plenty of headroom.

---

## 3. Data Pipelines & Flow Lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant GTFS as TransJakarta GTFS Feed
    participant Replay as Kafka Producer/Consumer
    participant DevPG as Local Dev PostgreSQL
    participant Airflow as Apache Airflow
    participant dbt as dbt Core
    participant Bridge as Promotion Script
    participant ProdPG as Production PostgreSQL
    participant Web as Web Portal & Superset

    Note over GTFS,DevPG: Phase 1 & 2: Landing Zone Ingestion
    Airflow->>GTFS: Trigger gtfs_ingest_dag (Weekly)
    GTFS-->>DevPG: Validate & Load raw.gtfs_* tables
    Replay->>DevPG: Stream & Validate raw.taps_stream records

    Note over DevPG,dbt: Phase 3 & 4: Warehouse ELT & Quality Testing
    Airflow->>dbt: Trigger warehouse_build_dag (Nightly)
    dbt->>DevPG: Build staging and dimensional models
    dbt->>DevPG: Execute 80 automated dbt data quality tests

    Note over Bridge,ProdPG: Phase 8: Gated Promotion Bridge
    Bridge->>dbt: Run pre-promotion quality gate (80 tests)
    Bridge->>DevPG: pg_dump conformed warehouse schema
    Bridge->>ProdPG: SSH Stream & pg_restore into production
    Bridge->>Web: Sync compiled dbt documentation

    Note over ProdPG,Web: Phase 7: Serving Layer & Embedded Analytics
    Web->>ProdPG: FastAPI queries real-time analytics KPIs
    Web->>ProdPG: Superset renders guest-embedded charts (superset_ro)
```

### Ingestion Details
1. **GTFS Ingestion (`ingestion/gtfs_ingest.py`)**:
   - Downloads the official TransJakarta GTFS archive (`file_gtfs.zip`).
   - Parses `routes.txt`, `stops.txt`, `trips.txt`, and `calendar.txt` using chunked pandas ingestion.
   - Enforces Pydantic schema validation (`ingestion/schemas.py`).
   - Stamps audit lineage fields (`_ingested_at`, `_source_url`) into `raw` schema tables.
2. **Streaming Tap Ingestion (`ingestion/replay_producer.py` & `ingestion/tap_consumer.py`)**:
   - Replays historical tap records with configurable time acceleration (e.g. 60x real-time).
   - Produces JSON payloads to Kafka topic `taps.raw`.
   - Consumer validates events with Pydantic; valid records are batched into `raw.taps_stream`, while malformed payloads land in `taps.deadletter`.

### Transformation & Star Schema Modeling (`dbt/`)
1. **Staging Layer (`staging` schema)**:
   - Sanitizes text, parses timestamps, extracts corridor identifiers from route short names, and computes trip duration intervals.
   - Unions batch transactions (`stg_taps`) and incremental streaming transactions (`stg_streaming_taps`).
2. **Warehouse Layer (`warehouse` schema)**:
   - Conforms core transit entities into an analytical star schema:
     - `dim_routes`: 270 routes with BRT classification and color badges.
     - `dim_stops`: 8,445 stops with WGS84 geographic coordinates and corridor associations.
     - `dim_corridors`: 270 corridor summary dimensions.
     - `dim_calendar`: Date dimension with weekday/weekend indicators and calendar quarters.
     - `fact_taps`: 72,300+ granular tap-in and tap-out fact records with surrogate keys (`tap_id`).

---

## 4. Promotion Bridge & Security Model

The promotion bridge (`scripts/promote_to_prod.sh`) is the sole mechanism for publishing validated data from the local compute environment to the public VPS:

1. **Strict Quality Gate**: Executes `dbt test --target dev`. If any single test fails, the promotion script aborts immediately with exit code 1.
2. **Schema-Isolated Dump**: Dumps only the conformed analytical models (`--schema=warehouse`), leaving staging and raw tables in dev.
3. **Encrypted Tunnel**: Streams the SQL dump through an authenticated SSH tunnel directly into `psql -v ON_ERROR_STOP=1` inside the production database container.
4. **Role-Based Least Privilege**:
   - `postgres` (Superuser): Used only during internal migrations and data restore.
   - `superset_ro` (Read-Only User): Granted strictly `SELECT` permissions on `warehouse.*` tables and `superset_meta`. Cannot perform `INSERT`, `UPDATE`, `DELETE`, or schema modifications.
   - `token-service`: Connects to `warehouse` with read-only credentials to aggregate real-time KPI metrics.
5. **Static dbt Docs Sync**: Generates and pushes compiled `manifest.json`, `catalog.json`, and `index.html` to `/app/web/dbt_docs/` on the VPS for public exploration.

---

## 5. CI / CD Lifecycle

```mermaid
flowchart LR
    subgraph GitHubActions ["GitHub Actions Workflows"]
        subgraph CI ["CI: ci.yml (Every PR & Push to main)"]
            Lint["Lint: Ruff & SQLFluff"]
            Test["Pytest & Schemas"]
            DbtEphemeral["dbt test (Ephemeral Postgres Service)"]
            Lint --> Test --> DbtEphemeral
        end

        subgraph CD ["CD: cd.yml (Gated behind CI on main)"]
            BuildGHCR["Build & Push Docker Images to GHCR"]
            CoolifyWebhook["Trigger Coolify Webhook Deploy"]
            BuildGHCR --> CoolifyWebhook
        end
    end

    CI --> CD
```

- **Continuous Integration (`.github/workflows/ci.yml`)**:
  - Validates Python code style and formatting via **Ruff**.
  - Validates SQL formatting and dbt Jinja templating via **SQLFluff**.
  - Executes unit and API test suites via **Pytest**.
  - Spins up an ephemeral PostgreSQL service container, runs `dbt seed`, `dbt run`, and verifies all **80 dbt data quality tests**.
- **Continuous Deployment (`.github/workflows/cd.yml`)**:
  - Builds optimized Docker container images for `token-service`.
  - Publishes multi-arch images to GitHub Container Registry (GHCR).
  - Triggers Coolify webhook API to redeploy the serving layer on the VPS.
  - **Data Safety Guarantee**: CD deploys application code only; data is never automatically pushed to production from Git.

---

## 6. Data Governance & Disclaimer Standard

To ensure ethical data practices and compliance:
- **Reference Data**: Official TransJakarta GTFS feed published under Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Fact Data**: Simulated tap-in/tap-out transaction records generated for portfolio demonstration purposes.
- **Compliance Enforcement**: Every analytical model and reporting query enforces `is_simulated = TRUE`, and public disclaimers are prominently displayed in `README.md`, the web portal banner, and API health responses.

