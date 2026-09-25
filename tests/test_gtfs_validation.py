"""Unit tests for GTFS validation and Pydantic schema models."""

import pytest
from pydantic import ValidationError

from ingestion.schemas import GTFSCalendar, GTFSRoute, GTFSStop, GTFSTrip


class TestGTFSSchemas:
    """Test suite for GTFS Pydantic models."""

    def test_valid_route(self):
        data = {
            "route_id": "1",
            "agency_id": "Tije",
            "route_short_name": "1",
            "route_long_name": "Blok M - Kota",
            "route_desc": "BRT",
            "route_type": 3,
            "route_color": "D81B60",
            "route_text_color": "FFFFFF",
        }
        route = GTFSRoute.model_validate(data)
        assert route.route_id == "1"
        assert route.route_short_name == "1"
        assert route.route_type == 3

    def test_invalid_route_empty_id(self):
        data = {"route_id": "  ", "route_type": 3}
        with pytest.raises(ValidationError):
            GTFSRoute.model_validate(data)

    def test_valid_stop(self):
        data = {
            "stop_id": "B00001P",
            "stop_name": "18 Office Park",
            "stop_lat": -6.299146,
            "stop_lon": 106.8321,
            "location_type": 0,
            "wheelchair_boarding": 2,
        }
        stop = GTFSStop.model_validate(data)
        assert stop.stop_id == "B00001P"
        assert stop.stop_lat == -6.299146
        assert stop.stop_lon == 106.8321

    def test_invalid_stop_out_of_bounds_lat(self):
        data = {
            "stop_id": "B00001P",
            "stop_name": "Invalid Location",
            "stop_lat": -45.0,  # Outside Indonesia/Jakarta bounds
            "stop_lon": 106.8321,
        }
        with pytest.raises(ValidationError):
            GTFSStop.model_validate(data)

    def test_valid_trip(self):
        data = {
            "trip_id": "9-P23",
            "route_id": "9",
            "service_id": "SH",
            "trip_headsign": "Pinang Ranti",
            "direction_id": 0,
            "shape_id": "9-P23_shp",
        }
        trip = GTFSTrip.model_validate(data)
        assert trip.trip_id == "9-P23"
        assert trip.route_id == "9"
        assert trip.service_id == "SH"

    def test_valid_calendar(self):
        data = {
            "service_id": "HK",
            "monday": 1,
            "tuesday": 1,
            "wednesday": 1,
            "thursday": 1,
            "friday": 1,
            "saturday": 0,
            "sunday": 0,
            "start_date": "20260101",
            "end_date": "20261231",
        }
        cal = GTFSCalendar.model_validate(data)
        assert cal.service_id == "HK"
        assert cal.monday == 1
        assert cal.sunday == 0

    def test_invalid_calendar_bad_date(self):
        data = {
            "service_id": "HK",
            "monday": 1,
            "tuesday": 1,
            "wednesday": 1,
            "thursday": 1,
            "friday": 1,
            "saturday": 0,
            "sunday": 0,
            "start_date": "2026-01-01",  # Invalid format (should be YYYYMMDD)
            "end_date": "20261231",
        }
        with pytest.raises(ValidationError):
            GTFSCalendar.model_validate(data)
