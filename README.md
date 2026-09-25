# KoridorTJ — TransJakarta Transit Data Platform

> **Status:** 🚧 Under Active Development (Phase 0: Repository & Environment Setup)

KoridorTJ is an end-to-end data platform built around Jakarta's TransJakarta BRT network. It ingests official TransJakarta open transit data (GTFS routes, stops, schedules), combines it with a simulated tap-in/tap-out transaction stream, and models both into a tested, documented PostgreSQL analytics warehouse served via Apache Superset dashboards and automated with Apache Airflow and dbt.

---

## Documentation & Roadmap

- **Architecture & Story:** [WALKTHROUGH.md](WALKTHROUGH.md)
- **Technical Specifications & Tech Stack:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- **Development Roadmap & Task Checklist:** [TASKS.md](TASKS.md)

---

## Disclaimer

The transit **network structure** (routes, stops, schedules) uses real, official TransJakarta open data. All **transaction/ridership volumes** are simulated and do **not** represent actual passenger counts.
