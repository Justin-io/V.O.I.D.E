"""End-to-end replay service and machine-readable benchmark output."""
from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn

from .evaluation import asset_time_split, binary_metrics, split_summary
from .models import predict_event, persistence_prediction
from .schema import default_chiller_asset
from .scenarios import MaintenanceScenario, rank_scenarios
from .simulator import write_simulation
from .telemetry import read_csv_events, replay_events
from .twin import AssetRegistry, DigitalTwin


def run_replay(
    csv_path: str | Path,
    *,
    benchmark_dir: str | Path | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    source = Path(csv_path)
    truth_path = source.with_name("ground_truth.csv")
    frame = pd.read_csv(source, usecols=["asset_id"])
    asset_ids = sorted(frame["asset_id"].dropna().unique().tolist())
    if not asset_ids:
        raise ValueError("telemetry contains no asset IDs")
    registry = AssetRegistry()
    specs = {}
    for asset_id in asset_ids:
        spec = default_chiller_asset(str(asset_id))
        registry.register(spec)
        specs[str(asset_id)] = spec
    events = []
    for spec in specs.values():
        events.extend(read_csv_events(source, spec))
    ordered = list(replay_events(events))
    twin = DigitalTwin(registry)
    twin.replay(ordered)

    results: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "source_type": "synthetic" if all(e.source == "synthetic_simulator" for e in events) else "csv",
        "event_count": len(events),
        "fleet": twin.fleet_snapshot(),
        "asset_time_split": None,
        "metrics": {},
        "limitations": [
            "RUL is a statistical trend baseline, not a trained prognostics model",
            "failure probability is not calibrated unless evaluated on representative failure labels",
            "synthetic telemetry is not plant evidence",
            "no safety certification or autonomous control",
        ],
    }

    train, test, split_description = asset_time_split(ordered, seed=seed)
    results["asset_time_split"] = {
        "description": split_description,
        **split_summary(train, test),
    }
    predictions = []
    prediction_history: dict[str, list] = {asset_id: [] for asset_id in specs}
    for event in ordered:
        history = prediction_history[event.asset_id]
        prediction = predict_event(event, history)
        baseline = persistence_prediction(event, history)
        predictions.append((event, prediction, baseline))
        history.append(event)

    if truth_path.exists():
        truth = pd.read_csv(truth_path)
        truth["event_id"] = truth["asset_id"].astype(str) + "-" + truth["step"].astype(int).map(lambda n: f"{n:06d}")
        truth_map = truth.set_index("event_id").to_dict("index")
        labels, scores, baseline_scores = [], [], []
        for event, prediction, baseline in predictions:
            label_row = truth_map.get(event.event_id)
            if label_row is not None:
                labels.append(int(bool(label_row["degradation_active"])))
                scores.append(prediction.failure_probability)
                baseline_scores.append(baseline.failure_probability)
        if labels and len(set(labels)) > 1:
            results["metrics"]["synthetic_degradation_phase"] = {
                "trend_baseline": binary_metrics(labels, scores),
                "persistence_baseline": binary_metrics(labels, baseline_scores),
                "label_definition": "simulator degradation_active; not physical failure",
            }
    results["environment"] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "seed": seed,
        "accelerator": "CPU",
    }
    for asset_id, state in twin.states.items():
        scenarios = [
            MaintenanceScenario("inspect", "inspection_and_condition_assessment", 1.0, 2.0, 0.05, 0.02),
            MaintenanceScenario("service", "planned_service", 4.0, 8.0, 0.35, 0.12),
            MaintenanceScenario("replace", "component_replacement", 8.0, 25.0, 0.70, 0.30),
        ]
        results.setdefault("maintenance_scenarios", {})[asset_id] = rank_scenarios(state, scenarios)
    if benchmark_dir is not None:
        output = Path(benchmark_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "benchmark.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        (output / "benchmark.md").write_text(render_benchmark(results), encoding="utf-8")
        pd.DataFrame([
            {"asset_id": event.asset_id, "event_time": event.event_time.isoformat(), **prediction.to_dict()}
            for event, prediction, _ in predictions
        ]).to_csv(output / "predictions.csv", index=False)
    return results


def render_benchmark(results: dict[str, Any]) -> str:
    fleet = results["fleet"]
    lines = [
        "# V.O.I.D.E. 2.0 Synthetic / Telemetry Replay Benchmark",
        "",
        f"- Source type: `{results['source_type']}`",
        f"- Events replayed: **{results['event_count']}**",
        f"- Assets: **{fleet['asset_count']}**",
        f"- Health states: nominal={fleet['nominal']}, degraded={fleet['degraded']}, critical={fleet['critical']}",
        f"- Split: `{results['asset_time_split']['description']}`",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(results["metrics"], indent=2),
        "```",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in results["limitations"])
    lines.extend([
        "",
        "Synthetic degradation labels measure simulator phase membership, not observed equipment failure.",
        "No plant measurements, safety certification, or control actions are represented.",
    ])
    return "\n".join(lines) + "\n"


def generate_demo(output_dir: str | Path, *, seed: int = 20261112) -> dict[str, Any]:
    telemetry, truth = write_simulation(output_dir, seed=seed)
    result = run_replay(telemetry, benchmark_dir=Path(output_dir) / "benchmark", seed=seed)
    result["artifacts"] = {
        "telemetry": str(telemetry),
        "ground_truth": str(truth),
        "benchmark": str(Path(output_dir) / "benchmark"),
    }
    Path(output_dir, "demo_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
