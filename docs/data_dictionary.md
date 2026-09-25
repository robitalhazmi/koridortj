# Data Dictionary — KoridorTJ Transit Platform

> **Data Provenance & Disclaimer:**
> Reference GTFS data (routes, stops, trips, calendars) reflects official public transit feeds from PT Transportasi Jakarta. All passenger tap transactions (`raw.taps`, `raw.taps_stream`, `stg_taps`, `stg_streaming_taps`, and `fact_taps`) represent synthetic/simulated data modeled after open public patterns for analytics demonstration. The `is_simulated` column is explicitly set to `TRUE` across all fact records.

---

## 1. Overview of Data Architecture

The KoridorTJ warehouse uses a **Medallion / Layered ELT Architecture**:
- **Raw Layer (`raw`)**: Exact mirror of source feeds (GTFS CSVs, batch CSV transactions, real-time Kafka streams).
- **Staging Layer (`staging`)**: Views providing column cleaning, whitespace trimming, datatype casting, and unpivoting of tap transactions.
- **Warehouse Layer (`warehouse`)**: Star schema consisting of conformed dimension tables (`dim_*`) and unified fact tables (`fact_*`).

```
[GTFS Feed]       --> raw.gtfs_*       --> stg_routes / stg_stops / stg_trips / stg_calendar --> dim_routes / dim_stops / dim_corridors / dim_calendar
[Historical CSV]  --> raw.taps         --> stg_taps           \
[Kafka Stream]    --> raw.taps_stream  --> stg_streaming_taps  --> fact_taps
```

---

## 2. Warehouse Layer (Star Schema)

### `warehouse.fact_taps`
**Description:** Star schema fact table recording granular passenger tap-in (boarding) and tap-out (alighting) transactions. Combines historical batch records and streaming Kafka events with automated deduplication.  
**Materialization:** Table  
**Primary Key:** `tap_id` (`<trans_id>_IN` or `<trans_id>_OUT`)  
**Foreign Keys:** `route_id` -> `dim_routes`, `stop_id` -> `dim_stops`, `date_id` -> `dim_calendar`  

| Column Name | Data Type | Nullable | Key / Constraint | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- |
| `tap_id` | VARCHAR(110) | NO | PK, Unique | Surrogate primary key uniquely identifying each discrete tap event. Formed by appending `_IN` or `_OUT` to `trans_id`. |
| `trans_id` | VARCHAR(100) | NO | Indexed | Unique transaction identifier linking matching tap-in and tap-out event pairs for a single trip. |
| `pay_card_id` | VARCHAR(100) | NO | Indexed | Anonymized passenger smart card identifier (e-money, Flazz, TapCash, JakLingko). |
| `pay_card_bank` | VARCHAR(100) | YES | — | Card issuer/bank identifier (e.g., `emoney`, `flazz`, `bni`, `dki`, `bri`). |
| `pay_card_name` | VARCHAR(255) | YES | — | Cardholder name associated with the payment card. |
| `pay_card_sex` | VARCHAR(10) | YES | Accepted: `M`, `F` | Passenger gender indicator. |
| `pay_card_birth_date`| INT | YES | Range [1900, 2026] | Passenger birth year. |
| `route_id` | VARCHAR(100) | NO | FK -> `dim_routes` | Foreign key referencing the bus route or BRT corridor. |
| `stop_id` | VARCHAR(100) | NO | FK -> `dim_stops` | Foreign key referencing the specific bus stop or shelter where tap occurred. |
| `date_id` | INT | NO | FK -> `dim_calendar` | Integer surrogate foreign key in `YYYYMMDD` format (e.g. `20230403`). |
| `corridor_code` | VARCHAR(100) | YES | — | Operational corridor code (e.g., `1`, `5`, `6C`, `R1A`). |
| `direction` | INT | NO | Accepted: `0`, `1` | Travel direction (`0` = Outbound, `1` = Inbound). |
| `tap_type` | VARCHAR(10) | NO | Accepted: `IN`, `OUT` | Event stage flag. `IN` indicates boarding fare gate; `OUT` indicates alighting gate. |
| `tap_timestamp` | TIMESTAMP | NO | Test: `<= now()` | UTC timestamp at which passenger tapped the validator. |
| `stop_sequence` | INT | YES | Positive | Sequence number of the stop along the vehicle route pattern. |
| `pay_amount` | NUMERIC(10,2)| NO | Test: `0 <= amount <= 50000` | Fare charged in Indonesian Rupiah (IDR). Standard BRT flat fare is `3500.00` on tap-in, and `0.00` on tap-out. |
| `is_simulated` | BOOLEAN | NO | Accepted: `TRUE` | Explicit indicator confirming synthetic nature of transaction records. |
| `_ingested_at` | TIMESTAMPTZ | NO | Default: `now()` | Ingestion timestamp when the record entered the data warehouse. |

---

### `warehouse.dim_routes`
**Description:** Conformed route dimension containing official TransJakarta BRT trunk lines, non-BRT feeder routes, Mikrotrans, and tourist lines.  
**Materialization:** Table  
**Primary Key:** `route_id`  

| Column Name | Data Type | Nullable | Key / Constraint | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- |
| `route_id` | VARCHAR(100) | NO | PK, Unique | Unique route identifier (e.g., `1`, `9C`, `GR1`, `UNKNOWN`). |
| `route_short_name` | VARCHAR(100) | YES | — | Short public route code shown on bus displays and maps. |
| `route_long_name` | VARCHAR(255) | YES | — | Full descriptive route name (e.g., `Blok M - Kota`). |
| `route_name` | VARCHAR(255) | NO | Not Null | Consolidated public name resolved from long name or corridor description. |
| `route_desc` | VARCHAR(255) | YES | — | Service classification (e.g., `BRT`, `Non-BRT`, `Mikrotrans`). |
| `route_type` | INT | NO | Accepted: `3` | GTFS route type code (`3` = Bus / Road transit). |
| `route_color` | VARCHAR(20) | YES | Hex format | Hexadecimal color code representing the route on transit maps (e.g., `#D32F2F`). |
| `route_text_color` | VARCHAR(20) | YES | Hex format | Hexadecimal color code for text displayed on route badges. |

---

### `warehouse.dim_stops`
**Description:** Conformed stop dimension representing all TransJakarta BRT elevated/median stations, roadside bus stops, and interchange hubs with WGS84 GPS coordinates.  
**Materialization:** Table  
**Primary Key:** `stop_id`  

| Column Name | Data Type | Nullable | Key / Constraint | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- |
| `stop_id` | VARCHAR(100) | NO | PK, Unique | Unique stop identifier (e.g., `1-1`, `P00142`, `B01963P`). |
| `stop_code` | VARCHAR(100) | YES | — | Public stop code. |
| `stop_name` | VARCHAR(255) | NO | Not Null | Standardized public name of the stop/station (e.g., `Harmoni`, `Monas`). |
| `stop_desc` | VARCHAR(255) | YES | — | Landmark, district, or street description. |
| `latitude` | DOUBLE PRECISION | NO | Bounding: `[-7.0, -5.5]` | WGS84 latitude coordinate in the Jakarta metropolitan region. |
| `longitude` | DOUBLE PRECISION | NO | Bounding: `[106.3, 107.5]`| WGS84 longitude coordinate in the Jakarta metropolitan region. |
| `location_type` | INT | YES | Accepted: `0`, `1` | GTFS location type (`0` = Stop/Platform, `1` = Station/Interchange). |
| `parent_station` | VARCHAR(100) | YES | — | Stop ID of parent station if platform is nested. |
| `wheelchair_boarding` | INT | YES | Accepted: `0`, `1`, `2` | Accessibility code (`1` = Accessible, `2` = Not accessible, `0` = Unknown). |

---

### `warehouse.dim_corridors`
**Description:** Conformed dimension for TransJakarta dedicated BRT corridors and directional branches.  
**Materialization:** Table  
**Primary Key:** `corridor_code`  

| Column Name | Data Type | Nullable | Key / Constraint | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- |
| `corridor_code` | VARCHAR(100) | NO | PK, Unique | Public corridor code (e.g., `1`, `2A`, `6C`, `11D`). |
| `corridor_name` | VARCHAR(255) | NO | Not Null | Descriptive title of corridor endpoints (e.g., `Blok M - Kota`). |

---

### `warehouse.dim_calendar`
**Description:** Date dimension spanning transit operations (2022–2026) containing calendar attributes for temporal slicing and aggregations.  
**Materialization:** Table  
**Primary Key:** `date_id`  

| Column Name | Data Type | Nullable | Key / Constraint | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- |
| `date_id` | INT | NO | PK, Unique | Surrogate integer key in `YYYYMMDD` format (e.g. `20230403`). |
| `full_date` | DATE | NO | Unique | Calendar date (`YYYY-MM-DD`). |
| `year` | INT | NO | Range: `[2022, 2026]` | Calendar year. |
| `quarter` | INT | NO | Range: `[1, 4]` | Calendar quarter. |
| `month` | INT | NO | Range: `[1, 12]` | Month number. |
| `month_name` | VARCHAR(20) | NO | — | Full month name (e.g. `April`, `September`). |
| `day_of_month`| INT | NO | Range: `[1, 31]` | Day of month number. |
| `day_of_week` | INT | NO | Range: `[1, 7]` | ISO day of week (`1` = Monday, `7` = Sunday). |
| `day_name` | VARCHAR(20) | NO | — | Full weekday name (e.g. `Monday`, `Sunday`). |
| `is_weekend` | BOOLEAN | NO | Accepted: `TRUE`, `FALSE`| `TRUE` for Saturday and Sunday; `FALSE` for Monday–Friday. |

---

## 3. Staging Layer (`staging`)

Staging views clean, normalize, and expose raw landing data to the warehouse modeling layer.

| View Name | Source Table | Purpose | Primary Key |
| :--- | :--- | :--- | :--- |
| `stg_routes` | `raw.gtfs_routes` | Trims strings, filters null IDs, casts route types | `route_id` |
| `stg_stops` | `raw.gtfs_stops` | Normalizes coordinates, validates spatial boundaries | `stop_id` |
| `stg_trips` | `raw.gtfs_trips` | Cleans trip patterns and directional mappings | `trip_id` |
| `stg_calendar` | `raw.gtfs_calendar` | Standardizes date formats and service masks | `service_id` |
| `stg_taps` | `raw.taps` | Unpivots batch tap rows into discrete `IN`/`OUT` events | `tap_id` |
| `stg_streaming_taps` | `raw.taps_stream` | Unpivots real-time Kafka tap rows into discrete `IN`/`OUT` events | `tap_id` |

---

## 4. Raw & Streaming Ingestion Layer (`raw`)

| Table Name | Source Origin | Ingestion Method | Refresh Frequency |
| :--- | :--- | :--- | :--- |
| `raw.gtfs_routes` | PT Transportasi Jakarta GTFS Feed | Python `gtfs_ingestion.py` / Airflow DAG | Weekly (`0 3 * * 1`) |
| `raw.gtfs_stops` | PT Transportasi Jakarta GTFS Feed | Python `gtfs_ingestion.py` / Airflow DAG | Weekly (`0 3 * * 1`) |
| `raw.gtfs_trips` | PT Transportasi Jakarta GTFS Feed | Python `gtfs_ingestion.py` / Airflow DAG | Weekly (`0 3 * * 1`) |
| `raw.gtfs_calendar` | PT Transportasi Jakarta GTFS Feed | Python `gtfs_ingestion.py` / Airflow DAG | Weekly (`0 3 * * 1`) |
| `raw.taps` | Historical Transaction Dataset | Python `tap_loader.py` | One-off historical baseline |
| `raw.taps_stream` | Kafka Topic `taps.raw` | Python `tap_consumer.py` micro-batches | Continuous real-time streaming |

---

## 5. Dead-Letter Queue (DLQ) Governance

When malformed or unparseable payloads arrive over Kafka topic `taps.raw`, they are rejected by Pydantic validation before database landing and routed to `taps.deadletter`.

### DLQ Payload Schema (`DeadLetterEvent`)
```json
{
  "original_payload": { ... },
  "error_message": "Detailed description of validation or parsing failure",
  "error_type": "ValidationError | JSONDecodeError | DatabaseError",
  "failed_at": "2026-09-25T03:33:17.476460+00:00",
  "source_topic": "taps.raw"
}
```

---

## 6. Automated Quality Gate Rules

| Test Category | Target Models | Rule / Expression | Action on Failure |
| :--- | :--- | :--- | :--- |
| **Uniqueness** | All Dimension & Fact PKs | `count(*) = count(distinct PK)` | **DAG Fails** (Build halts) |
| **Completeness** | Mandatory columns (`stop_id`, `route_id`, `tap_timestamp`) | `column IS NOT NULL` | **DAG Fails** |
| **Referential Integrity** | `fact_taps` -> Dimensions | Foreign keys must resolve in `dim_routes`, `dim_stops`, `dim_calendar` | **DAG Fails** |
| **Chronological Validity** | `raw.taps`, `raw.taps_stream`, `fact_taps` | `tap_out_time >= tap_in_time` AND `tap_timestamp <= now()` | **DAG Fails** |
| **Fare Bounds** | `fact_taps` | `0.00 <= pay_amount <= 50000.00` | **DAG Fails** |
| **Geographic Bounds** | `dim_stops` | Lat `[-7.0, -5.5]`, Lon `[106.3, 107.5]` | **DAG Fails** |
| **Simulated Flag** | `fact_taps`, `stg_taps`, `stg_streaming_taps` | `is_simulated = TRUE` | **DAG Fails** |
