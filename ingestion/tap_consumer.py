#!/usr/bin/env python3
"""Kafka Streaming Tap Consumer for KoridorTJ.

Consumes real-time passenger tap transactions from Kafka topic `taps.raw`,
validates each event against Pydantic schema `StreamingTapEvent`, lands valid records
into PostgreSQL `raw.taps_stream`, and routes malformed records to Dead-Letter Queue (DLQ)
topic `taps.deadletter`.
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import execute_values
from pydantic import ValidationError
from dotenv import load_dotenv
from kafka import KafkaConsumer, KafkaProducer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("tap_consumer")

try:
    from ingestion.schemas import DeadLetterEvent, StreamingTapEvent
except ImportError:
    from schemas import DeadLetterEvent, StreamingTapEvent

DEFAULT_KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
DEFAULT_RAW_TOPIC = os.getenv("KAFKA_TOPIC_RAW", "taps.raw")
DEFAULT_DLQ_TOPIC = os.getenv("KAFKA_TOPIC_DLQ", "taps.deadletter")
DEFAULT_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "koridortj-tap-consumer")


class TapStreamConsumer:
    """Consumes, validates, and loads streaming tap transactions into PostgreSQL with DLQ routing."""

    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        raw_topic: str = DEFAULT_RAW_TOPIC,
        dlq_topic: str = DEFAULT_DLQ_TOPIC,
        group_id: str = DEFAULT_GROUP_ID,
        batch_size: int = 500,
        flush_interval_seconds: float = 2.0,
        max_messages: Optional[int] = None,
        db_host: Optional[str] = None,
        db_port: Optional[int] = None,
        db_name: Optional[str] = None,
        db_user: Optional[str] = None,
        db_password: Optional[str] = None,
    ):
        self.bootstrap_servers = bootstrap_servers or DEFAULT_KAFKA_SERVERS
        self.raw_topic = raw_topic
        self.dlq_topic = dlq_topic
        self.group_id = group_id
        self.batch_size = max(1, batch_size)
        self.flush_interval = flush_interval_seconds
        self.max_messages = max_messages

        self.db_host = db_host or os.getenv("POSTGRES_HOST", "localhost")
        self.db_port = int(db_port or os.getenv("POSTGRES_PORT", 5432))
        self.db_name = db_name or os.getenv("POSTGRES_DB_WAREHOUSE", os.getenv("POSTGRES_DB", "warehouse"))
        self.db_user = db_user or os.getenv("POSTGRES_INGESTION_USER", os.getenv("POSTGRES_USER", "postgres"))
        self.db_password = db_password or os.getenv("POSTGRES_INGESTION_PASSWORD", os.getenv("POSTGRES_PASSWORD", "postgres_dev_password"))

        self.running = True
        self._consumer: Optional[KafkaConsumer] = None
        self._dlq_producer: Optional[KafkaProducer] = None
        self._db_conn: Optional[psycopg2.extensions.connection] = None

    def get_db_connection(self) -> psycopg2.extensions.connection:
        """Establish connection to PostgreSQL warehouse."""
        if self._db_conn is None or self._db_conn.closed:
            logger.info("Connecting to PostgreSQL at %s:%s/%s as %s", self.db_host, self.db_port, self.db_name, self.db_user)
            self._db_conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password,
                connect_timeout=10,
            )
            self._db_conn.autocommit = False
        return self._db_conn

    def get_consumer(self) -> KafkaConsumer:
        """Create and return configured KafkaConsumer."""
        if self._consumer is None:
            logger.info("Initializing KafkaConsumer for topic '%s' (group: '%s')...", self.raw_topic, self.group_id)
            self._consumer = KafkaConsumer(
                self.raw_topic,
                bootstrap_servers=self.bootstrap_servers.split(","),
                group_id=self.group_id,
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                consumer_timeout_ms=1000,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            )
        return self._consumer

    def get_dlq_producer(self) -> KafkaProducer:
        """Create and return KafkaProducer for dead-letter routing."""
        if self._dlq_producer is None:
            self._dlq_producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers.split(","),
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks=1,
            )
        return self._dlq_producer

    def route_to_dlq(self, payload: Any, error_msg: str, error_type: str) -> None:
        """Send a failed message to the Dead-Letter Queue topic."""
        dlq_producer = self.get_dlq_producer()
        dlq_event = DeadLetterEvent(
            original_payload=payload,
            error_message=error_msg,
            error_type=error_type,
            failed_at=datetime.now(timezone.utc).isoformat(),
            source_topic=self.raw_topic,
        )
        dlq_producer.send(
            topic=self.dlq_topic,
            key=str(payload.get("transID", "unknown") if isinstance(payload, dict) else "unknown"),
            value=dlq_event.model_dump(),
        )
        dlq_producer.flush()
        logger.warning("Message routed to DLQ [%s]: %s", self.dlq_topic, error_msg)

    def flush_batch(self, batch: List[Dict[str, Any]]) -> int:
        """Bulk upsert validated streaming records into raw.taps_stream."""
        if not batch:
            return 0

        columns = [
            "trans_id", "pay_card_id", "pay_card_bank", "pay_card_name",
            "pay_card_sex", "pay_card_birth_date", "corridor_id", "corridor_name",
            "direction", "tap_in_stops", "tap_in_stops_name", "tap_in_stops_lat",
            "tap_in_stops_lon", "stop_start_seq", "tap_in_time", "tap_out_stops",
            "tap_out_stops_name", "tap_out_stops_lat", "tap_out_stops_lon",
            "stop_end_seq", "tap_out_time", "pay_amount"
        ]
        full_columns = columns + ["is_simulated", "_ingested_at", "_source_topic"]

        now_utc = datetime.now(timezone.utc)
        rows_to_insert = [
            tuple(r.get(c) for c in columns) + (True, now_utc, self.raw_topic)
            for r in batch
        ]

        query = f"""
            INSERT INTO raw.taps_stream ({', '.join(full_columns)})
            VALUES %s
            ON CONFLICT (trans_id) DO UPDATE SET
                {', '.join(f"{c} = EXCLUDED.{c}" for c in columns[1:])},
                is_simulated = EXCLUDED.is_simulated,
                _ingested_at = EXCLUDED._ingested_at,
                _source_topic = EXCLUDED._source_topic;
        """

        conn = self.get_db_connection()
        with conn.cursor() as cur:
            execute_values(cur, query, rows_to_insert, page_size=1000)
            conn.commit()

        return len(batch)

    def run(self) -> Dict[str, Any]:
        """Execute the streaming consumer loop."""
        consumer = self.get_consumer()
        logger.info("=== Starting Tap Stream Consumer on '%s' ===", self.raw_topic)

        current_batch: List[Dict[str, Any]] = []
        last_flush_time = time.time()
        total_processed = 0
        total_valid = 0
        total_dlq = 0

        start_time = time.time()

        try:
            while self.running:
                msg_pack = consumer.poll(timeout_ms=1000, max_records=self.batch_size)

                for tp, messages in msg_pack.items():
                    for msg in messages:
                        total_processed += 1
                        raw_data = msg.value

                        try:
                            valid_event = StreamingTapEvent.model_validate(raw_data)
                            current_batch.append(valid_event.model_dump())
                            total_valid += 1
                        except ValidationError as err:
                            total_dlq += 1
                            self.route_to_dlq(raw_data, str(err), "ValidationError")
                        except Exception as unk_err:
                            total_dlq += 1
                            self.route_to_dlq(raw_data, str(unk_err), unk_err.__class__.__name__)

                # Check if batch ready to flush (by size or time)
                time_since_flush = time.time() - last_flush_time
                if current_batch and (len(current_batch) >= self.batch_size or time_since_flush >= self.flush_interval):
                    flushed_count = self.flush_batch(current_batch)
                    consumer.commit()
                    logger.info(
                        "Committed %d records to raw.taps_stream (Total Valid: %d, DLQ: %d)",
                        flushed_count,
                        total_valid,
                        total_dlq,
                    )
                    current_batch = []
                    last_flush_time = time.time()

                if self.max_messages and total_processed >= self.max_messages:
                    logger.info("Processed max requested messages (%d). Flushing and stopping.", self.max_messages)
                    break

            # Final flush before stopping
            if current_batch:
                flushed_count = self.flush_batch(current_batch)
                consumer.commit()
                logger.info("Flushed final batch of %d records.", flushed_count)

        finally:
            if self._db_conn and not self._db_conn.closed:
                self._db_conn.close()
            if self._consumer:
                self._consumer.close()
            if self._dlq_producer:
                self._dlq_producer.close()

        total_duration = time.time() - start_time
        summary = {
            "status": "SUCCESS",
            "total_processed": total_processed,
            "total_valid": total_valid,
            "total_dlq": total_dlq,
            "duration_seconds": round(total_duration, 2),
        }
        logger.info("=== Tap Stream Consumer Stopped ===")
        logger.info("Summary: %s", summary)
        return summary


def main():
    """CLI argument parser and entry point."""
    parser = argparse.ArgumentParser(description="KoridorTJ Kafka Tap Stream Consumer")
    parser.add_argument(
        "--bootstrap-servers",
        default=DEFAULT_KAFKA_SERVERS,
        help=f"Kafka bootstrap servers (default: {DEFAULT_KAFKA_SERVERS})",
    )
    parser.add_argument(
        "--topic",
        default=DEFAULT_RAW_TOPIC,
        help=f"Kafka topic to consume from (default: {DEFAULT_RAW_TOPIC})",
    )
    parser.add_argument(
        "--dlq-topic",
        default=DEFAULT_DLQ_TOPIC,
        help=f"Kafka dead-letter topic (default: {DEFAULT_DLQ_TOPIC})",
    )
    parser.add_argument(
        "--group-id",
        default=DEFAULT_GROUP_ID,
        help=f"Consumer group ID (default: {DEFAULT_GROUP_ID})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for bulk database insert (default: 500)",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Max messages to consume before exiting (default: infinite loop)",
    )

    args = parser.parse_args()

    consumer = TapStreamConsumer(
        bootstrap_servers=args.bootstrap_servers,
        raw_topic=args.topic,
        dlq_topic=args.dlq_topic,
        group_id=args.group_id,
        batch_size=args.batch_size,
        max_messages=args.max_messages,
    )

    def handle_signal(sig, frame):
        logger.info("Received signal %s. Shutting down gracefully...", sig)
        consumer.running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        consumer.run()
    except Exception as exc:
        logger.critical("Tap stream consumer crashed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
