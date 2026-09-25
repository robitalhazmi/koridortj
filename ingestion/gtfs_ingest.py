#!/usr/bin/env python3
"""GTFS Ingestion Pipeline for TransJakarta Open Data.

Downloads, validates, and loads official GTFS reference data (routes, stops, trips, calendar)
into raw PostgreSQL landing tables with structured logging and Pydantic validation.
"""

import csv
import io
import logging
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Type
import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gtfs_ingest")

# Import Pydantic schemas
try:
    from ingestion.schemas import GTFSCalendar, GTFSRoute, GTFSStop, GTFSTrip
except ImportError:
    # Fallback for standalone script execution
    from schemas import GTFSCalendar, GTFSRoute, GTFSStop, GTFSTrip


DEFAULT_GTFS_URL = "https://gtfs.transjakarta.co.id/files/file_gtfs.zip"


class GTFSIngestionError(Exception):
    """Base exception for GTFS ingestion failures."""
    pass


class GTFSIngestor:
    """Manages downloading, parsing, validating, and loading TransJakarta GTFS data."""

    def __init__(
        self,
        db_host: Optional[str] = None,
        db_port: Optional[int] = None,
        db_name: Optional[str] = None,
        db_user: Optional[str] = None,
        db_password: Optional[str] = None,
        feed_url: Optional[str] = None,
    ):
        self.db_host = db_host or os.getenv("POSTGRES_HOST", "localhost")
        self.db_port = int(db_port or os.getenv("POSTGRES_PORT", 5432))
        self.db_name = db_name or os.getenv("POSTGRES_DB_WAREHOUSE", os.getenv("POSTGRES_DB", "warehouse"))
        self.db_user = db_user or os.getenv("POSTGRES_INGESTION_USER", os.getenv("POSTGRES_USER", "postgres"))
        self.db_password = db_password or os.getenv("POSTGRES_INGESTION_PASSWORD", os.getenv("POSTGRES_PASSWORD", "postgres_dev_password"))
        self.feed_url = feed_url or os.getenv("GTFS_FEED_URL", DEFAULT_GTFS_URL)

    def get_connection(self) -> psycopg2.extensions.connection:
        """Establish connection to the target PostgreSQL database."""
        logger.info("Connecting to PostgreSQL at %s:%s/%s as %s", self.db_host, self.db_port, self.db_name, self.db_user)
        try:
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password,
                connect_timeout=10,
            )
            conn.autocommit = False
            return conn
        except Exception as exc:
            logger.error("Failed to connect to PostgreSQL database: %s", exc)
            raise GTFSIngestionError(f"Database connection failed: {exc}") from exc

    def download_feed(self, retries: int = 3, timeout: int = 30) -> bytes:
        """Download GTFS zip archive with retry logic."""
        import requests

        logger.info("Downloading TransJakarta GTFS feed from %s", self.feed_url)
        for attempt in range(1, retries + 1):
            try:
                response = requests.get(self.feed_url, timeout=timeout, headers={"User-Agent": "KoridorTJ-Ingest/1.0"})
                response.raise_for_status()
                content = response.content
                if not content:
                    raise GTFSIngestionError("Downloaded GTFS feed content is empty")
                logger.info("Successfully downloaded GTFS feed (%d bytes)", len(content))
                return content
            except Exception as exc:
                logger.warning("Download attempt %d/%d failed: %s", attempt, retries, exc)
                if attempt == retries:
                    raise GTFSIngestionError(f"Failed to download GTFS feed after {retries} attempts: {exc}") from exc
                time.sleep(2 ** attempt)

        raise GTFSIngestionError("Unexpected download loop termination")

    def validate_and_open_zip(self, zip_bytes: bytes) -> zipfile.ZipFile:
        """Verify ZIP archive integrity and required files."""
        try:
            zip_buffer = io.BytesIO(zip_bytes)
            zf = zipfile.ZipFile(zip_buffer)
            bad_file = zf.testzip()
            if bad_file:
                raise GTFSIngestionError(f"Corrupted file inside GTFS archive: {bad_file}")

            namelist = zf.namelist()
            required = ["routes.txt", "stops.txt", "trips.txt", "calendar.txt"]
            missing = [f for f in required if f not in namelist]
            if missing:
                raise GTFSIngestionError(f"GTFS archive missing required files: {missing}")

            logger.info("GTFS ZIP archive verified. Contains %d files: %s", len(namelist), namelist)
            return zf
        except zipfile.BadZipFile as exc:
            raise GTFSIngestionError(f"Invalid ZIP archive file: {exc}") from exc

    def parse_csv(
        self,
        zf: zipfile.ZipFile,
        filename: str,
        model_cls: Type[BaseModel],
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """Extract and validate records from a GTFS CSV file inside the zip archive."""
        logger.info("Parsing and validating %s ...", filename)
        valid_records: List[Dict[str, Any]] = []
        invalid_count = 0

        with zf.open(filename) as f:
            # Wrap in TextIOWrapper with utf-8-sig to automatically handle any BOM
            text_stream = io.TextIOWrapper(f, encoding="utf-8-sig")
            reader = csv.DictReader(text_stream)

            for row_idx, row in enumerate(reader, start=1):
                # Clean empty string keys or whitespace
                cleaned_row = {k.strip(): (v.strip() if v is not None else None) for k, v in row.items() if k}
                # Convert empty strings to None for optional fields
                cleaned_row = {k: (v if v != "" else None) for k, v in cleaned_row.items()}

                try:
                    validated_item = model_cls.model_validate(cleaned_row)
                    valid_records.append(validated_item.model_dump())
                except ValidationError as exc:
                    invalid_count += 1
                    if invalid_count <= 5:
                        logger.warning("Validation error in %s row %d: %s (Sample data: %s)", filename, row_idx, exc.errors(), cleaned_row)
                    elif invalid_count == 6:
                        logger.warning("Further validation errors in %s will be suppressed from logging.", filename)

        total_rows = len(valid_records) + invalid_count
        logger.info(
            "Finished %s: %d valid records, %d invalid/quarantined (total: %d)",
            filename,
            len(valid_records),
            invalid_count,
            total_rows,
        )
        return valid_records, len(valid_records), invalid_count

    def init_database_schema(self, conn: psycopg2.extensions.connection) -> None:
        """Ensure raw landing tables exist with correct schemas."""
        logger.info("Ensuring PostgreSQL raw schema and landing tables exist...")
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")

            # 1. raw.gtfs_routes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS raw.gtfs_routes (
                    route_id VARCHAR(100) PRIMARY KEY,
                    agency_id VARCHAR(100),
                    route_short_name VARCHAR(255),
                    route_long_name TEXT,
                    route_desc TEXT,
                    route_type INT,
                    route_url TEXT,
                    route_color VARCHAR(50),
                    route_text_color VARCHAR(50),
                    route_sort_order INT,
                    ticketing_deep_link_id VARCHAR(100),
                    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    _source_url TEXT
                );
            """)

            # 2. raw.gtfs_stops
            cur.execute("""
                CREATE TABLE IF NOT EXISTS raw.gtfs_stops (
                    stop_id VARCHAR(100) PRIMARY KEY,
                    stop_code VARCHAR(100),
                    stop_name VARCHAR(255) NOT NULL,
                    stop_desc TEXT,
                    stop_lat DOUBLE PRECISION NOT NULL,
                    stop_lon DOUBLE PRECISION NOT NULL,
                    zone_id VARCHAR(100),
                    stop_url TEXT,
                    location_type INT DEFAULT 0,
                    parent_station VARCHAR(100),
                    stop_timezone VARCHAR(100),
                    wheelchair_boarding INT DEFAULT 0,
                    platform_code VARCHAR(100),
                    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    _source_url TEXT
                );
            """)

            # 3. raw.gtfs_trips
            cur.execute("""
                CREATE TABLE IF NOT EXISTS raw.gtfs_trips (
                    trip_id VARCHAR(100) PRIMARY KEY,
                    route_id VARCHAR(100) NOT NULL,
                    service_id VARCHAR(100) NOT NULL,
                    trip_headsign TEXT,
                    trip_short_name VARCHAR(255),
                    direction_id INT DEFAULT 0,
                    block_id VARCHAR(100),
                    shape_id VARCHAR(100),
                    wheelchair_accessible INT DEFAULT 0,
                    bikes_allowed INT DEFAULT 0,
                    ticketing_trip_id VARCHAR(100),
                    ticketing_type INT DEFAULT 0,
                    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    _source_url TEXT
                );
            """)

            # 4. raw.gtfs_calendar
            cur.execute("""
                CREATE TABLE IF NOT EXISTS raw.gtfs_calendar (
                    service_id VARCHAR(100) PRIMARY KEY,
                    monday INT NOT NULL,
                    tuesday INT NOT NULL,
                    wednesday INT NOT NULL,
                    thursday INT NOT NULL,
                    friday INT NOT NULL,
                    saturday INT NOT NULL,
                    sunday INT NOT NULL,
                    start_date VARCHAR(8) NOT NULL,
                    end_date VARCHAR(8) NOT NULL,
                    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    _source_url TEXT
                );
            """)
            conn.commit()

    def load_table(
        self,
        conn: psycopg2.extensions.connection,
        table_name: str,
        columns: List[str],
        records: List[Dict[str, Any]],
        ingested_at: datetime,
    ) -> int:
        """Perform transactional idempotent bulk load into target raw table."""
        if not records:
            logger.warning("No records to load into %s", table_name)
            return 0

        start_t = time.time()
        # Prepare list of row tuples matching columns + audit columns
        full_columns = columns + ["_ingested_at", "_source_url"]
        rows_to_insert = [
            tuple(r.get(c) for c in columns) + (ingested_at, self.feed_url)
            for r in records
        ]

        query = f"""
            INSERT INTO {table_name} ({', '.join(full_columns)})
            VALUES %s
            ON CONFLICT ({columns[0]}) DO UPDATE SET
                {', '.join(f"{c} = EXCLUDED.{c}" for c in columns[1:])},
                _ingested_at = EXCLUDED._ingested_at,
                _source_url = EXCLUDED._source_url;
        """

        with conn.cursor() as cur:
            execute_values(cur, query, rows_to_insert, page_size=1000)
            conn.commit()

        elapsed = time.time() - start_t
        logger.info("Loaded %d rows into %s (took %.2fs)", len(records), table_name, elapsed)
        return len(records)

    def run(self, local_zip_path: Optional[str] = None) -> Dict[str, Any]:
        """Execute full GTFS ingestion pipeline."""
        pipeline_start = time.time()
        now_utc = datetime.now(timezone.utc)
        logger.info("=== Starting TransJakarta GTFS Ingestion Pipeline ===")

        # 1. Acquire ZIP
        if local_zip_path and os.path.exists(local_zip_path):
            logger.info("Using provided local GTFS archive: %s", local_zip_path)
            with open(local_zip_path, "rb") as f:
                zip_bytes = f.read()
        else:
            zip_bytes = self.download_feed()

        # 2. Validate ZIP
        zf = self.validate_and_open_zip(zip_bytes)

        # 3. Parse and Validate Models
        routes_data, routes_valid, routes_inv = self.parse_csv(zf, "routes.txt", GTFSRoute)
        stops_data, stops_valid, stops_inv = self.parse_csv(zf, "stops.txt", GTFSStop)
        trips_data, trips_valid, trips_inv = self.parse_csv(zf, "trips.txt", GTFSTrip)
        calendar_data, cal_valid, cal_inv = self.parse_csv(zf, "calendar.txt", GTFSCalendar)

        # 4. Connect to PostgreSQL and Load
        conn = self.get_connection()
        try:
            self.init_database_schema(conn)

            # Load routes
            route_cols = [
                "route_id", "agency_id", "route_short_name", "route_long_name",
                "route_desc", "route_type", "route_url", "route_color",
                "route_text_color", "route_sort_order", "ticketing_deep_link_id"
            ]
            self.load_table(conn, "raw.gtfs_routes", route_cols, routes_data, now_utc)

            # Load stops
            stop_cols = [
                "stop_id", "stop_code", "stop_name", "stop_desc", "stop_lat",
                "stop_lon", "zone_id", "stop_url", "location_type",
                "parent_station", "stop_timezone", "wheelchair_boarding", "platform_code"
            ]
            self.load_table(conn, "raw.gtfs_stops", stop_cols, stops_data, now_utc)

            # Load trips
            trip_cols = [
                "trip_id", "route_id", "service_id", "trip_headsign", "trip_short_name",
                "direction_id", "block_id", "shape_id", "wheelchair_accessible",
                "bikes_allowed", "ticketing_trip_id", "ticketing_type"
            ]
            self.load_table(conn, "raw.gtfs_trips", trip_cols, trips_data, now_utc)

            # Load calendar
            cal_cols = [
                "service_id", "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday", "start_date", "end_date"
            ]
            self.load_table(conn, "raw.gtfs_calendar", cal_cols, calendar_data, now_utc)

        finally:
            conn.close()

        total_duration = time.time() - pipeline_start
        summary = {
            "status": "SUCCESS",
            "ingested_at": now_utc.isoformat(),
            "duration_seconds": round(total_duration, 2),
            "routes": {"valid": routes_valid, "invalid": routes_inv},
            "stops": {"valid": stops_valid, "invalid": stops_inv},
            "trips": {"valid": trips_valid, "invalid": trips_inv},
            "calendar": {"valid": cal_valid, "invalid": cal_inv},
        }
        logger.info("=== GTFS Ingestion Completed Successfully in %.2fs ===", total_duration)
        logger.info("Summary: %s", summary)
        return summary


def main():
    """CLI entrypoint."""
    local_path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        ingestor = GTFSIngestor()
        ingestor.run(local_zip_path=local_path)
    except Exception as e:
        logger.critical("GTFS Ingestion failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
