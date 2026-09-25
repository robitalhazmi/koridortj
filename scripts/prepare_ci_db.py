#!/usr/bin/env python3
"""Database bootstrap and sample data loader for CI/CD test runners."""

import logging
import os
import sys

import psycopg2
from dotenv import load_dotenv

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.gtfs_ingest import GTFSIngestor
from ingestion.tap_loader import TapLoader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("prepare_ci_db")


def init_database_schemas(host: str, port: int, user: str, password: str, dbname: str):
    """Execute SQL initialization scripts."""
    logger.info("Initializing schemas and roles in database '%s' at %s:%s...", dbname, host, port)
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
    )
    conn.autocommit = True
    sql_path = os.path.join(os.path.dirname(__file__), "init_db.sql")

    with open(sql_path, encoding="utf-8") as f:
        sql_content = f.read()

    # If \c warehouse is present, extract all SQL following it
    if "\\c warehouse" in sql_content:
        clean_sql = sql_content.split("\\c warehouse", 1)[1]
    else:
        clean_sql = sql_content

    with conn.cursor() as cur:
        cur.execute(clean_sql)

    # Ensure streaming raw table exists
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO raw.taps_stream (
                trans_id, pay_card_id, pay_card_bank, pay_card_name, pay_card_sex,
                pay_card_birth_date, corridor_id, corridor_name, direction,
                tap_in_stops, tap_in_stops_name, tap_in_stops_lat, tap_in_stops_lon,
                stop_start_seq, tap_in_time, tap_out_stops, tap_out_stops_name,
                tap_out_stops_lat, tap_out_stops_lon, stop_end_seq, tap_out_time,
                pay_amount, is_simulated, _ingested_at, _source_topic
            ) VALUES (
                'CI_STREAM_001', 'CARD_CI_99', 'dki', 'CI Test User', 'M',
                1995, '1', 'Blok M - Kota', 0,
                'B00499P', 'Penjaringan', -6.1263, 106.7920,
                1, NOW() - INTERVAL '10 minutes', 'B04962P', 'Garuda Taman Mini',
                -6.2901, 106.8811, 15, NOW() - INTERVAL '2 minutes',
                3500.00, TRUE, NOW(), 'taps.raw'
            )
            ON CONFLICT (trans_id) DO UPDATE SET
                tap_in_stops = EXCLUDED.tap_in_stops,
                tap_out_stops = EXCLUDED.tap_out_stops;
        """)

    conn.close()
    logger.info("Database schemas, roles, and streaming seed initialized successfully.")


def main():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres_dev_password")
    dbname = os.getenv("POSTGRES_DB_WAREHOUSE", "warehouse")

    gtfs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "gtfs.zip")
    taps_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "transjakarta_taps.csv"
    )

    try:
        init_database_schemas(host, port, user, password, dbname)

        # Ingest GTFS
        logger.info("Ingesting GTFS reference data...")
        gtfs_ingestor = GTFSIngestor(
            db_host=host,
            db_port=port,
            db_name=dbname,
            db_user=user,
            db_password=password,
        )
        gtfs_ingestor.run(local_zip_path=gtfs_path if os.path.exists(gtfs_path) else None)

        # Ingest Taps
        logger.info("Ingesting Historical Tap data...")
        tap_loader = TapLoader(
            db_host=host,
            db_port=port,
            db_name=dbname,
            db_user=user,
            db_password=password,
        )
        tap_loader.run(
            csv_file_path=taps_path if os.path.exists(taps_path) else None,
            batch_size=5000,
        )

        logger.info("=== CI Database Preparation Completed Successfully ===")

    except Exception as e:
        logger.critical("Failed to prepare CI database: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
