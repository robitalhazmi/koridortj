# Data Sources & Ingestion Provenance — KoridorTJ

This document records the exact data source origins, access endpoints, licensing terms, update cadence, and raw schemas used across the KoridorTJ platform.

---

## 1. TransJakarta GTFS Feed (Reference Data)

| Attribute | Specification |
|---|---|
| **Data Nature** | **Real, official reference data** |
| **Provider / Publisher** | PT Transportasi Jakarta (via PPID Open Data Portal) |
| **Official Portal** | [PPID TransJakarta Data Terbuka](https://ppid.transjakarta.co.id/pusat-data/data-terbuka/transjakarta-gtfs-feed) |
| **Direct Feed URL** | `https://gtfs.transjakarta.co.id/files/file_gtfs.zip` |
| **License** | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| **Update Frequency** | Periodic (as route revisions, stop changes, and schedule modifications occur) |
| **Ingestion Pipeline** | `ingestion/gtfs_ingest.py` (Automated weekly via Airflow DAG `gtfs_ingest_dag`) |

### Ingested GTFS Tables & Verification Counts

| Source File | Raw PostgreSQL Table | Primary Key | Verified Row Count | Description |
|---|---|---|---|---|
| `routes.txt` | `raw.gtfs_routes` | `route_id` | **240** | BRT corridors, feeder routes, Mikrotrans, and tourist bus routes |
| `stops.txt` | `raw.gtfs_stops` | `stop_id` | **8,091** | Bus stops, BRT stations, and integration points with geographic coordinates |
| `trips.txt` | `raw.gtfs_trips` | `trip_id` | **700** | Directional trip patterns and shape associations |
| `calendar.txt` | `raw.gtfs_calendar` | `service_id` | **7** | Service availability rules across weekdays, weekends, and holidays |

### Audit & Lineage Metadata

Every row loaded into the `raw` schema is stamped with two audit columns:
- `_ingested_at` (`TIMESTAMPTZ`): UTC timestamp when the record was validated and inserted.
- `_source_url` (`TEXT`): Origin URL of the feed archive at the time of ingestion.

---

## 2. Simulated Tap-in / Tap-out Transaction Dataset (Fact Data)

| Attribute | Specification |
|---|---|
| **Data Nature** | **Simulated / Synthetic** |
| **Description** | Faker-generated timestamped tap-in and tap-out transaction events built upon the real TransJakarta stop/route structure. |
| **Usage** | Demonstrates high-volume batch loading and real-time Kafka streaming replay patterns. |
| **Labeling Standard** | Explicitly labeled as simulated across all models (`is_simulated = TRUE`), dashboards, and documentation. |
| **Phase** | Phase 2 (Historical Batch Loader) & Phase 5 (Kafka Streaming Replay) |
