# Task Checklist — KoridorTJ

No dates attached — work through phases in order when you have time. Each phase produces something runnable, so the project is demoable even if you stop partway through.

---

## Phase 0 — Repo & environment setup
- [x] Create GitHub repo, add `.gitignore` (Python, Docker, dbt, IDE), `LICENSE` (MIT recommended)
- [x] Set up `.env.example` with all required env vars (never commit real `.env`)
- [x] Scaffold folder structure (see `IMPLEMENTATION_PLAN.md` §4)
- [x] Write a minimal `README.md` stub (finish it properly in Phase 9)
- [x] Confirm Antigravity IDE + Docker + Docker Compose work locally

## Phase 1 — Real reference data: GTFS ingestion
- [x] Write a Python script to download the current Transjakarta GTFS zip
- [x] Parse `routes.txt`, `stops.txt`, `trips.txt`, `calendar.txt` into raw Postgres tables
- [x] Handle: feed unreachable, zip malformed, schema changed since last run
- [x] Add basic logging (structured, not just `print`)
- [x] Manually verify row counts look sane against the feed's published route count

## Phase 2 — Historical fact data: transaction dataset
- [x] Download the public simulated tap-in/tap-out dataset
- [x] Write a loader that lands it into a raw Postgres table as-is (no transformation yet)
- [x] Document its provenance and synthetic nature in `/docs/data_sources.md`

## Phase 3 — Warehouse modeling with dbt
- [ ] Initialize dbt project, connect to Postgres
- [ ] Build staging models (`stg_routes`, `stg_stops`, `stg_trips`, `stg_taps`, ...)
- [ ] Build dimension models: `dim_routes`, `dim_stops`, `dim_corridors`, `dim_calendar`
- [ ] Build fact model: `fact_taps`
- [ ] Add column-level descriptions in `schema.yml` for every model

## Phase 4 — Orchestration with Airflow
- [ ] Stand up Airflow (LocalExecutor) via Docker Compose
- [ ] DAG 1: `gtfs_ingest` — weekly, runs Phase 1 script
- [ ] DAG 2: `warehouse_build` — nightly, runs `dbt run` then `dbt test`
- [ ] Wire failure alerting (even just Airflow's own email/Slack-less failure UI is fine for a portfolio)
- [ ] Confirm DAGs are idempotent (safe to re-run without duplicating data)

## Phase 5 — Streaming: replay pipeline
- [ ] Stand up Kafka (KRaft mode, no ZooKeeper) via Docker Compose
- [ ] Write the replay producer (reads historical taps, republishes with "now" timestamps at a configurable speed multiplier)
- [ ] Write the consumer service (validates each event with Pydantic, lands good events in Postgres, bad events to a dead-letter topic)
- [ ] Add a small incremental dbt model that picks up newly-landed streaming taps
- [ ] Load test: run the producer for an hour, confirm no consumer lag/crash

## Phase 6 — Data quality & governance
- [ ] Add dbt schema tests: `not_null`, `unique`, `relationships`, `accepted_values` on key columns
- [ ] Add at least 3 custom singular dbt tests (e.g., no future timestamps, tap-out after tap-in, valid stop references)
- [ ] Generate `dbt docs` and confirm the lineage graph renders correctly
- [ ] Write `/docs/data_dictionary.md` and `/docs/erd.md` (Mermaid ERD)

## Phase 7 — BI / dashboard
- [ ] Stand up Apache Superset via Docker Compose, connect to the warehouse (read-only DB role)
- [ ] Build 3–5 dashboards (ridership by corridor/hour, weekday vs weekend, busiest stops, network map if feasible)
- [ ] Enable the `EMBEDDED_SUPERSET` feature flag and build a minimal guest-token service (Python or Go) to issue short-lived tokens for anonymous embed visitors
- [ ] Build a small public HTML page that embeds the dashboard via the guest-token service
- [ ] Add the "simulated data" disclaimer directly on the dashboard/embed page, not just in the README

## Phase 8 — Containerization & deployment
- [ ] Consolidate all services into one `docker-compose.yml` (Kafka, Airflow, Superset, guest-token service, producer, consumer)
- [ ] In Coolify: create a Docker Compose resource pointed at the repo, plus a managed Postgres database resource (`warehouse` + `airflow_meta` databases)
- [ ] Assign subdomains to public-facing services only (embed page, dbt docs) in Coolify; leave Airflow/Superset admin unexposed
- [ ] Deploy manually once via the Coolify UI to confirm everything works end-to-end
- [ ] Document VPS resource usage (RAM/CPU) — right-size the compose file if the VPS is small

## Phase 9 — CI/CD
- [ ] GitHub Actions: lint job (ruff/black for Python, sqlfluff for SQL)
- [ ] GitHub Actions: test job (pytest for ingestion/validation code, `dbt test` against an ephemeral Postgres service container)
- [ ] GitHub Actions: build job (build & push Docker images to GHCR)
- [ ] GitHub Actions: deploy job (call Coolify's API / `coolify-deploy-action` with `COOLIFY_API_TOKEN` to trigger a redeploy, gated behind the CI jobs passing)
- [ ] Add a status badge to the README

## Phase 10 — Documentation & polish
- [ ] Finish `README.md`: architecture diagram, quick start, links to dbt docs + public dashboard
- [ ] Record a short screen-capture GIF/video of the dashboard and DAGs for the README
- [ ] Proofread all docs for the "simulated data" disclaimer consistency
- [ ] Tag a `v1.0` release on GitHub

---

## Stretch goals (optional, do only if you want extra depth or extra keyword coverage)
- [ ] Extend the guest-token service into a small Go-based "network health" API (pipeline status, last successful DAG run) for extra Golang depth
- [ ] Mirror the warehouse into BigQuery free tier to explicitly demonstrate a managed cloud warehouse
- [ ] Add Great Expectations as a second, independent validation layer on the raw landing zone
- [ ] Add dbt snapshots (SCD2) to track how GTFS routes/stops change over time between feed pulls
- [ ] Add Terraform to provision the VPS/DNS instead of doing it by hand
- [ ] Add a simple public static page (e.g., Evidence.dev or a GitHub Pages site) summarizing key insights for non-technical visitors
