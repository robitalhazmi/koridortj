"""Unit tests for Tap transaction validation schemas."""

import pytest
from pydantic import ValidationError
from ingestion.schemas import RawTapTransaction


class TestTapSchemas:
    """Test suite for RawTapTransaction Pydantic model."""

    def test_valid_tap_transaction(self):
        data = {
            "transID": "EIIW227B8L34VB",
            "payCardID": "180062659848800",
            "payCardBank": "emoney",
            "payCardName": "Bajragin Usada",
            "payCardSex": "M",
            "payCardBirthDate": "2008",
            "corridorID": "5",
            "corridorName": "Matraman Baru - Ancol",
            "direction": "1.0",
            "tapInStops": "P00142",
            "tapInStopsName": "Pal Putih",
            "tapInStopsLat": "-6.184631",
            "tapInStopsLon": "106.84402",
            "stopStartSeq": "7",
            "tapInTime": "2023-04-03 05:21:44",
            "tapOutStops": "P00253",
            "tapOutStopsName": "Tegalan",
            "tapOutStopsLat": "-6.203101",
            "tapOutStopsLon": "106.85715",
            "stopEndSeq": "12.0",
            "tapOutTime": "2023-04-03 06:00:53",
            "payAmount": "3500.0",
        }
        tap = RawTapTransaction.model_validate(data)
        assert tap.trans_id == "EIIW227B8L34VB"
        assert tap.pay_card_id == "180062659848800"
        assert tap.direction == 1
        assert tap.stop_end_seq == 12
        assert tap.pay_card_birth_date == 2008
        assert tap.pay_amount == 3500.0

    def test_invalid_tap_missing_trans_id(self):
        data = {
            "transID": "  ",
            "payCardID": "180062659848800",
        }
        with pytest.raises(ValidationError):
            RawTapTransaction.model_validate(data)

    def test_invalid_tap_missing_card_id(self):
        data = {
            "transID": "VALID_TX_123",
            "payCardID": "",
        }
        with pytest.raises(ValidationError):
            RawTapTransaction.model_validate(data)
