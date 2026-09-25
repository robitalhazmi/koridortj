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
| **Original Publisher / Repository** | Public capstone dataset by `rahmadits/capstone2_transjakarta` (derived from Kaggle dataset by `dikirenanda`) |
| **Source URL** | `https://raw.githubusercontent.com/rahmadits/capstone2_transjakarta/master/Transjakarta.csv` |
| **Date Range Covered** | April 1, 2023 – April 30, 2023 |
| **Verified Row Count** | **37,900 transactions** (2,000 unique passenger cards) |
| **Landing Table** | `raw.taps` (PostgreSQL `warehouse` database) |
| **Ingestion Pipeline** | `ingestion/tap_loader.py` |
| **Labeling Standard** | Explicitly flagged as synthetic on every record (`is_simulated = TRUE`). |

### Raw Schema: `raw.taps`

| Column | Data Type | Nullable | Description |
|---|---|---|---|
| `trans_id` | `VARCHAR(100)` | No (PK) | Unique transaction alphanumeric identifier |
| `pay_card_id` | `VARCHAR(100)` | No | Customer payment card identifier |
| `pay_card_bank` | `VARCHAR(100)` | Yes | Issuing card bank (e.g., `emoney`, `flazz`, `brizzi`, `dki`) |
| `pay_card_name` | `VARCHAR(255)` | Yes | Passenger name embedded on payment card |
| `pay_card_sex` | `VARCHAR(10)` | Yes | Passenger gender (`M`/`F`) |
| `pay_card_birth_date` | `INT` | Yes | Passenger birth year |
| `corridor_id` | `VARCHAR(100)` | Yes | Route / corridor ID |
| `corridor_name` | `VARCHAR(255)` | Yes | Corridor descriptive name |
| `direction` | `INT` | Yes | Direction flag (0 = Outbound, 1 = Inbound) |
| `tap_in_stops` | `VARCHAR(100)` | Yes | Tap-in stop ID |
| `tap_in_stops_name` | `VARCHAR(255)` | Yes | Tap-in stop name |
| `tap_in_stops_lat` | `DOUBLE PRECISION` | Yes | Tap-in stop latitude coordinate |
| `tap_in_stops_lon` | `DOUBLE PRECISION` | Yes | Tap-in stop longitude coordinate |
| `stop_start_seq` | `INT` | Yes | Sequence number of tap-in stop |
| `tap_in_time` | `TIMESTAMP` | Yes | Timestamp of tap-in |
| `tap_out_stops` | `VARCHAR(100)` | Yes | Tap-out stop ID |
| `tap_out_stops_name` | `VARCHAR(255)` | Yes | Tap-out stop name |
| `tap_out_stops_lat` | `DOUBLE PRECISION` | Yes | Tap-out stop latitude coordinate |
| `tap_out_stops_lon` | `DOUBLE PRECISION` | Yes | Tap-out stop longitude coordinate |
| `stop_end_seq` | `INT` | Yes | Sequence number of tap-out stop |
| `tap_out_time` | `TIMESTAMP` | Yes | Timestamp of tap-out |
| `pay_amount` | `NUMERIC(10,2)` | Yes | Fare amount in IDR (standard Rp 3,500) |
| `is_simulated` | `BOOLEAN` | No | Constant `TRUE` indicator for synthetic fact data |
| `_ingested_at` | `TIMESTAMPTZ` | No | Ingestion timestamp |
| `_source_file` | `TEXT` | Yes | Source filename reference |
