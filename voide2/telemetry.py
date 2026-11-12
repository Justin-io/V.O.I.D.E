"""CSV ingestion, unit validation and deterministic event-time replay."""
from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .schema import AssetSpec, TelemetryEvent


class TelemetryValidationError(ValueError):
    """Raised when telemetry violates the declared asset contract."""


def parse_event_time(value: str) -> datetime:
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise TelemetryValidationError(f"invalid event_time: {value!r}") from exc
    if parsed.tzinfo is None:
        raise TelemetryValidationError("event_time must include timezone offset or Z")
    return parsed.astimezone(timezone.utc)


def validate_event(event: TelemetryEvent, asset: AssetSpec) -> TelemetryEvent:
    if event.asset_id != asset.asset_id:
        raise TelemetryValidationError(
            f"event asset {event.asset_id!r} does not match {asset.asset_id!r}"
        )
    specs = {sensor.name: sensor for sensor in asset.sensors}
    unknown = set(event.values) - set(specs)
    if unknown:
        raise TelemetryValidationError(f"unknown sensor columns: {sorted(unknown)}")
    flags = list(event.quality_flags)
    for name, value in event.values.items():
        if value is None:
            flags.append(f"missing:{name}")
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise TelemetryValidationError(f"{name} must be a finite number or null")
        spec = specs[name]
        if value < spec.min_value or value > spec.max_value:
            flags.append(f"out_of_range:{name}")
    return TelemetryEvent(
        asset_id=event.asset_id,
        event_time=event.event_time,
        values=dict(event.values),
        event_id=event.event_id,
        source=event.source,
        sequence=event.sequence,
        quality_flags=tuple(sorted(set(flags))),
    )


def read_csv_events(path: str | Path, asset: AssetSpec) -> list[TelemetryEvent]:
    """Read rows for one asset from a shared multi-asset telemetry CSV."""
    rows: list[TelemetryEvent] = []
    source_path = Path(path)
    with source_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"event_time", "asset_id", "event_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise TelemetryValidationError(f"missing required columns: {sorted(missing)}")
        sensor_names = {sensor.name for sensor in asset.sensors}
        unknown = set(reader.fieldnames or []) - required - sensor_names - {"source", "sequence"}
        if unknown:
            raise TelemetryValidationError(f"unknown CSV columns: {sorted(unknown)}")
        for index, row in enumerate(reader):
            asset_id = (row.get("asset_id") or "").strip()
            if asset_id != asset.asset_id:
                continue
            values: dict[str, float | None] = {}
            for sensor in asset.sensors:
                raw = (row.get(sensor.name) or "").strip()
                if raw == "":
                    values[sensor.name] = None
                else:
                    try:
                        values[sensor.name] = float(raw)
                    except ValueError as exc:
                        raise TelemetryValidationError(
                            f"row {index + 2}: invalid numeric value for {sensor.name}"
                        ) from exc
            event = TelemetryEvent(
                asset_id=asset_id,
                event_time=parse_event_time(row.get("event_time") or ""),
                values=values,
                event_id=(row.get("event_id") or f"csv-{index}").strip(),
                source=(row.get("source") or f"csv:{source_path.name}").strip(),
                sequence=int(row.get("sequence") or index),
            )
            rows.append(validate_event(event, asset))
    return rows


def replay_events(
    events: Iterable[TelemetryEvent], *, allow_out_of_order: bool = False
) -> Iterator[TelemetryEvent]:
    """Replay deterministically by event-time, then sequence, then event id.

    Streaming adapters should buffer according to a bounded-lateness policy before
    invoking this finite replay function.
    """
    ordered = sorted(events, key=lambda e: (e.event_time, e.sequence, e.event_id))
    if not allow_out_of_order:
        previous: datetime | None = None
        for event in ordered:
            if previous is not None and event.event_time < previous:
                raise TelemetryValidationError("event-time ordering failure")
            previous = event.event_time
    yield from ordered
