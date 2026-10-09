from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Objective = Literal["cheapest", "fastest", "lowest-risk", "balanced"]
Mode = Literal["road", "air", "rail", "multimodal"]


MODE_ALIASES = {
    "ground": "road",
    "surface": "road",
    "truck": "road",
    "road-transport": "road",
    "ground/road": "road",
    "road/ground": "road",

    "airway": "air",
    "express": "air",
    "air-express": "air",
    "flight": "air",
    "air-transport": "air",

    "multi-modal": "multimodal",
    "multi-modal-route": "multimodal",
    "ground-air-ground": "multimodal",
    "road-air-road": "multimodal",
}


def normalize_modes(value):
    """Canonical transport labels shared by intent, stored context and API models.

    Unknown values remain invalid: normalization must not grant mode feasibility.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return value
    return list(dict.fromkeys(MODE_ALIASES.get(str(mode).strip().casefold().replace(" ", "-"),
                                             str(mode).strip().casefold()) for mode in value))


class Shipment(BaseModel):
    weight_kg: float = Field(gt=0)
    quantity: int = Field(default=1, gt=0)
    sku: str | None = None

class ScoringWeights(BaseModel):
    cost: float = Field(default=.30, ge=0)
    eta: float = Field(default=.25, ge=0)
    risk: float = Field(default=.20, ge=0)
    reliability: float = Field(default=.10, ge=0)
    sla: float = Field(default=.10, ge=0)
    utilization: float = Field(default=.05, ge=0)

    @model_validator(mode="after")
    def positive_total(self):
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("scoring weights must have a positive total")
        return self




PLANNING_TZ = ZoneInfo("Asia/Kolkata")


def parse_planning_deadline(value):
    """Parse common conversational planning deadlines in IST."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=PLANNING_TZ)

    if not isinstance(value, str):
        return value

    raw = value.strip()

    # Preserve normal ISO timestamps.
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=PLANNING_TZ)
    except ValueError:
        pass

    text = raw.casefold().strip()

    match = re.fullmatch(
        r"(today|tomorrow)\s+(?:at\s+)?"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
        text,
        re.I,
    )

    if not match:
        return value

    day, hour, minute, meridiem = match.groups()

    hour = int(hour)
    minute = int(minute or 0)

    if not (1 <= hour <= 12 and 0 <= minute <= 59):
        return value

    if meridiem.lower() == "pm" and hour != 12:
        hour += 12
    elif meridiem.lower() == "am" and hour == 12:
        hour = 0

    now = datetime.now(PLANNING_TZ)

    if day.lower() == "tomorrow":
        now += timedelta(days=1)

    return now.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


class PlanningRequest(BaseModel):
    source: str
    destination: str
    shipment: Shipment
    objective: Objective = "balanced"
    shipment_ready_datetime: datetime | None = None
    deadline: datetime | None = None
    allowed_modes: list[Mode] = Field(default_factory=lambda: ["road", "air", "multimodal"])
    required_mode_sequence: list[Literal["road", "air"]] = Field(default_factory=list)
    target_margin: float = Field(default=0.20, ge=0, lt=1)
    max_risk: float | None = Field(default=None, ge=0, le=1)
    intermediate_stops: list[str] = Field(default_factory=list)
    handling_cost_per_stop: float = Field(default=250.0, ge=0)
    fuel_cost_multiplier: float = Field(default=1.0, gt=0)
    sla_mandatory: bool = False
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    source_country: str | None = None
    destination_country: str | None = None


    @field_validator("deadline", mode="before")
    @classmethod
    def normalize_planning_deadline(cls, value):
        return parse_planning_deadline(value)

    @field_validator("allowed_modes", mode="before")
    @classmethod
    def canonical_modes(cls, value):
        return normalize_modes(value)

    @model_validator(mode="after")
    def validate_locations(self):
        if self.source.strip().casefold() == self.destination.strip().casefold():
            raise ValueError("source and destination must differ")
        if not self.allowed_modes:
            raise ValueError("at least one transport mode is required")
        return self


class ScenarioCreateRequest(BaseModel):
    planning_request: PlanningRequest
    changes: dict[str, Any] = Field(default_factory=dict)


class ConsolidationShipment(BaseModel):
    shipment_id: str
    source: str
    destination: str
    weight_kg: float = Field(gt=0)
    deadline: datetime | None = None
    planned_departure: datetime | None = None
    intermediate_stops: list[str] = Field(default_factory=list)


class ConsolidationRequest(BaseModel):
    shipments: list[ConsolidationShipment] = Field(min_length=2)


class ExpansionRequest(BaseModel):
    demand_locations: list[dict[str, Any]] = Field(min_length=1)
    candidate_hubs: list[dict[str, Any]] = Field(min_length=1)
    hubs_to_open: int = Field(default=1, gt=0)
    facility_cost: float | None = Field(default=None, ge=0)


class BreakdownRequest(BaseModel):
    plan_id: str | None = None
    shipment_id: str | None = None
    vehicle_label: str
    current_location: str
    destination: str
    remaining_weight_kg: float = Field(gt=0)
    deadline: datetime | None = None


class FulfilmentRequest(BaseModel):
    destination: str
    quantity: int = Field(gt=0)
    weight_kg: float = Field(gt=0)
    objective: Objective = "balanced"
    deadline: datetime | None = None


class FutureReplanRequest(BaseModel):
    delayed_vehicle_label: str
    delay_hours: float = Field(gt=0)


class MultiStopRequest(BaseModel):
    source: str
    destination: str
    stops: list[str] = Field(min_length=1)
    shipment: Shipment
    objective: Objective = "balanced"

class TransportScopeRequest(BaseModel):
    source_country: str
    destination_country: str

class ShipmentScheduleRequest(BaseModel):
    shipment_id: str
    source: str
    destination: str
    weight_kg: float = Field(gt=0)
    quantity: int = Field(gt=0)
    sku: str | None = None
    deadline: datetime | None = None
    assigned_vehicle_labels: list[str] = Field(default_factory=list)
    route_id: int | None = None
    scheduled_start: datetime
    scheduled_end: datetime
