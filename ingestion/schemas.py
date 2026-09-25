"""Pydantic schemas and validation models for KoridorTJ data ingestion."""

from datetime import datetime
from typing import Optional
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
