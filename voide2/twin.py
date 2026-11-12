"""In-memory digital twin state with idempotent event application."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .models import Prediction, predict_event
from .schema import AssetSpec, AssetTwinState, TelemetryEvent


class AssetRegistry:
    def __init__(self) -> None:
        self._assets: dict[str, AssetSpec] = {}

    def register(self, asset: AssetSpec) -> None:
        if asset.asset_id in self._assets and self._assets[asset.asset_id] != asset:
            raise ValueError(f"asset {asset.asset_id!r} is already registered differently")
        self._assets[asset.asset_id] = asset

    def get(self, asset_id: str) -> AssetSpec:
        try:
            return self._assets[asset_id]
        except KeyError as exc:
            raise KeyError(f"unregistered asset: {asset_id}") from exc

    def all(self) -> tuple[AssetSpec, ...]:
        return tuple(self._assets[key] for key in sorted(self._assets))


class DigitalTwin:
    def __init__(self, registry: AssetRegistry) -> None:
        self.registry = registry
        self.states: dict[str, AssetTwinState] = {}
        self._history: dict[str, list[TelemetryEvent]] = {}
        self._seen_events: set[str] = set()
        self.predictions: dict[str, Prediction] = {}

    def apply(self, event: TelemetryEvent) -> AssetTwinState:
        asset = self.registry.get(event.asset_id)
        known = {sensor.name for sensor in asset.sensors}
        unknown = set(event.values) - known
        if unknown:
            raise ValueError(f"unknown sensors for {event.asset_id}: {sorted(unknown)}")
        if event.event_id in self._seen_events:
            return self.states[event.asset_id]
        state = self.states.setdefault(event.asset_id, AssetTwinState(asset_id=event.asset_id))
        if state.last_event_time and event.event_time < state.last_event_time:
            raise ValueError("late event would regress twin state; replay through event-time reorderer")
        self._seen_events.add(event.event_id)
        history = self._history.setdefault(event.asset_id, [])
        prediction = predict_event(event, history)
        state.last_event_time = event.event_time
        state.last_event_id = event.event_id
        state.latest_values = dict(event.values)
        state.observation_count += 1
        state.missing_observations += sum(value is None for value in event.values.values())
        state.anomaly_score = prediction.anomaly_score
        state.failure_probability = prediction.failure_probability
        state.rul_hours = prediction.rul_hours
        state.prediction_uncertainty = prediction.uncertainty_hours
        state.health_status = (
            "critical" if prediction.failure_probability >= 0.8
            else "degraded" if prediction.failure_probability >= 0.45
            else "nominal"
        )
        state.evidence = list(prediction.evidence) + list(event.quality_flags)
        history.append(event)
        self.predictions[event.event_id] = prediction
        return state

    def replay(self, events: Iterable[TelemetryEvent]) -> list[AssetTwinState]:
        from .telemetry import replay_events

        snapshots = []
        for event in replay_events(events):
            snapshots.append(self.apply(event))
        return snapshots

    def history(self, asset_id: str) -> tuple[TelemetryEvent, ...]:
        return tuple(self._history.get(asset_id, ()))

    def fleet_snapshot(self) -> dict[str, object]:
        states = [self.states[key] for key in sorted(self.states)]
        return {
            "asset_count": len(states),
            "nominal": sum(state.health_status == "nominal" for state in states),
            "degraded": sum(state.health_status == "degraded" for state in states),
            "critical": sum(state.health_status == "critical" for state in states),
            "assets": [state.to_dict() for state in states],
        }
