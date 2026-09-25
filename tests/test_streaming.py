"""Unit tests for Kafka streaming components, replay producer, and consumer schemas."""

import json
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from ingestion.schemas import DeadLetterEvent, StreamingTapEvent
from ingestion.replay_producer import format_timestamp, parse_timestamp


class TestStreamingSchemas:
    """Test suite for streaming Pydantic models."""

    def test_valid_streaming_tap_event(self):
        data = {
            "transID": "STREAM_TX_001",
            "payCardID": "CARD_999",
            "payCardBank": "flazz",
            "payCardName": "Test Passenger",
            "payCardSex": "F",
            "payCardBirthDate": 1995,
            "corridorID": "1",
            "corridorName": "Blok M - Kota",
            "direction": 0,
            "tapInStops": "1-1",
            "tapInStopsName": "Blok M",
            "tapInStopsLat": -6.24434,
            "tapInStopsLon": 106.79799,
            "stopStartSeq": 1,
            "tapInTime": "2026-09-25 10:00:00",
            "tapOutStops": "1-22",
            "tapOutStopsName": "Kota",
            "tapOutStopsLat": -6.13764,
            "tapOutStopsLon": 106.81462,
            "stopEndSeq": 22,
            "tapOutTime": "2026-09-25 10:45:00",
            "payAmount": 3500.0,
        }
        event = StreamingTapEvent.model_validate(data)
        assert event.trans_id == "STREAM_TX_001"
        assert event.pay_card_id == "CARD_999"
        assert event.is_simulated is True
        assert event.direction == 0
        assert event.pay_amount == 3500.0

    def test_invalid_streaming_tap_event(self):
        data = {
            "transID": "",
            "payCardID": "CARD_999",
        }
        with pytest.raises(ValidationError):
            StreamingTapEvent.model_validate(data)

    def test_dead_letter_event_creation(self):
        dlq = DeadLetterEvent(
            original_payload={"bad_key": "bad_value"},
            error_message="Missing required field transID",
            error_type="ValidationError",
            failed_at="2026-09-25T10:00:00Z",
            source_topic="taps.raw",
        )
        assert dlq.error_type == "ValidationError"
        assert dlq.source_topic == "taps.raw"
        assert "bad_key" in dlq.original_payload
        dump = dlq.model_dump()
        assert dump["error_message"] == "Missing required field transID"


class TestReplayProducerLogic:
    """Test suite for timestamp shifting and parsing logic."""

    def test_parse_and_format_timestamp(self):
        ts_str = "2023-04-03 05:21:44"
        dt = parse_timestamp(ts_str)
        assert dt is not None
        assert dt.year == 2023
        assert dt.month == 4
        assert dt.day == 3
        assert dt.hour == 5
        assert dt.minute == 21
        assert dt.second == 44

        formatted = format_timestamp(dt)
        assert formatted == ts_str

    def test_timestamp_scaling_math(self):
        speed_multiplier = 60.0
        t0 = parse_timestamp("2023-04-03 05:00:00")
        t1 = parse_timestamp("2023-04-03 06:00:00")
        assert t0 and t1

        hist_delta_seconds = (t1 - t0).total_seconds()
        assert hist_delta_seconds == 3600.0

        scaled_seconds = hist_delta_seconds / speed_multiplier
        assert scaled_seconds == 60.0  # 1 hour condensed into 60 seconds
