"""Transparent statistical predictive baselines for synthetic/industrial telemetry."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Iterable

from .schema import TelemetryEvent


@dataclass(frozen=True)
class Prediction:
    asset_id: str
    event_time: str
    anomaly_score: float
    failure_probability: float
    rul_hours: float
    uncertainty_hours: float
    evidence: tuple[str, ...]
    model_name: str = "trend_statistical_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "event_time": self.event_time,
            "anomaly_score": round(self.anomaly_score, 6),
            "failure_probability": round(self.failure_probability, 6),
            "rul_hours": round(self.rul_hours, 4),
            "uncertainty_hours": round(self.uncertainty_hours, 4),
            "evidence": list(self.evidence),
            "model_name": self.model_name,
        }


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 60.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -60.0))
    return z / (1.0 + z)


def predict_event(
    event: TelemetryEvent,
    history: Iterable[TelemetryEvent],
    *,
    nominal_power_kw_per_load: float = 0.48,
    nominal_vibration_mm_s: float = 2.5,
    failure_threshold_health: float = 0.55,
) -> Prediction:
    """Estimate risk and RUL from evidence; no trained failure labels are implied.

    RUL baseline extrapolates an observed health proxy based on power efficiency
    and vibration. Its interval is a heuristic uncertainty band and must not be
    interpreted as a calibrated confidence interval.
    """
    samples = [e for e in history if e.asset_id == event.asset_id]
    values = event.values
    load = values.get("load_pct")
    power = values.get("power_kw")
    vibration = values.get("vibration_mm_s")
    temp = values.get("bearing_temp_c")
    flow = values.get("flow_lps")
    evidence: list[str] = []
    if load is None or power is None:
        evidence.append("insufficient_load_or_power_for_efficiency")
        efficiency_ratio = 1.0
    else:
        expected = max(1.0, nominal_power_kw_per_load * float(load))
        efficiency_ratio = float(power) / expected
        if efficiency_ratio > 1.25:
            evidence.append("power_intensity_above_nominal_proxy")
    if vibration is not None and float(vibration) > nominal_vibration_mm_s:
        evidence.append("vibration_above_reference_proxy")
    if temp is not None and float(temp) > 75:
        evidence.append("bearing_temperature_high_for_simulator_contract")
    if flow is not None and load is not None and float(load) > 20 and float(flow) / float(load) < 1.0:
        evidence.append("flow_to_load_ratio_depressed")

    anomaly_score = min(1.0, max(0.0, (
        max(0.0, efficiency_ratio - 1.0) / 0.8
        + max(0.0, (float(vibration or 0) / nominal_vibration_mm_s) - 1.0) / 2.0
        + max(0.0, (float(temp or 35) - 55.0) / 50.0)
    ) / 3.0))
    failure_probability = _sigmoid(-3.2 + 5.0 * anomaly_score + 0.8 * len(evidence))

    # A dimensionless deterioration proxy, estimated against fixed documented
    # reference values. This is deliberately a baseline, not a learned RUL model.
    health_proxy = max(0.02, min(
        1.0,
        1.0
        - 0.34 * max(0.0, efficiency_ratio - 1.0)
        - 0.22 * max(0.0, float(vibration or 0) / nominal_vibration_mm_s - 1.0)
        - 0.003 * max(0.0, float(temp or 35) - 45.0),
    ))
    degradation_rates: list[float] = []
    ordered = sorted(samples[-36:], key=lambda e: e.event_time)
    if len(ordered) >= 4:
        proxies: list[tuple[float, float]] = []
        for sample in ordered:
            v = sample.values
            l = v.get("load_pct")
            p = v.get("power_kw")
            vib = v.get("vibration_mm_s")
            t = v.get("bearing_temp_c")
            if None in (l, p, vib, t):
                continue
            er = float(p) / max(1.0, nominal_power_kw_per_load * float(l))
            hp = max(0.02, min(1.0, 1.0 - 0.34 * max(0, er - 1)
                               - 0.22 * max(0, float(vib) / nominal_vibration_mm_s - 1)
                               - 0.003 * max(0, float(t) - 45)))
            proxies.append((sample.event_time.timestamp() / 3600.0, hp))
        if len(proxies) >= 4:
            x0 = statistics.mean(x for x, _ in proxies)
            y0 = statistics.mean(y for _, y in proxies)
            denom = sum((x - x0) ** 2 for x, _ in proxies)
            slope = sum((x - x0) * (y - y0) for x, y in proxies) / denom if denom else 0.0
            if slope < -1e-6:
                degradation_rates.append(-slope)

    rate = statistics.mean(degradation_rates) if degradation_rates else 0.001
    remaining = max(0.0, health_proxy - failure_threshold_health)
    rul = min(100_000.0, remaining / rate)
    uncertainty = max(1.0, rul * (0.35 if degradation_rates else 0.75))
    if not evidence:
        evidence.append("no_configured_proxy_thresholds_exceeded")
    return Prediction(
        asset_id=event.asset_id,
        event_time=event.event_time.isoformat(),
        anomaly_score=anomaly_score,
        failure_probability=failure_probability,
        rul_hours=rul,
        uncertainty_hours=uncertainty,
        evidence=tuple(evidence),
    )


def persistence_prediction(event: TelemetryEvent, history: Iterable[TelemetryEvent]) -> Prediction:
    """Simple persistence comparator: repeat current score and 1000 h RUL."""
    values = event.values
    vibration = float(values.get("vibration_mm_s") or 0)
    temp = float(values.get("bearing_temp_c") or 35)
    score = min(1.0, max(0.0, (vibration / 10.0 + temp / 150.0) / 2.0))
    return Prediction(
        asset_id=event.asset_id,
        event_time=event.event_time.isoformat(),
        anomaly_score=score,
        failure_probability=score,
        rul_hours=1000.0,
        uncertainty_hours=1000.0,
        evidence=("persistence_baseline_no_degradation_fit",),
        model_name="persistence_baseline",
    )
