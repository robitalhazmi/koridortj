"""Airflow DAG: Weekly TransJakarta GTFS Reference Data Ingestion.

Downloads the official GTFS zip, validates its structure and schemas, and loads routes,
stops, trips, and calendars into PostgreSQL raw tables idempotently.
"""

import logging
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger("airflow.task")


def check_feed_availability():
    """Verify that the official TransJakarta GTFS feed endpoint is responsive."""
    from ingestion.gtfs_ingest import DEFAULT_GTFS_URL

    logger.info("Checking availability for GTFS endpoint: %s", DEFAULT_GTFS_URL)
    response = requests.head(
        DEFAULT_GTFS_URL, timeout=30, headers={"User-Agent": "Airflow-HealthCheck/1.0"}
    )
    if response.status_code not in (200, 302, 307):
        # Retry with GET in case HEAD is not allowed
        response = requests.get(
            DEFAULT_GTFS_URL,
            stream=True,
            timeout=30,
            headers={"User-Agent": "Airflow-HealthCheck/1.0"},
        )
    response.raise_for_status()
    logger.info("GTFS feed endpoint is reachable (HTTP %d)", response.status_code)
    return True


def execute_gtfs_ingestion():
    """Run the GTFSIngestor pipeline to parse and load reference data."""
    from ingestion.gtfs_ingest import GTFSIngestor

    ingestor = GTFSIngestor()
    summary = ingestor.run()
    logger.info("Ingestion completed with summary: %s", summary)
    return summary


def verify_ingested_row_counts():
    """Verify that raw tables have been populated and log current table metrics."""
    from ingestion.gtfs_ingest import GTFSIngestor

    ingestor = GTFSIngestor()
    conn = ingestor.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 'raw.gtfs_routes' as tbl, count(*) FROM raw.gtfs_routes
                UNION ALL
                SELECT 'raw.gtfs_stops', count(*) FROM raw.gtfs_stops
                UNION ALL
                SELECT 'raw.gtfs_trips', count(*) FROM raw.gtfs_trips
                UNION ALL
                SELECT 'raw.gtfs_calendar', count(*) FROM raw.gtfs_calendar;
            """)
            counts = dict(cur.fetchall())
            logger.info("Verified PostgreSQL raw GTFS row counts: %s", counts)

            # Ensure minimum expected thresholds are met
            assert counts.get("raw.gtfs_routes", 0) > 0, "No routes loaded!"
            assert counts.get("raw.gtfs_stops", 0) > 0, "No stops loaded!"
            assert counts.get("raw.gtfs_trips", 0) > 0, "No trips loaded!"
            assert counts.get("raw.gtfs_calendar", 0) > 0, "No calendars loaded!"
    finally:
        conn.close()


default_args = {
    "owner": "koridortj",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="gtfs_ingest",
    default_args=default_args,
    description="Weekly automated ingestion of TransJakarta GTFS reference data",
    schedule_interval="0 3 * * 1",  # Weekly on Monday at 03:00 UTC
    start_date=datetime(2023, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["transjakarta", "gtfs", "ingestion", "reference_data"],
) as dag:
    task_check_availability = PythonOperator(
        task_id="check_feed_availability",
        python_callable=check_feed_availability,
    )

    task_ingest = PythonOperator(
        task_id="ingest_gtfs_data",
        python_callable=execute_gtfs_ingestion,
    )

    task_verify = PythonOperator(
        task_id="verify_row_counts",
        python_callable=verify_ingested_row_counts,
    )

    task_check_availability >> task_ingest >> task_verify
