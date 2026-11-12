"""Typed domain contracts for V.O.I.D.E. 2.0.

All timestamps are UTC event-time. Telemetry values are engineering units and
must be mapped explicitly at ingestion; values are never silently converted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SensorSpec:
    name: str
    unit: str
    min_value: float
    max_value: float
    sampling_seconds: int = 60

    def __post_init__(self) -> None:
        if not self.name or not self.unit:
            raise ValueError("sensor name and unit are required")
        if self.min_value >= self.max_value:
            raise ValueError("sensor min_value must be less than max_value")
        if self.sampling_seconds <= 0:
            raise ValueError("sampling_seconds must be positive")


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    asset_type: str
    sensors: tuple[SensorSpec, ...]
    failure_modes: tuple[str, ...] = ("bearing_wear", "thermal_overload", "efficiency_loss")

    def __post_init__(self) -> None:
        if not self.asset_id or not self.asset_type:
            raise ValueError("asset_id and asset_type are required")
        names = [sensor.name for sensor in self.sensors]
        if len(names) != len(set(names)):
            raise ValueError("sensor names must be unique within an asset")
        if not self.sensors:
            raise ValueError("at least one sensor is required")


@dataclass(frozen=True)
class TelemetryEvent:
    asset_id: str
    event_time: datetime
    values: dict[str, float | None]
    event_id: str
    source: str
    sequence: int = 0
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")
        if not self.asset_id or not self.event_id or not self.source:
            raise ValueError("asset_id, event_id and source are required")


@dataclass
class AssetTwinState:
    asset_id: str
    last_event_time: datetime | None = None
    last_event_id: str | None = None
    latest_values: dict[str, float | None] = field(default_factory=dict)
    observation_count: int = 0
    missing_observations: int = 0
    anomaly_score: float = 0.0
    failure_probability: float = 0.0
    rul_hours: float | None = None
    prediction_uncertainty: float | None = None
    health_status: str = "unknown"
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["last_event_time"] = (
            self.last_event_time.isoformat() if self.last_event_time else None
        )
        return result


def default_chiller_asset(asset_id: str = "CHILLER-SIM-01") -> AssetSpec:
    """Reference synthetic chiller; units/ranges are illustrative, not plant limits."""
    return AssetSpec(
        asset_id=asset_id,
        asset_type="synthetic_chiller",
        sensors=(
            SensorSpec("load_pct", "%", 0.0, 100.0),
            SensorSpec("flow_lps", "L/s", 0.0, 250.0),
            SensorSpec("power_kw", "kW", 0.0, 500.0),
            SensorSpec("bearing_temp_c", "degC", -20.0, 150.0),
            SensorSpec("vibration_mm_s", "mm/s", 0.0, 100.0),
            SensorSpec("ambient_temp_c", "degC", -30.0, 65.0),
        ),
    )
