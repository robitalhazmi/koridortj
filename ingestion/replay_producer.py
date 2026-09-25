#!/usr/bin/env python3
"""Kafka Replay Producer for KoridorTJ.

Reads historical TransJakarta tap transaction records, shifts timestamps to match
real-time wall clock according to a configurable speed multiplier, and streams
serialized JSON events to the Kafka topic `taps.raw`.
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

import requests
from dotenv import load_dotenv
from kafka import KafkaProducer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("replay_producer")

DEFAULT_KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
DEFAULT_TOPIC = os.getenv("KAFKA_TOPIC_RAW", "taps.raw")
DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "transjakarta_taps.csv"
)
DEFAULT_CSV_URL = (
    "https://raw.githubusercontent.com/rahmadits/capstone2_transjakarta/master/Transjakarta.csv"
)


def parse_timestamp(ts_str: str | None) -> datetime | None:
    """Parse timestamp string in standard formats."""
    if not ts_str or not ts_str.strip():
        return None
    cleaned = ts_str.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def format_timestamp(dt: datetime | None) -> str | None:
    """Format datetime to ISO 8601 string."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class TapReplayProducer:
    """Producer that replays historical tap events into Kafka at a specified speed multiplier."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str = DEFAULT_TOPIC,
        csv_path: str = DEFAULT_CSV_PATH,
        speed_multiplier: float = 60.0,
        max_events: int | None = None,
        loop: bool = False,
    ):
        self.bootstrap_servers = bootstrap_servers or DEFAULT_KAFKA_SERVERS
        self.topic = topic
        self.csv_path = csv_path
        self.speed_multiplier = max(0.01, float(speed_multiplier))
        self.max_events = max_events
        self.loop = loop
        self._producer: KafkaProducer | None = None

    def get_producer(self) -> KafkaProducer:
        """Create and return a KafkaProducer client with retries and JSON serializer."""
        if self._producer is None:
            logger.info("Initializing KafkaProducer targeting %s...", self.bootstrap_servers)
            retries = 5
            for attempt in range(1, retries + 1):
                try:
                    self._producer = KafkaProducer(
                        bootstrap_servers=self.bootstrap_servers.split(","),
                        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                        key_serializer=lambda k: k.encode("utf-8") if k else None,
                        acks=1,
                        linger_ms=10,
                        retries=3,
                    )
                    logger.info("Connected to Kafka broker at %s", self.bootstrap_servers)
                    break
                except Exception as exc:
                    logger.warning(
                        "Attempt %d/%d to connect to Kafka failed: %s", attempt, retries, exc
                    )
                    if attempt == retries:
                        raise
                    time.sleep(2)
        return self._producer

    def ensure_dataset_available(self) -> str:
        """Download and cache the dataset CSV if not already present."""
        if os.path.exists(self.csv_path) and os.path.getsize(self.csv_path) > 0:
            return self.csv_path

        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        logger.info("Downloading historical simulated tap dataset from %s...", DEFAULT_CSV_URL)
        try:
            res = requests.get(DEFAULT_CSV_URL, timeout=60)
            res.raise_for_status()
            with open(self.csv_path, "wb") as f:
                f.write(res.content)
            logger.info("Dataset downloaded successfully to %s", self.csv_path)
            return self.csv_path
        except Exception as exc:
            logger.error("Failed to download dataset: %s", exc)
            raise FileNotFoundError(f"Source dataset not found and download failed: {exc}") from exc

    def load_events(self) -> list[dict[str, Any]]:
        """Load and sort transactions from CSV by tapInTime."""
        self.ensure_dataset_available()

        logger.info("Loading transaction dataset from %s...", self.csv_path)
        events = []
        with open(self.csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cleaned = {
                    k.strip(): (v.strip() if v is not None and v.strip() != "" else None)
                    for k, v in row.items()
                    if k
                }
                events.append(cleaned)

        # Sort chronologically by tapInTime where present
        def sort_key(item: dict[str, Any]) -> str:
            return item.get("tapInTime") or ""

        events.sort(key=sort_key)
        logger.info("Loaded and sorted %d historical events.", len(events))
        return events

    def run(self) -> dict[str, Any]:
        """Execute the replay streaming loop."""
        events = self.load_events()
        if not events:
            logger.warning("No events to replay.")
            return {"status": "EMPTY", "events_published": 0}

        producer = self.get_producer()
        total_published = 0
        iteration = 0

        logger.info(
            "=== Starting Tap Replay Producer (Speed Multiplier: %.1fx, Topic: '%s') ===",
            self.speed_multiplier,
            self.topic,
        )

        start_wall_time = time.time()

        while True:
            iteration += 1
            logger.info("Starting replay pass %d (%d events in queue)", iteration, len(events))

            # Reference timestamps from the dataset
            first_event_dt: datetime | None = None
            for e in events:
                dt = parse_timestamp(e.get("tapInTime"))
                if dt:
                    first_event_dt = dt
                    break

            pass_start_wall_time = time.time()
            pass_start_wall_dt = datetime.now(UTC)

            for _idx, raw_event in enumerate(events, start=1):
                if self.max_events and total_published >= self.max_events:
                    logger.info("Reached maximum events threshold (%d). Exiting.", self.max_events)
                    break

                # Clone event dict to prevent mutating source list
                event = dict(raw_event)

                # Recompute timestamps relative to current wall clock
                orig_tap_in = parse_timestamp(event.get("tapInTime"))
                orig_tap_out = parse_timestamp(event.get("tapOutTime"))

                if orig_tap_in and first_event_dt:
                    hist_delta_seconds = (orig_tap_in - first_event_dt).total_seconds()
                    scaled_simulated_seconds = hist_delta_seconds / self.speed_multiplier

                    # Pacing sleep to match simulated speed
                    expected_elapsed_wall = scaled_simulated_seconds
                    actual_elapsed_wall = time.time() - pass_start_wall_time
                    time_to_wait = expected_elapsed_wall - actual_elapsed_wall

                    if time_to_wait > 0.001:
                        time.sleep(min(time_to_wait, 1.0))

                    # Calculate current simulated timestamp (never in the future)
                    sim_event_ts = pass_start_wall_dt.timestamp() + scaled_simulated_seconds
                    sim_event_dt = datetime.fromtimestamp(sim_event_ts, tz=UTC)

                    if orig_tap_out:
                        trip_duration = max(0.0, (orig_tap_out - orig_tap_in).total_seconds())
                        sim_tap_out_dt = sim_event_dt
                        sim_tap_in_dt = datetime.fromtimestamp(sim_event_ts - trip_duration, tz=UTC)
                        event["tapInTime"] = format_timestamp(sim_tap_in_dt)
                        event["tapOutTime"] = format_timestamp(sim_tap_out_dt)
                    else:
                        event["tapInTime"] = format_timestamp(sim_event_dt)
                        event["tapOutTime"] = None
                else:
                    now_dt = datetime.now(UTC)
                    event["tapInTime"] = format_timestamp(now_dt)
                    if event.get("tapOutTime"):
                        event["tapOutTime"] = format_timestamp(now_dt)

                # Ensure simulated marker
                event["is_simulated"] = True
                event["_replay_speed"] = self.speed_multiplier
                event["_streamed_at"] = datetime.now(UTC).isoformat()

                trans_id = event.get("transID") or f"trans_{total_published + 1}"

                # Publish to Kafka
                producer.send(
                    topic=self.topic,
                    key=trans_id,
                    value=event,
                )
                total_published += 1

                if total_published % 500 == 0:
                    producer.flush()
                    elapsed = time.time() - start_wall_time
                    rate = total_published / max(elapsed, 0.001)
                    logger.info(
                        "Published %d events (Throughput: %.1f events/sec)", total_published, rate
                    )

            producer.flush()

            if not self.loop or (self.max_events and total_published >= self.max_events):
                break

        total_duration = time.time() - start_wall_time
        summary = {
            "status": "SUCCESS",
            "topic": self.topic,
            "speed_multiplier": self.speed_multiplier,
            "events_published": total_published,
            "duration_seconds": round(total_duration, 2),
            "events_per_second": round(total_published / max(total_duration, 0.001), 1),
        }
        logger.info("=== Replay Stream Finished ===")
        logger.info("Summary: %s", summary)
        return summary


def main():
    """CLI argument parser and entry point."""
    parser = argparse.ArgumentParser(description="KoridorTJ Kafka Tap Replay Producer")
    parser.add_argument(
        "--bootstrap-servers",
        default=DEFAULT_KAFKA_SERVERS,
        help=f"Kafka bootstrap servers (default: {DEFAULT_KAFKA_SERVERS})",
    )
    parser.add_argument(
        "--topic",
        default=DEFAULT_TOPIC,
        help=f"Kafka topic to publish to (default: {DEFAULT_TOPIC})",
    )
    parser.add_argument(
        "--csv-path",
        default=DEFAULT_CSV_PATH,
        help=f"Path to transjakarta taps CSV (default: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--speed-multiplier",
        type=float,
        default=60.0,
        help="Replay speed multiplier (e.g. 60.0 = 1 hr in 1 min; 0 = max throughput)",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Maximum events to publish before exiting (default: all)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Continuously replay dataset in an infinite loop",
    )

    args = parser.parse_args()

    producer = TapReplayProducer(
        bootstrap_servers=args.bootstrap_servers,
        topic=args.topic,
        csv_path=args.csv_path,
        speed_multiplier=args.speed_multiplier,
        max_events=args.max_events,
        loop=args.loop,
    )
    try:
        producer.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting cleanly.")
    except Exception as exc:
        logger.critical("Replay producer failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
