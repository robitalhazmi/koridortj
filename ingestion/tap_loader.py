#!/usr/bin/env python3
"""Historical Simulated Tap Transaction Loader for KoridorTJ.

Downloads the public simulated TransJakarta transaction dataset, validates each transaction
using Pydantic, and loads raw records into PostgreSQL table `raw.taps` with audit metadata
and explicit `is_simulated = TRUE` flagging.
"""

import argparse
import csv
import logging
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values
from pydantic import ValidationError

# Load environment variables
load_dotenv()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("tap_loader")

# Import schema model
try:
    from ingestion.schemas import RawTapTransaction
except ImportError:
    from schemas import RawTapTransaction


DEFAULT_TAP_URL = (
    "https://raw.githubusercontent.com/rahmadits/capstone2_transjakarta/master/Transjakarta.csv"
)
DEFAULT_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "transjakarta_taps.csv"
)


class TapLoaderError(Exception):
    """Base exception for tap loading errors."""

    pass


class TapLoader:
    """Manages downloading, validating, and landing simulated tap transaction records."""

    def __init__(
        self,
        db_host: str | None = None,
        db_port: int | None = None,
        db_name: str | None = None,
        db_user: str | None = None,
        db_password: str | None = None,
        dataset_url: str | None = None,
        cache_path: str | None = None,
    ):
        self.db_host = db_host or os.getenv("POSTGRES_HOST", "localhost")
        self.db_port = int(db_port or os.getenv("POSTGRES_PORT", 5432))
        self.db_name = db_name or os.getenv(
            "POSTGRES_DB_WAREHOUSE", os.getenv("POSTGRES_DB", "warehouse")
        )
        self.db_user = db_user or os.getenv(
            "POSTGRES_INGESTION_USER", os.getenv("POSTGRES_USER", "postgres")
        )
        self.db_password = db_password or os.getenv(
            "POSTGRES_INGESTION_PASSWORD", os.getenv("POSTGRES_PASSWORD", "postgres_dev_password")
        )
        self.dataset_url = dataset_url or os.getenv("TAP_DATASET_URL", DEFAULT_TAP_URL)
        self.cache_path = cache_path or os.getenv("TAP_CACHE_PATH", DEFAULT_CACHE_PATH)

    def get_connection(self) -> psycopg2.extensions.connection:
        """Establish connection to the target PostgreSQL database."""
        hosts_to_try = [self.db_host]
        if self.db_host == "postgres" and "localhost" not in hosts_to_try:
            hosts_to_try.append("localhost")

        last_exc = None
        for host in hosts_to_try:
            logger.info(
                "Connecting to PostgreSQL at %s:%s/%s as %s",
                host,
                self.db_port,
                self.db_name,
                self.db_user,
            )
            try:
                conn = psycopg2.connect(
                    host=host,
                    port=self.db_port,
                    dbname=self.db_name,
                    user=self.db_user,
                    password=self.db_password,
                    connect_timeout=10,
                )
                conn.autocommit = False
                return conn
            except Exception as exc:
                last_exc = exc
                if len(hosts_to_try) > 1 and host == "postgres":
                    logger.warning(
                        "Could not connect to host 'postgres' (%s); attempting fallback to 'localhost'...",
                        exc,
                    )
                    continue

        logger.error("Failed to connect to PostgreSQL database: %s", last_exc)
        raise TapLoaderError(f"Database connection failed: {last_exc}") from last_exc

    def ensure_dataset_available(self) -> str:
        """Download and cache the dataset CSV if not already present."""
        if os.path.exists(self.cache_path) and os.path.getsize(self.cache_path) > 0:
            logger.info(
                "Found cached dataset at %s (%d bytes)",
                self.cache_path,
                os.path.getsize(self.cache_path),
            )
            return self.cache_path

        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        logger.info("Downloading historical simulated tap dataset from %s", self.dataset_url)

        try:
            response = requests.get(
                self.dataset_url,
                stream=True,
                timeout=60,
                headers={"User-Agent": "KoridorTJ-Loader/1.0"},
            )
            response.raise_for_status()
            with open(self.cache_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

            logger.info(
                "Dataset successfully downloaded and cached to %s (%d bytes)",
                self.cache_path,
                os.path.getsize(self.cache_path),
            )
            return self.cache_path
        except Exception as exc:
            logger.error("Failed to download dataset: %s", exc)
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
            raise TapLoaderError(f"Dataset download failed: {exc}") from exc

    def init_database_schema(self, conn: psycopg2.extensions.connection) -> None:
        """Ensure raw schema and raw.taps table exist."""
        logger.info("Ensuring PostgreSQL raw.taps table exists...")
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS raw.taps (
                    trans_id VARCHAR(100) PRIMARY KEY,
                    pay_card_id VARCHAR(100) NOT NULL,
                    pay_card_bank VARCHAR(100),
                    pay_card_name VARCHAR(255),
                    pay_card_sex VARCHAR(10),
                    pay_card_birth_date INT,
                    corridor_id VARCHAR(100),
                    corridor_name VARCHAR(255),
                    direction INT DEFAULT 0,
                    tap_in_stops VARCHAR(100),
                    tap_in_stops_name VARCHAR(255),
                    tap_in_stops_lat DOUBLE PRECISION,
                    tap_in_stops_lon DOUBLE PRECISION,
                    stop_start_seq INT,
                    tap_in_time TIMESTAMP,
                    tap_out_stops VARCHAR(100),
                    tap_out_stops_name VARCHAR(255),
                    tap_out_stops_lat DOUBLE PRECISION,
                    tap_out_stops_lon DOUBLE PRECISION,
                    stop_end_seq INT,
                    tap_out_time TIMESTAMP,
                    pay_amount NUMERIC(10, 2) DEFAULT 3500.00,
                    is_simulated BOOLEAN NOT NULL DEFAULT TRUE,
                    _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    _source_file TEXT
                );
            """)
            # Create indexes for commonly filtered attributes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_taps_card ON raw.taps (pay_card_id);")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_taps_corridor ON raw.taps (corridor_id);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_taps_tap_in_time ON raw.taps (tap_in_time);"
            )
            conn.commit()

    def load_records_batch(
        self,
        conn: psycopg2.extensions.connection,
        records: list[dict[str, Any]],
        columns: list[str],
        ingested_at: datetime,
        source_file: str,
    ) -> int:
        """Bulk upsert a batch of validated tap transaction records."""
        if not records:
            return 0

        full_columns = columns + ["is_simulated", "_ingested_at", "_source_file"]
        rows_to_insert = [
            tuple(r.get(c) for c in columns) + (True, ingested_at, source_file) for r in records
        ]

        query = f"""
            INSERT INTO raw.taps ({", ".join(full_columns)})
            VALUES %s
            ON CONFLICT (trans_id) DO UPDATE SET
                {", ".join(f"{c} = EXCLUDED.{c}" for c in columns[1:])},
                is_simulated = EXCLUDED.is_simulated,
                _ingested_at = EXCLUDED._ingested_at,
                _source_file = EXCLUDED._source_file;
        """

        with conn.cursor() as cur:
            execute_values(cur, query, rows_to_insert, page_size=1000)
            conn.commit()

        return len(records)

    def run(self, csv_file_path: str | None = None, batch_size: int = 5000) -> dict[str, Any]:
        """Execute the full tap transaction loading pipeline."""
        start_time = time.time()
        now_utc = datetime.now(UTC)
        logger.info("=== Starting TransJakarta Historical Tap Data Ingestion ===")

        target_file = csv_file_path or self.ensure_dataset_available()
        source_label = os.path.basename(target_file)

        conn = self.get_connection()
        try:
            self.init_database_schema(conn)

            columns = [
                "trans_id",
                "pay_card_id",
                "pay_card_bank",
                "pay_card_name",
                "pay_card_sex",
                "pay_card_birth_date",
                "corridor_id",
                "corridor_name",
                "direction",
                "tap_in_stops",
                "tap_in_stops_name",
                "tap_in_stops_lat",
                "tap_in_stops_lon",
                "stop_start_seq",
                "tap_in_time",
                "tap_out_stops",
                "tap_out_stops_name",
                "tap_out_stops_lat",
                "tap_out_stops_lon",
                "stop_end_seq",
                "tap_out_time",
                "pay_amount",
            ]

            total_valid = 0
            total_invalid = 0
            current_batch: list[dict[str, Any]] = []

            with open(target_file, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=1):
                    # Clean whitespace & map empty strings to None
                    cleaned = {
                        k.strip(): (v.strip() if v is not None and v.strip() != "" else None)
                        for k, v in row.items()
                        if k
                    }

                    try:
                        valid_model = RawTapTransaction.model_validate(cleaned)
                        current_batch.append(valid_model.model_dump())
                        total_valid += 1
                    except ValidationError as val_err:
                        total_invalid += 1
                        if total_invalid <= 5:
                            logger.warning(
                                "Validation error on row %d: %s (Row: %s)",
                                row_idx,
                                val_err.errors(),
                                cleaned,
                            )

                    if len(current_batch) >= batch_size:
                        inserted = self.load_records_batch(
                            conn, current_batch, columns, now_utc, source_label
                        )
                        logger.info(
                            "Loaded batch of %d records (Progress: %d total valid rows loaded)",
                            inserted,
                            total_valid,
                        )
                        current_batch = []

                # Final flush
                if current_batch:
                    inserted = self.load_records_batch(
                        conn, current_batch, columns, now_utc, source_label
                    )
                    logger.info("Loaded final batch of %d records", inserted)

        finally:
            conn.close()

        total_duration = time.time() - start_time
        summary = {
            "status": "SUCCESS",
            "ingested_at": now_utc.isoformat(),
            "duration_seconds": round(total_duration, 2),
            "total_valid_loaded": total_valid,
            "total_invalid": total_invalid,
            "source_file": source_label,
            "is_simulated": True,
        }

        logger.info("=== Tap Transaction Ingestion Completed in %.2fs ===", total_duration)
        logger.info("Summary: %s", summary)
        return summary


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="KoridorTJ Historical Tap Transaction Ingestion")
    parser.add_argument(
        "--csv-path",
        "-f",
        dest="csv_path",
        default=None,
        help="Path to the source TransJakarta tap CSV dataset",
    )
    parser.add_argument(
        "--db-host",
        default=None,
        help="PostgreSQL host (defaults to POSTGRES_HOST or localhost)",
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=None,
        help="PostgreSQL port (defaults to POSTGRES_PORT or 5432)",
    )
    parser.add_argument(
        "--db-name",
        default=None,
        help="PostgreSQL database name (defaults to POSTGRES_DB_WAREHOUSE or warehouse)",
    )
    parser.add_argument(
        "--db-user",
        default=None,
        help="PostgreSQL user (defaults to POSTGRES_INGESTION_USER or postgres)",
    )
    parser.add_argument(
        "--db-password",
        default=None,
        help="PostgreSQL password",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Batch size for bulk insertion (default: 5000)",
    )

    args = parser.parse_args()

    try:
        loader = TapLoader(
            db_host=args.db_host,
            db_port=args.db_port,
            db_name=args.db_name,
            db_user=args.db_user,
            db_password=args.db_password,
            cache_path=args.csv_path,
        )
        loader.run(csv_file_path=args.csv_path, batch_size=args.batch_size)
    except Exception as e:
        logger.critical("Tap data ingestion failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
