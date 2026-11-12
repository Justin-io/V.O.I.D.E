"""Counterfactual maintenance scenarios; no live control or actuation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .schema import AssetTwinState


@dataclass(frozen=True)
class MaintenanceScenario:
    scenario_id: str
    action: str
    downtime_hours: float
    cost_units: float
    expected_risk_reduction: float
    expected_health_gain: float

    def __post_init__(self) -> None:
        if self.downtime_hours < 0 or self.cost_units < 0:
            raise ValueError("downtime and cost cannot be negative")
        if not 0 <= self.expected_risk_reduction <= 1:
            raise ValueError("risk reduction must be in [0,1]")
        if not 0 <= self.expected_health_gain <= 1:
            raise ValueError("health gain must be in [0,1]")


def evaluate_scenario(
    state: AssetTwinState,
    scenario: MaintenanceScenario,
    *,
    risk_weight: float = 100.0,
    downtime_weight: float = 2.0,
    cost_weight: float = 1.0,
) -> dict[str, Any]:
    """Score a candidate action using explicit user-provided utility weights.

    This is a transparent decision-support score, not an optimizer trained on
    plant economics. Actions never trigger equipment control.
    """
    baseline_risk = min(1.0, max(0.0, state.failure_probability))
    residual_risk = baseline_risk * (1.0 - scenario.expected_risk_reduction)
    score = (
        residual_risk * risk_weight
        + scenario.downtime_hours * downtime_weight
        + scenario.cost_units * cost_weight
        - scenario.expected_health_gain * risk_weight * 0.15
    )
    return {
        "asset_id": state.asset_id,
        "scenario": asdict(scenario),
        "baseline_failure_probability": baseline_risk,
        "residual_failure_probability": residual_risk,
        "score_lower_is_better": round(score, 6),
        "assumptions": [
            "scenario effect sizes are user-supplied assumptions",
            "risk estimates inherit predictive-model uncertainty",
            "no control or maintenance action is executed",
        ],
    }


def rank_scenarios(
    state: AssetTwinState, scenarios: list[MaintenanceScenario], **weights: float
) -> list[dict[str, Any]]:
    return sorted(
        (evaluate_scenario(state, scenario, **weights) for scenario in scenarios),
        key=lambda item: item["score_lower_is_better"],
    )
