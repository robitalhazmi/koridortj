# Implementation Plan — KoridorTJ

## 1. Goals and non-goals

**Goals**
- Demonstrate every "must-have" in the Data Engineer JD with a real, runnable system (not slides).
- Cover the "plus" items (streaming, Golang, CI/CD, containerization, cloud, governance) without turning the core build into a sprawl.
- Produce something genuinely inspectable by a non-technical visitor (public dashboard) and a technical one (dbt docs, ERD, GitHub repo, CI badge).
- Be honest about which data is real (Transjakarta network structure) vs. simulated (transaction volumes).

**Non-goals**
- This is not a claim of real Transjakarta ridership statistics — see the disclaimer pattern used throughout.
- Not aiming for production-grade high availability; aiming for a correct, well-documented, single-node-per-service deployment that a reviewer can actually click through.

## 2. Tech stack, with rationale

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Strongest language; ecosystem fit for every layer below |
| Optional 2nd language | Go | Stretch-only; JD lists Golang as a plus, kept isolated so it's not a dependency for the core pipeline |
| Warehouse | PostgreSQL | Free, self-hostable, exactly matches "hands-on experience with Postgres"; BigQuery mirror is a clearly separated stretch task |
| Orchestration | Apache Airflow | Named explicitly in the JD; industry standard; first orchestration project, so kept to LocalExecutor (simpler mental model) |
| Transformation | dbt-core | Market-standard ELT transformation tool; gives tests, docs, and lineage "for free," which directly covers the JD's quality/documentation/governance asks |
| Streaming | Apache Kafka (KRaft mode) | Named explicitly in the JD; KRaft mode means no ZooKeeper, so the Compose setup is not much heavier than a Kafka-compatible alternative |
| Data quality | dbt tests + Pydantic (+ optional Great Expectations, stretch) | dbt tests cover the warehouse layer; Pydantic covers the ingestion boundary (schema validation before anything lands) |
| BI | Apache Superset | Apache-family tool that pairs naturally with Airflow/Kafka for a cohesive "Apache stack" story, and reads as more DE-specific to interviewers; public embedding needs a small guest-token service rather than a one-click toggle (see §10) — that gap becomes a core Phase 7 task, doubling as the JD's Golang-plus item |
| Containers | Docker + Docker Compose | Directly named in the JD; one compose file can run the whole stack locally or on the VPS |
| CI/CD | GitHub Actions | Matches "GitHub to sync code"; free for public repos; directly named pattern in the JD (CI/CD) |
| Hosting | Your VPS, managed by Coolify | Coolify deploys the Docker Compose stack straight from GitHub, handles HTTPS automatically (Traefik under the hood), and provides a managed Postgres resource with automated backups — real infra ownership with far less manual ops |
| IDE | Antigravity IDE | Already your chosen local dev environment |

## 3. Data sources

| Source | What it provides | Nature |
|---|---|---|
| Transjakarta official GTFS feed (via their public open-data portal, `ppid.transjakarta.co.id` → GTFS zip) | Routes, stops, trips, calendars/schedules for the full BRT network | **Real**, official, updates periodically |
| Public Transjakarta tap-in/tap-out transaction dataset | Per-trip transaction-like records (timestamps, stop/route references) generated with Faker on top of the real route/stop master data | **Simulated** — no real transaction data has been publicly released, so this fills that gap safely |

Both sources must be re-verified for current URLs/terms before you start Phase 1, since portal URLs and dataset hosting can change. Store the exact source URL and access date in `/docs/data_sources.md` when you download them.

**Labeling rule (apply everywhere):** any UI, dashboard, or doc that shows tap/ridership numbers must say "simulated data" in the same view — not just in a README three clicks away.

## 4. Repo structure

```
KoridorTJ/
├── docker-compose.yml
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
│   └── guest_token_service/   # small Python or Go service issuing Superset guest tokens for the public embed page
└── .github/
    └── workflows/
        ├── ci.yml
        └── cd.yml
```

## 5. Data model (star schema)

- `dim_routes` — route_id, route_name, route_type, corridor_code
- `dim_stops` — stop_id, stop_name, latitude, longitude
- `dim_corridors` — corridor_code, corridor_name, direction
- `dim_calendar` — date, day_of_week, is_weekend, is_holiday
- `fact_taps` — tap_id, route_id (FK), stop_id (FK), date_id (FK), tap_type (in/out), tap_timestamp, is_simulated (always true, kept as an explicit column so it can never be dropped silently downstream)

Keep `is_simulated` as a real column, not just documentation — it means any future real data source could be UNIONed in later without relabeling everything by hand.

## 6. Streaming design

- **Topic:** `taps.raw` (JSON events), **dead-letter topic:** `taps.deadletter`
- **Producer (`replay_producer.py`):** reads the historical tap dataset in timestamp order, rewrites each record's timestamp relative to "now" using a configurable speed multiplier (e.g., 1 real day of history replayed every 10 minutes), publishes to `taps.raw`
- **Consumer (`tap_consumer.py`):** validates each message against a Pydantic schema; valid → insert into raw Postgres table `raw.taps`; invalid → publish to `taps.deadletter` with the validation error attached
- **Why replay, not a live feed:** no confirmed public real-time Transjakarta feed was found; replay is the standard, transparent way to demonstrate streaming ingestion patterns without fabricating a live data source

## 7. Airflow DAGs

| DAG | Schedule | Tasks |
|---|---|---|
| `gtfs_ingest` | Weekly | download GTFS zip → validate structure → load raw tables → log row-count deltas |
| `warehouse_build` | Nightly | `dbt run` → `dbt test` → on failure, fail loudly (no silent partial loads) |

Both DAGs should be written idempotently (safe re-runs), and use Airflow connections/variables for credentials — never hardcode them in the DAG file.

## 8. dbt project layout

- `staging/`: 1:1 cleaned views over raw tables (renaming, type casting, light filtering)
- `warehouse/`: the star schema models described in §5
- `schema.yml` per folder: column descriptions + tests (`not_null`, `unique`, `relationships`, `accepted_values`)
- At least 3 custom singular tests in `tests/`: e.g. no tap timestamps in the future, tap-out always after matching tap-in, all `stop_id`s in `fact_taps` exist in `dim_stops`

## 9. Data quality & governance

- **Quality gate:** `warehouse_build` DAG fails if `dbt test` fails — no bad data reaches Metabase
- **Metadata:** `dbt docs generate` + `dbt docs serve` (or host the static output) gives a browsable catalog with column descriptions and a lineage graph — this is your "documentation for data models and system flows" deliverable, and doubles as lightweight data governance/metadata management
- **Manual docs:** `/docs/data_dictionary.md` (plain-English column definitions) and `/docs/erd.md` (Mermaid ER diagram) for reviewers who don't want to run dbt docs locally

## 10. BI / dashboard plan

- Apache Superset connected directly to the Postgres warehouse (read-only DB user, not the ingestion user)
- Suggested dashboards: ridership by corridor & hour-of-day, weekday vs. weekend pattern, top boarding stops, simple network map if stop lat/long renders cleanly
- Superset dashboards are private by default — there's no one-click "make public" toggle. To make a dashboard genuinely public: enable the `EMBEDDED_SUPERSET` feature flag, build a small **guest-token service** (Python/FastAPI or Go) that mints short-lived Superset guest JWTs for anonymous visitors, and embed the dashboard on a small public HTML page that calls that service. Writing it in Go covers the JD's Golang-plus line with a naturally-scoped piece of work rather than a bolted-on stretch goal.
- Keep the Superset admin console itself unexposed (no public domain) — only the embed page and the token service are public-facing

## 11. Containerization

Single `docker-compose.yml` with services: `postgres`, `kafka` (KRaft, single broker), `airflow-webserver`, `airflow-scheduler`, `replay-producer`, `tap-consumer`, `metabase`. Keep resource limits explicit (`mem_limit`, `cpus`) so it fits comfortably on your VPS.

## 12. Deployment to the VPS (via Coolify)

1. In Coolify, create a **Docker Compose** resource pointing at the GitHub repo/branch, using `docker-compose.yml` as the deployment definition
2. Create a **Coolify-managed Postgres** database resource (free automated backups) with two logical databases — `warehouse` and `airflow_meta` — instead of running Postgres as a plain compose service
3. Assign a subdomain per public-facing service (e.g. `embed.yourdomain` for the public dashboard page, `dbtdocs.yourdomain` for the catalog) — Coolify/Traefik issues HTTPS certs automatically per domain
4. Set all secrets (DB password, Airflow Fernet key, Kafka config, guest-token signing key) as environment variables on the Coolify resource itself, not in a repo `.env` — keep `.env.example` in the repo for local dev only
5. Leave Airflow and the Superset admin console **unexposed** (no public domain, or behind Coolify's basic auth) — only the embed page, the token service, and the dbt docs site get public domains
6. First deploy manually from the Coolify UI to confirm the stack behaves; wire automatic, CI-gated redeploys afterward (§13)

## 13. CI/CD (GitHub Actions)

- **`ci.yml`** (on pull request): `ruff`/`black` check, `sqlfluff` lint on SQL, `pytest` for ingestion/validation code, `dbt test` run against a throwaway Postgres service container in the Action runner
- **`cd.yml`** (on push to `main`, after CI passes): build Docker images, push to GHCR, then call Coolify's REST API (or the community `coolify-deploy-action`) with a `COOLIFY_API_TOKEN` secret to trigger a redeploy of the Compose resource — keeps deploys gated behind passing CI rather than relying on Coolify's own raw auto-deploy-on-push
- Add a status badge for `ci.yml` to the top of `README.md`

## 14. Security & secrets handling

- `.env.example` in the repo with placeholder values for local dev; production secrets live only in Coolify's per-resource environment variable settings and in GitHub Actions secrets (`COOLIFY_API_TOKEN`) — never in Git
- Superset and Airflow admin UIs should sit behind their own auth, and ideally not be publicly exposed at all — only the embed page, the guest-token service, and the dbt docs site should have public domains
- Use a read-only Postgres role for Superset; a separate role for dbt/Airflow with only the privileges it needs; the guest-token service itself needs no direct database access

## 15. Stretch goals (see `TASKS.md` for the checklist form)

- Extend the guest-token service into a small Go-based "network health" API exposing live pipeline status (last successful DAG run, consumer lag) for extra Golang depth beyond the core token service
- BigQuery free-tier warehouse mirror, to explicitly demonstrate a managed cloud warehouse alongside self-hosted Postgres
- Great Expectations as an additional, independent validation layer on the raw landing zone
- dbt snapshots (SCD2) to track GTFS route/stop changes across feed pulls over time
- Terraform for VPS/DNS provisioning
- A simple public static insights page (e.g. Evidence.dev or GitHub Pages) for non-technical visitors
