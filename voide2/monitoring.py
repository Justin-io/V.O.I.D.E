"""Model and telemetry monitoring primitives."""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from .schema import TelemetryEvent


@dataclass
class DriftMonitor:
    reference_mean: float
    reference_std: float
    z_threshold: float = 3.0
    window_size: int = 50
    values: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.reference_std <= 0 or self.z_threshold <= 0 or self.window_size < 5:
            raise ValueError("invalid drift monitor configuration")
        self.values = deque(self.values, maxlen=self.window_size)

    def observe(self, value: float) -> dict[str, float | bool | int]:
        self.values.append(float(value))
        mean = statistics.mean(self.values)
        z_score = (mean - self.reference_mean) / self.reference_std
        return {
            "window_count": len(self.values),
            "window_mean": mean,
            "mean_z_score": z_score,
            "drift_detected": len(self.values) == self.window_size
            and abs(z_score) >= self.z_threshold,
        }


def ingestion_quality(events: Iterable[TelemetryEvent]) -> dict[str, float | int | None]:
    rows = list(events)
    if not rows:
        return {"event_count": 0, "missing_fraction": None, "out_of_order_count": 0, "ingestion_lag_seconds_p95": None}
    total = missing = out_of_order = 0
    previous_by_asset: dict[str, datetime] = {}
    lags: list[float] = []
    for event in rows:
        total += len(event.values)
        missing += sum(value is None for value in event.values.values())
        previous = previous_by_asset.get(event.asset_id)
        if previous and event.event_time < previous:
            out_of_order += 1
        previous_by_asset[event.asset_id] = max(previous, event.event_time) if previous else event.event_time
        # No ingestion timestamp supplied by CSV: do not fabricate lag.
    return {
        "event_count": len(rows),
        "missing_fraction": missing / total if total else None,
        "out_of_order_count": out_of_order,
        "ingestion_lag_seconds_p95": None,
    }
