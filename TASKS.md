# Task Checklist — KoridorTJ

No dates attached — work through phases in order when you have time. Each phase produces something runnable. Phases 0–6 happen entirely on your **laptop**; Phase 7 deploys to the **VPS**; Phase 8 wires the two together.

---

## Phase 0 — Repo & environment setup
- [x] Create GitHub repo, add `.gitignore` (Python, Docker, dbt, IDE), `LICENSE` (MIT recommended)
- [x] Set up `.env.example` with all required env vars for local dev (never commit real `.env`)
- [x] Scaffold folder structure (see `IMPLEMENTATION_PLAN.md` §5)
- [x] Write a minimal `README.md` stub (finish properly in Phase 9)
- [x] Confirm Antigravity IDE + Docker + Docker Compose work locally

## Phase 1 — Real reference data: GTFS ingestion (local)
- [x] Write a Python script to download the current Transjakarta GTFS zip
- [x] Parse `routes.txt`, `stops.txt`, `trips.txt`, `calendar.txt` into raw tables in the **local dev Postgres**
- [x] Handle: feed unreachable, zip malformed, schema changed since last run
- [x] Add structured logging
- [x] Manually verify row counts look sane against the feed's published route count

## Phase 2 — Historical fact data: transaction dataset (local)
- [x] Download the public simulated tap-in/tap-out dataset
- [x] Write a loader that lands it into a raw table in the local dev Postgres, as-is
- [x] Document its provenance and synthetic nature in `/docs/data_sources.md`

## Phase 3 — Warehouse modeling with dbt (local)
- [x] Initialize dbt project, connect to the local dev Postgres
- [x] Build staging models (`stg_routes`, `stg_stops`, `stg_trips`, `stg_taps`, ...)
- [x] Build dimension models: `dim_routes`, `dim_stops`, `dim_corridors`, `dim_calendar`
- [x] Build fact model: `fact_taps`
- [x] Add column-level descriptions in `schema.yml` for every model

## Phase 4 — Orchestration with Airflow (local only)
- [x] Stand up Airflow (LocalExecutor) via `docker-compose.dev.yml`
- [x] DAG 1: `gtfs_ingest` — weekly, runs Phase 1 script
- [x] DAG 2: `warehouse_build` — nightly/on-demand, runs `dbt run` then `dbt test`
- [x] Confirm both DAGs write only to the local dev Postgres — never to production
- [x] Confirm DAGs are idempotent (safe to re-run without duplicating data)

## Phase 5 — Streaming: replay pipeline (local only)
- [x] Stand up Kafka (KRaft mode) via `docker-compose.dev.yml`
- [x] Write the replay producer (reads historical taps, republishes with "now" timestamps at a configurable speed multiplier)
- [x] Write the consumer service (validates each event with Pydantic, lands good events in the dev Postgres, bad events to a dead-letter topic)
- [x] Add a small incremental dbt model that picks up newly-landed streaming taps
- [x] Load test: run the producer for an hour, confirm no consumer lag/crash

## Phase 6 — Data quality & governance (local)
- [x] Add dbt schema tests: `not_null`, `unique`, `relationships`, `accepted_values` on key columns
- [x] Add at least 3 custom singular dbt tests (no future timestamps, tap-out after tap-in, valid stop references)
- [x] Generate `dbt docs` locally and confirm the lineage graph renders correctly
- [x] Write `/docs/data_dictionary.md` and `/docs/erd.md` (Mermaid ERD)

## Phase 7 — BI / dashboard (VPS)
- [x] In Coolify, create a **production Postgres** database resource
- [x] Stand up Superset via `docker-compose.prod.yml` (single worker, no Celery/Redis), connect to the **production** Postgres via a read-only role
- [x] Build 3–5 dashboards (ridership by corridor/hour, weekday vs weekend, busiest stops, network map if feasible)
- [x] Enable the `EMBEDDED_SUPERSET` feature flag and build the guest-token service (Python or Go)
- [x] Build a small public HTML page that embeds the dashboard via the guest-token service
- [x] Add the "simulated data" disclaimer directly on the dashboard/embed page

## Phase 8 — Dev → prod promotion pipeline
- [x] Write `scripts/promote_to_prod.sh`: re-run `dbt test` as a final gate, `pg_dump` the finished warehouse tables, SSH-tunnel to the VPS, `pg_restore` into production
- [x] Add a step to regenerate `dbt docs` and publish the static output to wherever the VPS serves it
- [ ] Test the failure path: intentionally break a dbt test and confirm the script refuses to promote
- [x] Document the promotion cadence in the README (manual, whenever you want the public demo refreshed)

## Phase 9 — CI/CD
- [x] GitHub Actions: lint job (ruff/black for Python, sqlfluff for SQL)
- [x] GitHub Actions: test job (pytest for ingestion/validation code, `dbt test` against an ephemeral Postgres service container)
- [x] GitHub Actions: build job (build & push Docker images for the serving-layer services to GHCR)
- [x] GitHub Actions: deploy job (call Coolify's API/`coolify-deploy-action` with `COOLIFY_API_TOKEN` to redeploy `docker-compose.prod.yml`, gated behind CI passing) — this deploys code, not data
- [x] Add a status badge to the README

## Phase 10 — Documentation & polish
- [x] Finish `README.md`: architecture diagram, quick start (both compose files + promotion script), links to dbt docs + public dashboard
- [ ] Record a short screen-capture GIF/video of the dashboard and DAGs for the README
- [x] Proofread all docs for the "simulated data" disclaimer consistency
- [ ] Tag a `v1.0` release on GitHub

---

## Stretch goals (optional)
- [ ] Extend the guest-token service into a small Go-based "network health" API (pipeline status, last successful local DAG run, consumer lag)
- [ ] Mirror the local dev warehouse into BigQuery free tier, to explicitly demonstrate a managed cloud warehouse
- [ ] Add Great Expectations as a second, independent validation layer on the raw landing zone (local)
- [ ] Add dbt snapshots (SCD2) to track GTFS route/stop changes across feed pulls
- [ ] Add Terraform to provision the VPS/DNS instead of doing it by hand
- [ ] Run a self-hosted GitHub Actions runner on your laptop so the promotion script can be triggered from a `workflow_dispatch` button instead of run by hand — the data never has to leave your machine except during the promotion itself
- [ ] A simple public static insights page (e.g. Evidence.dev or GitHub Pages) for non-technical visitors
