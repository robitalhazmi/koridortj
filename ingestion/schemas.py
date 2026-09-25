"""Pydantic schemas and validation models for KoridorTJ data ingestion."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class GTFSRoute(BaseModel):
    """Pydantic model representing a record from routes.txt."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    route_id: str = Field(..., description="Unique route identifier")
    agency_id: Optional[str] = Field(None, description="Agency identifier")
    route_short_name: Optional[str] = Field(None, description="Short public route name/code (e.g. 1, 8K)")
    route_long_name: Optional[str] = Field(None, description="Full descriptive route name")
    route_desc: Optional[str] = Field(None, description="Route category description (e.g. BRT, Bus Wisata)")
    route_type: int = Field(3, description="GTFS route type (3 = Bus)")
    route_url: Optional[str] = Field(None, description="URL for route information")
    route_color: Optional[str] = Field(None, description="Hex color code for the route")
    route_text_color: Optional[str] = Field(None, description="Hex color code for text on route color")
    route_sort_order: Optional[int] = Field(0, description="Display order ranking")
    ticketing_deep_link_id: Optional[str] = Field(None, description="Ticketing deep link identifier")

    @field_validator("route_id")
    @classmethod
    def validate_route_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("route_id cannot be empty")
        return v.strip()


class GTFSStop(BaseModel):
    """Pydantic model representing a record from stops.txt."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    stop_id: str = Field(..., description="Unique stop/shelter identifier")
    stop_code: Optional[str] = Field(None, description="Public stop code")
    stop_name: str = Field(..., description="Name of the stop/shelter")
    stop_desc: Optional[str] = Field(None, description="Description of the stop")
    stop_lat: float = Field(..., description="Latitude coordinate")
    stop_lon: float = Field(..., description="Longitude coordinate")
    zone_id: Optional[str] = Field(None, description="Fare zone identifier")
    stop_url: Optional[str] = Field(None, description="URL for stop details")
    location_type: Optional[int] = Field(0, description="0 = Stop/Platform, 1 = Station")
    parent_station: Optional[str] = Field(None, description="Parent station ID if nested")
    stop_timezone: Optional[str] = Field(None, description="Timezone of the stop")
    wheelchair_boarding: Optional[int] = Field(0, description="Accessibility indicator")
    platform_code: Optional[str] = Field(None, description="Platform identifier")

    @field_validator("stop_id", "stop_name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @field_validator("stop_lat")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        # Jakarta metropolitan bounding latitude roughly [-7.5, -5.0]
        if not (-10.0 <= v <= 10.0):
            raise ValueError(f"Latitude {v} is outside acceptable range")
        return v

    @field_validator("stop_lon")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        # Jakarta metropolitan bounding longitude roughly [105.5, 108.0]
        if not (90.0 <= v <= 145.0):
            raise ValueError(f"Longitude {v} is outside acceptable range")
        return v


class GTFSTrip(BaseModel):
    """Pydantic model representing a record from trips.txt."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    trip_id: str = Field(..., description="Unique trip identifier")
    route_id: str = Field(..., description="Associated route identifier")
    service_id: str = Field(..., description="Associated calendar service identifier")
    trip_headsign: Optional[str] = Field(None, description="Destination displayed to passengers")
    trip_short_name: Optional[str] = Field(None, description="Short trip label")
    direction_id: Optional[int] = Field(0, description="0 = Outbound, 1 = Inbound")
    block_id: Optional[str] = Field(None, description="Block identifier")
    shape_id: Optional[str] = Field(None, description="Associated shape polyline identifier")
    wheelchair_accessible: Optional[int] = Field(0, description="Wheelchair accessibility flag")
    bikes_allowed: Optional[int] = Field(0, description="Bikes allowed flag")
    ticketing_trip_id: Optional[str] = Field(None, description="Ticketing identifier")
    ticketing_type: Optional[int] = Field(0, description="Ticketing category code")

    @field_validator("trip_id", "route_id", "service_id")
    @classmethod
    def validate_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Trip identifiers cannot be empty")
        return v.strip()


class GTFSCalendar(BaseModel):
    """Pydantic model representing a record from calendar.txt."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    service_id: str = Field(..., description="Unique service schedule identifier")
    monday: int = Field(..., ge=0, le=1)
    tuesday: int = Field(..., ge=0, le=1)
    wednesday: int = Field(..., ge=0, le=1)
    thursday: int = Field(..., ge=0, le=1)
    friday: int = Field(..., ge=0, le=1)
    saturday: int = Field(..., ge=0, le=1)
    sunday: int = Field(..., ge=0, le=1)
    start_date: str = Field(..., min_length=8, max_length=8, description="Start date in YYYYMMDD format")
    end_date: str = Field(..., min_length=8, max_length=8, description="End date in YYYYMMDD format")

    @field_validator("service_id")
    @classmethod
    def validate_service_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("service_id cannot be empty")
        return v.strip()

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y%m%d")
        except ValueError:
            raise ValueError(f"Date string '{v}' must be in valid YYYYMMDD format")
        return v


class RawTapTransaction(BaseModel):
    """Pydantic model representing a raw simulated tap transaction record."""

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    trans_id: str = Field(..., alias="transID", description="Unique transaction ID")
    pay_card_id: str = Field(..., alias="payCardID", description="Customer payment card identifier")
    pay_card_bank: Optional[str] = Field(None, alias="payCardBank", description="Bank issuing payment card")
    pay_card_name: Optional[str] = Field(None, alias="payCardName", description="Passenger name on card")
    pay_card_sex: Optional[str] = Field(None, alias="payCardSex", description="Passenger gender (M/F)")
    pay_card_birth_date: Optional[int] = Field(None, alias="payCardBirthDate", description="Birth year")
    corridor_id: Optional[str] = Field(None, alias="corridorID", description="Corridor / Route identifier")
    corridor_name: Optional[str] = Field(None, alias="corridorName", description="Corridor descriptive name")
    direction: Optional[int] = Field(0, alias="direction", description="0 = Outbound, 1 = Inbound")
    tap_in_stops: Optional[str] = Field(None, alias="tapInStops", description="Stop ID for tap-in")
    tap_in_stops_name: Optional[str] = Field(None, alias="tapInStopsName", description="Stop name for tap-in")
    tap_in_stops_lat: Optional[float] = Field(None, alias="tapInStopsLat", description="Tap-in latitude")
    tap_in_stops_lon: Optional[float] = Field(None, alias="tapInStopsLon", description="Tap-in longitude")
    stop_start_seq: Optional[int] = Field(None, alias="stopStartSeq", description="Start stop sequence index")
    tap_in_time: Optional[datetime] = Field(None, alias="tapInTime", description="Timestamp of tap-in")
    tap_out_stops: Optional[str] = Field(None, alias="tapOutStops", description="Stop ID for tap-out")
    tap_out_stops_name: Optional[str] = Field(None, alias="tapOutStopsName", description="Stop name for tap-out")
    tap_out_stops_lat: Optional[float] = Field(None, alias="tapOutStopsLat", description="Tap-out latitude")
    tap_out_stops_lon: Optional[float] = Field(None, alias="tapOutStopsLon", description="Tap-out longitude")
    stop_end_seq: Optional[int] = Field(None, alias="stopEndSeq", description="End stop sequence index")
    tap_out_time: Optional[datetime] = Field(None, alias="tapOutTime", description="Timestamp of tap-out")
    pay_amount: Optional[float] = Field(3500.0, alias="payAmount", description="Transaction fare amount in IDR")

    @field_validator("trans_id", "pay_card_id")
    @classmethod
    def validate_required_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Required identifier cannot be empty")
        return v.strip()

    @field_validator("direction", "stop_end_seq", mode="before")
    @classmethod
    def coerce_float_to_int(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None

    @field_validator("pay_card_birth_date", mode="before")
    @classmethod
    def coerce_birth_date(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None


class StreamingTapEvent(RawTapTransaction):
    """Pydantic model for validating real-time streaming tap transactions over Kafka."""

    is_simulated: bool = Field(True, description="Always TRUE for simulated replay data")


class DeadLetterEvent(BaseModel):
    """Pydantic model for messages routed to Kafka Dead-Letter Queue (taps.deadletter)."""

    model_config = ConfigDict(from_attributes=True)

    original_payload: Any = Field(..., description="The raw unparseable or invalid payload")
    error_message: str = Field(..., description="Detailed validation or processing error")
    error_type: str = Field(..., description="Class or category of error (e.g. ValidationError, JSONDecodeError)")
    failed_at: str = Field(..., description="ISO 8601 UTC timestamp of failure")
    source_topic: str = Field("taps.raw", description="Original topic where error occurred")


