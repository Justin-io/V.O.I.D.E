"""Synthetic industrial chiller simulator with explicit degradation ground truth.

This dataset is synthetic and is intended for algorithm development only. It is
not a model of any specific plant and does not encode validated safety limits.
"""
from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .schema import AssetSpec, TelemetryEvent, default_chiller_asset
from .telemetry import validate_event


def simulate(
    *,
    assets: int = 4,
    hours: int = 240,
    interval_minutes: int = 10,
    seed: int = 20261112,
    missing_rate: float = 0.015,
    noise_scale: float = 1.0,
) -> tuple[list[TelemetryEvent], list[dict[str, Any]]]:
    if assets < 2 or hours < 8 or interval_minutes <= 0:
        raise ValueError("need >=2 assets, >=8 hours and a positive sampling interval")
    if not 0 <= missing_rate < 1 or noise_scale < 0:
        raise ValueError("missing_rate must be in [0,1) and noise_scale non-negative")
    rng = random.Random(seed)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events: list[TelemetryEvent] = []
    truth: list[dict[str, Any]] = []
    steps = hours * 60 // interval_minutes

    for asset_index in range(assets):
        asset_id = f"CHILLER-SIM-{asset_index + 1:02d}"
        asset: AssetSpec = default_chiller_asset(asset_id)
        failure_start = int(steps * (0.57 + 0.06 * (asset_index % 3)))
        initial_health = rng.uniform(0.94, 1.0)
        degradation_rate = rng.uniform(0.00035, 0.0008)
        fault_mode = ("bearing_wear", "thermal_overload", "efficiency_loss")[
            asset_index % 3
        ]
        for step in range(steps):
            event_time = now + timedelta(minutes=interval_minutes * step)
            regime = "night" if 0.0 <= (event_time.hour + event_time.minute / 60) % 24 < 6 else "day"
            load = 42 + 18 * math.sin(2 * math.pi * step / max(1, 144)) + rng.gauss(0, 3 * noise_scale)
            load = min(95.0, max(20.0, load))
            health = max(0.05, initial_health - degradation_rate * max(0, step - failure_start))
            age = max(0, step - failure_start)
            ambient = 27 + 5 * math.sin(2 * math.pi * step / max(1, 144)) + rng.gauss(0, noise_scale)
            flow = 1.65 * load * (0.88 + 0.12 * health) + rng.gauss(0, 1.1 * noise_scale)
            base_power = 0.31 * load + 0.008 * load**2
            power = base_power / max(health, 0.2) + rng.gauss(0, 1.8 * noise_scale)
            bearing_temp = 35 + 0.22 * load + (1 - health) * 48 + rng.gauss(0, 1.2 * noise_scale)
            vibration = 1.0 + 0.018 * load + (1 - health) * 11 + rng.gauss(0, 0.12 * noise_scale)
            if fault_mode == "thermal_overload":
                bearing_temp += max(0, age) * 0.0008
            values: dict[str, float | None] = {
                "load_pct": round(load, 4),
                "flow_lps": round(max(0.0, flow), 4),
                "power_kw": round(max(0.0, power), 4),
                "bearing_temp_c": round(bearing_temp, 4),
                "vibration_mm_s": round(max(0.0, vibration), 4),
                "ambient_temp_c": round(ambient, 4),
            }
            # Random missingness and rare bursts are controlled by the seed.
            for name in values:
                if rng.random() < missing_rate:
                    values[name] = None
            event = TelemetryEvent(
                asset_id=asset_id,
                event_time=event_time,
                values=values,
                event_id=f"{asset_id}-{step:06d}",
                source="synthetic_simulator",
                sequence=step,
                quality_flags=(),
            )
            events.append(validate_event(event, asset))
            # Ground truth is retained separately from observable telemetry.
            truth.append({
                "asset_id": asset_id,
                "event_time": event_time.isoformat(),
                "step": step,
                "health_index": round(health, 8),
                "degradation_active": bool(step >= failure_start),
                "failure_mode": fault_mode,
                "failure_start_step": failure_start,
                "regime": regime,
                "is_synthetic": True,
            })
    return events, truth


def write_simulation(
    output_dir: str | Path,
    *,
    assets: int = 4,
    hours: int = 240,
    interval_minutes: int = 10,
    seed: int = 20261112,
) -> tuple[Path, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    events, truth = simulate(
        assets=assets, hours=hours, interval_minutes=interval_minutes, seed=seed
    )
    telemetry_path = target / "telemetry.csv"
    truth_path = target / "ground_truth.csv"
    columns = [
        "event_time", "asset_id", "event_id", "source", "sequence",
        "load_pct", "flow_lps", "power_kw", "bearing_temp_c",
        "vibration_mm_s", "ambient_temp_c",
    ]
    with telemetry_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for event in events:
            writer.writerow({
                "event_time": event.event_time.isoformat(),
                "asset_id": event.asset_id,
                "event_id": event.event_id,
                "source": event.source,
                "sequence": event.sequence,
                **event.values,
            })
    with truth_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(truth[0]))
        writer.writeheader()
        writer.writerows(truth)
    return telemetry_path, truth_path
