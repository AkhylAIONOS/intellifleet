from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DEFAULT_PLAYBACK_SPEED = 120

Mode = Literal['AIR', 'SURFACE', 'RAIL']


class Schedule(BaseModel):
    data_source: Literal["FEDEX_SOURCE", "SYNTHETIC_SCHEDULE", "SYNTHETIC_NETWORK"] = "FEDEX_SOURCE"
    eta_day_offset: int | None = Field(default=None, ge=0)
    origin_coordinates: tuple[float, float] | None = None
    destination_coordinates: tuple[float, float] | None = None
    schedule_id: str
    source_sheet: str
    source_row: int
    origin_city: str
    origin_station: str
    gateway: str
    lane: str
    run: str
    mode: Mode
    source_mode: str
    service: str
    cutoff_minutes: int | None = Field(default=None, ge=0, lt=1440)
    etd_minutes: int | None = Field(default=None, ge=0, lt=1440)
    eta_minutes: int | None = Field(default=None, ge=0, lt=1440)
    retrieval_minutes: int | None = Field(default=None, ge=0, lt=1440)
    transit_minutes: float | None = Field(default=None, ge=0)
    vehicle_count: int | None = Field(default=None, ge=0)
    source: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    valid: bool = True


class EligibilityInput(BaseModel):
    origin_station: str = Field(min_length=1, max_length=40)
    gateway: str = Field(min_length=1, max_length=40)
    shipment_ready_datetime: datetime
    simulation_date: date

    @field_validator('origin_station', 'gateway')
    @classmethod
    def normalize_code(cls, value):
        value = value.strip().upper()
        if not value:
            raise ValueError('Station/gateway is required')
        return value


class SimulationInput(EligibilityInput):
    road_optimization: Literal['FASTEST', 'SHORTEST', 'CHEAPEST'] = 'FASTEST'
    shipment_id: str = Field(default='DEMO-SHIPMENT', min_length=1, max_length=80)
    schedule_id: str | None = None
    speed: float = Field(default=DEFAULT_PLAYBACK_SPEED, ge=1, le=10000, allow_inf_nan=False)
    seed: int = 42
    random_events: bool = False


class DisruptionInput(BaseModel):
    event_type: Literal['DELAY', 'SLOWDOWN', 'UNEXPECTED_STOP', 'BREAKDOWN'] = 'DELAY'
    expected_delay_minutes: float = Field(default=30, gt=0, le=1440, allow_inf_nan=False)
    reason: str = Field(default='Presenter-injected synthetic event', min_length=1, max_length=500)


class ControlInput(BaseModel):
    action: Literal['pause', 'resume', 'stop', 'reset', 'speed']
    speed: float | None = Field(default=None, ge=1, le=10000, allow_inf_nan=False)
