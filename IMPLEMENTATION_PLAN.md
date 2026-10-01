# Implementation Plan — KoridorTJ

## 1. Goals and non-goals

**Goals**
- Demonstrate every "must-have" in the Data Engineer JD with a real, runnable system.
- Cover the "plus" items (streaming, Golang, CI/CD, containerization, cloud, governance) without turning the core build into a sprawl.
- Right-size the design to the actual hardware available (a 1 vCPU / 2GB VPS) rather than assuming unlimited resources — and make that reasoning visible, since it's itself a demonstrable engineering judgment.
- Produce something genuinely inspectable by a non-technical visitor (public dashboard) and a technical one (dbt docs, ERD, GitHub repo, CI badge).
- Be honest about which data is real (Transjakarta network structure) vs. simulated (transaction volumes).

**Non-goals**
- Not a claim of real Transjakarta ridership statistics.
- Not aiming for production-grade high availability; aiming for a correct, well-documented system a reviewer can actually click through.

## 2. Environments: local dev/compute vs. VPS serving

This project deliberately runs in two places. The target VPS (1 vCPU / 2GB RAM) isn't big enough to run an orchestrator, a streaming broker, and a BI tool simultaneously and reliably — Airflow's own docs ask for 4GB RAM and 2 cores just for Airflow itself, and Coolify's own documented minimum (2 vCPU / 2GB) already consumes most of what the box has before anything else is deployed.

| Environment | Runs | Always-on? |
|---|---|---|
| **Local (your laptop)** | Airflow (webserver + scheduler), Kafka, replay producer/consumer, dbt, a local "dev" Postgres | No — only while you're actively working |
| **VPS, via Coolify** | A "production" Postgres (Coolify-managed), a trimmed Superset, the guest-token service, the dbt docs static site | Yes — this is the public-facing demo |

A **promotion script** (§14) is the only link between the two: after a local pipeline run passes its dbt tests, the script pushes the finalized warehouse tables and freshly-generated dbt docs to the VPS. The production Postgres is never written to by an untested run, and your laptop never needs to be reachable from the internet.

## 3. Tech stack, with rationale

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Strongest language; ecosystem fit for every layer below |
| Optional 2nd language | Go | Used for the guest-token service (§11) — a naturally-scoped place for the JD's Golang-plus line |
| Warehouse (dev) | PostgreSQL, local Docker container | Disposable, fast to reset while iterating |
| Warehouse (prod) | PostgreSQL, Coolify-managed resource on the VPS | Only ever holds promoted, test-passed data; automated backups via Coolify |
| Orchestration | Apache Airflow — **local only** | Named explicitly in the JD; too heavy for the VPS, so it runs on your laptop |
| Transformation | dbt-core, run locally against the dev warehouse | Gives tests, docs, and lineage "for free" |
| Streaming | Apache Kafka (KRaft mode) — **local only** | Named explicitly in the JD; runs alongside Airflow on your laptop |
| Data quality | dbt tests + Pydantic, run locally | dbt tests cover the warehouse layer; Pydantic covers the ingestion boundary |
| BI | Apache Superset — **VPS only**, reads the production warehouse | Public-facing; trimmed to skip Celery/Redis since it only serves pre-computed dashboards, never runs live/async queries |
| Containers | Docker + Docker Compose — `docker-compose.dev.yml` (local) and `docker-compose.prod.yml` (VPS) | Keeps the two environments explicit and independently runnable |
| CI/CD | GitHub Actions | CI (lint/test) on every push; CD redeploys only the serving-layer code — data promotion is a separate, manual step (§14) |
| Hosting | Your VPS, managed by Coolify, serving-layer only | Realistic for the hardware available |
| IDE | Antigravity IDE | Already your chosen local dev environment |

## 4. Data sources

| Source | What it provides | Nature |
|---|---|---|
| Transjakarta official GTFS feed (`ppid.transjakarta.co.id` → GTFS zip) | Routes, stops, trips, calendars/schedules | **Real**, official, updates periodically |
| Public Transjakarta tap-in/tap-out transaction dataset | Per-trip transaction-like records generated with Faker on top of real route/stop master data | **Simulated** — no real transaction data has been publicly released |

Re-verify both URLs/terms before Phase 1, since portal links can drift. Store the exact source URL and access date in `/docs/data_sources.md`.

**Labeling rule (apply everywhere):** any UI, dashboard, or doc showing tap/ridership numbers must say "simulated data" in the same view.

## 5. Repo structure

```
KoridorTJ/
├── docker-compose.dev.yml       # Airflow, Kafka, dev Postgres, producer, consumer
├── docker-compose.prod.yml      # Superset, guest-token service (Postgres is a Coolify-managed resource, not in this file)
├── .env.example
├── README.md
├── docs/
│   ├── architecture.md
│   ├── erd.md
│   ├── data_dictionary.md
│   └── data_sources.md
├── ingestion/
│   ├── gtfs_ingest.py
│   ├── tap_loader.py
│   ├── replay_producer.py
│   ├── tap_consumer.py
│   └── schemas.py            # Pydantic models
├── dags/
│   ├── gtfs_ingest_dag.py
│   └── warehouse_build_dag.py
├── dbt/
│   ├── dbt_project.yml
│   ├── models/
│   │   ├── staging/
│   │   └── warehouse/
│   └── tests/
├── superset/
│   └── (exported dashboard/dataset definitions, optional)
├── services/
│   └── guest_token_service/
├── scripts/
│   └── promote_to_prod.sh
└── .github/
    └── workflows/
        ├── ci.yml
        └── cd.yml
```

## 6. Data model (star schema)

- `dim_routes` — route_id, route_name, route_type, corridor_code
- `dim_stops` — stop_id, stop_name, latitude, longitude
- `dim_corridors` — corridor_code, corridor_name, direction
- `dim_calendar` — date, day_of_week, is_weekend, is_holiday
- `fact_taps` — tap_id, route_id (FK), stop_id (FK), date_id (FK), tap_type (in/out), tap_timestamp, is_simulated (always true — kept as a real column so a future real source could be UNIONed in later without relabeling everything by hand)

This schema is identical in the dev and production Postgres instances — production simply receives a copy of dev's finished tables via the promotion script, not a separate dbt run.

## 7. Streaming design (local only)

- **Topic:** `taps.raw`; **dead-letter topic:** `taps.deadletter`
- **Producer (`replay_producer.py`):** reads the historical tap dataset in timestamp order, rewrites timestamps relative to "now" at a configurable speed multiplier, publishes to `taps.raw`
- **Consumer (`tap_consumer.py`):** validates each message with Pydantic; valid → insert into the local dev Postgres; invalid → publish to `taps.deadletter` with the validation error attached
- **Why replay, not a live feed:** no confirmed public real-time Transjakarta feed was found; replay is the standard, transparent way to demonstrate streaming ingestion without fabricating a live source

## 8. Airflow DAGs (local only)

| DAG | Schedule | Tasks |
|---|---|---|
| `gtfs_ingest` | Weekly | download GTFS zip → validate structure → load into the local dev warehouse → log row-count deltas |
| `warehouse_build` | Nightly / on demand | `dbt run` → `dbt test` against the local dev warehouse → fail loudly on any test failure |

Both DAGs run entirely on your laptop and never write to production — that only happens through the promotion script (§14). Write them idempotently, and use Airflow connections/variables for the dev Postgres credentials.

## 9. dbt project layout

- `staging/`: 1:1 cleaned views over raw tables
- `warehouse/`: the star schema models in §6
- `schema.yml` per folder: column descriptions + tests (`not_null`, `unique`, `relationships`, `accepted_values`)
- At least 3 custom singular tests in `tests/`
- dbt only ever runs against the local **dev** target — there is no dbt "prod" target; production receives a copy of dev's finished tables via §14

## 10. Data quality & governance

- **Quality gate:** the `warehouse_build` DAG fails if `dbt test` fails, and the promotion script re-checks tests one more time before touching production
- **Metadata:** `dbt docs generate` (run locally) gives a browsable catalog with column descriptions and a lineage graph; the static output is published to the VPS during promotion
- **Manual docs:** `/docs/data_dictionary.md` and `/docs/erd.md` for reviewers who don't want to run dbt docs locally

## 11. BI / dashboard plan

- Apache Superset (on the VPS) connected to the **production** Postgres via a read-only role — Superset never talks to the local dev database
- Suggested dashboards: ridership by corridor & hour-of-day, weekday vs. weekend pattern, top boarding stops, simple network map if stop lat/long renders cleanly
- Superset dashboards are private by default — there's no one-click "make public" toggle. Enable the `EMBEDDED_SUPERSET` feature flag, build a small **guest-token service** (Python/FastAPI or Go) that mints short-lived guest JWTs, and embed the dashboard on a small public HTML page that calls that service
- Because Superset here only ever serves dashboards refreshed by the promotion script (never a live/changing source), Celery and Redis — needed mainly for async queries, alerts, and scheduled reports — can be skipped entirely; run Superset with a single synchronous Gunicorn worker, which matters on a 2GB box
- Keep the Superset admin console itself unexposed — only the embed page and the token service are public-facing

## 12. Containerization

- **`docker-compose.dev.yml`** (local, your laptop): Postgres (dev warehouse + Airflow metadata), Kafka (KRaft, single broker), Airflow webserver + scheduler, replay-producer, tap-consumer. Full resources available — no need to trim.
- **`docker-compose.prod.yml`** (VPS, via Coolify): Superset (single Gunicorn worker, no Celery/Redis), guest-token service. Postgres is a separate Coolify-managed database resource, not a service in this file. Set explicit `mem_limit`/`cpus` on both containers to stay well within the VPS's 2GB.

## 13. Deployment to the VPS (via Coolify) — serving layer only

1. In Coolify, create a **Postgres database** resource — this is the production warehouse
2. In Coolify, create a **Docker Compose** resource pointing at `docker-compose.prod.yml`, with env vars (including the production Postgres connection string) set in Coolify's UI, not in a repo `.env`
3. Assign subdomains: one for the public embed page / guest-token service, one for the dbt docs static site
4. Leave the Superset admin console unexposed
5. First deploy manually from the Coolify UI; confirm Superset connects to production and the embed page renders
6. From here, this environment barely changes day to day — new data arrives only via promotion (§14); new *code* changes redeploy via CD (§15)

## 14. Dev → prod promotion pipeline

The one deliberate manual step connecting your laptop to the public demo.

- **When:** whenever you want the public dashboard to reflect a new pipeline run — not on every DAG run, only when you're happy with the result
- **What `scripts/promote_to_prod.sh` does:**
  1. Runs `dbt test` one more time against the local dev warehouse as a final gate — refuses to promote if anything fails
  2. `pg_dump`s the finalized warehouse tables (the `dim_*`/`fact_*` models, not raw/staging) from the local dev Postgres
  3. Opens a short-lived SSH tunnel to the VPS and `pg_restore`s into the production database
  4. Runs `dbt docs generate` locally, then copies the generated static site to wherever `docker-compose.prod.yml`'s static-file server serves it from
- **Why an SSH tunnel, not an open port:** the production Postgres never needs to accept connections from the wider internet — only from you, only while promoting. Keeping it closed by default is meaningfully better security for very little extra effort.
- **Failure mode:** if the dbt-test gate fails, nothing is promoted and the public dashboard keeps showing the last good run.

## 15. CI/CD (GitHub Actions)

- **`ci.yml`** (on pull request): `ruff`/`black`, `sqlfluff`, `pytest`, and `dbt test` against an ephemeral Postgres service container in the runner
- **`cd.yml`** (on push to `main`, after CI passes): builds and pushes images for the serving-layer services only, then calls Coolify's API (or `coolify-deploy-action`, gated by a `COOLIFY_API_TOKEN` secret) to redeploy `docker-compose.prod.yml`
- **Data promotion is intentionally not part of `cd.yml`** — it's the manual step in §14, run from your laptop, since that's where the dev warehouse lives. A stretch goal in `TASKS.md` covers optionally triggering it from a self-hosted Actions runner on your own machine.

## 16. Security & secrets handling

- `.env.example` in the repo for local dev only; production secrets (production Postgres URL, Superset secret key, guest-token signing key) live in Coolify's per-resource environment variable settings, and `COOLIFY_API_TOKEN` lives in GitHub Actions secrets — never in Git
- The production Postgres is not exposed on a public port; the promotion script reaches it only via a short-lived SSH tunnel authenticated with your own SSH key
- Superset and Airflow admin UIs stay unexposed — Airflow doesn't run on the VPS at all; only the embed page, the guest-token service, and the dbt docs site get public domains
- Use a read-only Postgres role for Superset on the production database; the promotion script's role needs write access but is only reachable via the SSH tunnel

## 17. Stretch goals

- Extend the guest-token service into a small Go-based "network health" API (pipeline status, last successful local DAG run, consumer lag)
- Mirror the local dev warehouse into BigQuery free tier, to explicitly demonstrate a managed cloud warehouse
- Add Great Expectations as a second, independent validation layer on the raw landing zone (local)
- Add dbt snapshots (SCD2) to track GTFS route/stop changes across feed pulls over time
- Add Terraform for VPS/DNS provisioning
- Run a self-hosted GitHub Actions runner on your laptop so the promotion script can be triggered from a `workflow_dispatch` button instead of run by hand — the data never has to leave your machine except during the promotion itself
- A simple public static insights page (e.g. Evidence.dev or GitHub Pages) for non-technical visitors
