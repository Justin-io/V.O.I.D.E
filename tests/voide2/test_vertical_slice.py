"""V.O.I.D.E. 2.0 end-to-end and domain unit tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from voide2.evaluation import asset_time_split, binary_metrics
from voide2.monitoring import DriftMonitor, ingestion_quality
from voide2.schema import AssetTwinState, TelemetryEvent, default_chiller_asset
from voide2.scenarios import MaintenanceScenario, rank_scenarios
from voide2.simulator import simulate, write_simulation
from voide2.telemetry import TelemetryValidationError, parse_event_time, read_csv_events, replay_events, validate_event
from voide2.twin import AssetRegistry, DigitalTwin


def test_simulator_is_deterministic_and_labels_are_separate():
    events_a, truth_a = simulate(assets=3, hours=24, seed=7)
    events_b, truth_b = simulate(assets=3, hours=24, seed=7)
    assert events_a == events_b
    assert truth_a == truth_b
    assert all(event.source == "synthetic_simulator" for event in events_a)
    assert all(row["is_synthetic"] for row in truth_a)
    assert {row["failure_mode"] for row in truth_a} == {
        "bearing_wear", "thermal_overload", "efficiency_loss"
    }


def test_asset_wise_split_has_no_asset_leakage():
    events, _ = simulate(assets=5, hours=24, seed=11)
    train, test, description = asset_time_split(events, seed=4)
    assert {e.asset_id for e in train}.isdisjoint({e.asset_id for e in test})
    assert "asset_holdout=" in description
    assert min(e.event_time for e in train) <= max(e.event_time for e in train)
    assert min(e.event_time for e in test) <= max(e.event_time for e in test)


def test_replay_is_event_time_ordered_and_stable():
    events, _ = simulate(assets=2, hours=8, seed=12)
    ordered = list(replay_events(reversed(events)))
    assert ordered == sorted(events, key=lambda e: (e.event_time, e.sequence, e.event_id))


def test_csv_roundtrip_and_twin_idempotency(tmp_path):
    telemetry, _ = write_simulation(tmp_path, assets=2, hours=8, seed=13)
    parsed = []
    registry = AssetRegistry()
    import pandas as pd
    ids = sorted(pd.read_csv(telemetry, usecols=["asset_id"])["asset_id"].unique())
    for asset_id in ids:
        spec = default_chiller_asset(str(asset_id))
        registry.register(spec)
        parsed.extend(read_csv_events(telemetry, spec))
    twin = DigitalTwin(registry)
    states = twin.replay(parsed)
    assert len(states) == len(parsed)
    state = twin.states[ids[0]]
    count = state.observation_count
    first = next(e for e in parsed if e.asset_id == ids[0])
    twin.apply(first)
    assert state.observation_count == count
    assert state.last_event_time is not None
    assert state.rul_hours is not None
    assert state.prediction_uncertainty is not None


def test_naive_timestamp_is_rejected():
    with pytest.raises(TelemetryValidationError, match="timezone"):
        parse_event_time("2026-01-01T00:00:00")


def test_invalid_sensor_value_is_rejected():
    asset = default_chiller_asset()
    event = TelemetryEvent(
        asset_id=asset.asset_id,
        event_time=datetime.now(timezone.utc),
        values={"not_a_sensor": 1.0},
        event_id="bad",
        source="test",
    )
    with pytest.raises(TelemetryValidationError, match="unknown sensor"):
        validate_event(event, asset)


def test_twin_rejects_time_regression():
    events, _ = simulate(assets=2, hours=8, seed=15)
    asset = default_chiller_asset(events[0].asset_id)
    registry = AssetRegistry()
    registry.register(asset)
    twin = DigitalTwin(registry)
    asset_events = sorted((e for e in events if e.asset_id == asset.asset_id), key=lambda e: e.event_time)
    for event in asset_events:
        twin.apply(event)
    late = TelemetryEvent(
        asset_id=asset.asset_id,
        event_time=asset_events[0].event_time,
        values={"load_pct": 40.0},
        event_id="late-new-event",
        source="test",
    )
    with pytest.raises(ValueError, match="late event"):
        twin.apply(late)


def test_scenario_ranking_prefers_lower_risk_adjusted_score():
    state = AssetTwinState(asset_id="x", failure_probability=0.8)
    scenarios = [
        MaintenanceScenario("inspect", "inspect", 1, 1, 0.05, 0.02),
        MaintenanceScenario("service", "service", 3, 4, 0.4, 0.2),
    ]
    ranked = rank_scenarios(state, scenarios)
    assert ranked[0]["score_lower_is_better"] < ranked[1]["score_lower_is_better"]


def test_binary_metrics_handles_single_class():
    metrics = binary_metrics([1, 1], [0.8, 0.7])
    assert metrics["pr_auc_average_precision"] is None
    assert metrics["brier_score"] >= 0


def test_drift_monitor_requires_full_window_and_detects_shift():
    monitor = DriftMonitor(reference_mean=0.0, reference_std=1.0, z_threshold=2, window_size=5)
    for _ in range(4):
        assert monitor.observe(4.0)["drift_detected"] is False
    assert monitor.observe(4.0)["drift_detected"] is True


def test_ingestion_quality_does_not_invent_lag():
    events, _ = simulate(assets=2, hours=8, seed=19)
    metrics = ingestion_quality(events)
    assert metrics["event_count"] == len(events)
    assert metrics["ingestion_lag_seconds_p95"] is None
