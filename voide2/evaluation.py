"""Leakage-aware evaluation helpers and benchmark metrics."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Iterable

from .schema import TelemetryEvent


def asset_time_split(
    events: Iterable[TelemetryEvent],
    *,
    test_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[list[TelemetryEvent], list[TelemetryEvent], str]:
    """Hold out entire assets; never place one asset in both partitions.

    Asset IDs are deterministically shuffled using seed. All observations from
    selected test assets are held out. Event-time ordering is retained within
    each partition. This evaluates unseen-asset generalization, not future-time
    forecasting on known assets.
    """
    items = list(events)
    if len(items) < 2 or not 0.05 <= test_fraction <= 0.5:
        raise ValueError("requires >=2 events and test_fraction in [0.05,0.5]")
    by_asset: dict[str, list[TelemetryEvent]] = defaultdict(list)
    for event in items:
        by_asset[event.asset_id].append(event)
    assets = sorted(by_asset)
    if len(assets) < 2:
        raise ValueError("asset-wise split requires at least two distinct assets")
    import random
    random.Random(seed).shuffle(assets)
    n_test = max(1, min(len(assets) - 1, round(len(assets) * test_fraction)))
    test_assets = set(assets[:n_test])
    train: list[TelemetryEvent] = []
    test: list[TelemetryEvent] = []
    for asset_id, rows in by_asset.items():
        rows.sort(key=lambda event: (event.event_time, event.sequence, event.event_id))
        (test if asset_id in test_assets else train).extend(rows)
    if not train or not test:
        raise ValueError("split produced an empty partition")
    return train, test, (
        f"seed={seed};asset_holdout={sorted(test_assets)};"
        f"test_fraction={test_fraction};whole_asset_holdout=True"
    )


def regression_metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    if not actual or len(actual) != len(predicted):
        raise ValueError("actual and predicted must be non-empty and same length")
    errors = [a - p for a, p in zip(actual, predicted)]
    mae = statistics.mean(abs(error) for error in errors)
    rmse = math.sqrt(statistics.mean(error * error for error in errors))
    return {"mae": mae, "rmse": rmse, "count": float(len(errors))}


def binary_metrics(labels: list[int], scores: list[float]) -> dict[str, float | None]:
    """Compute average precision and Brier score; None if one class is absent."""
    if not labels or len(labels) != len(scores):
        raise ValueError("labels and scores must be non-empty and same length")
    if any(label not in (0, 1) for label in labels):
        raise ValueError("labels must be binary")
    if any(not 0 <= score <= 1 for score in scores):
        raise ValueError("scores must be in [0,1]")
    positives = sum(labels)
    brier = statistics.mean((label - score) ** 2 for label, score in zip(labels, scores))
    if positives == 0 or positives == len(labels):
        return {"pr_auc_average_precision": None, "brier_score": brier, "count": float(len(labels))}
    order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    tp = fp = 0
    ap = previous_recall = 0.0
    for index in order:
        if labels[index]:
            tp += 1
            recall = tp / positives
            ap += (recall - previous_recall) * (tp / (tp + fp))
            previous_recall = recall
        else:
            fp += 1
    return {"pr_auc_average_precision": ap, "brier_score": brier, "count": float(len(labels))}


def split_summary(train: list[TelemetryEvent], test: list[TelemetryEvent]) -> dict[str, Any]:
    train_assets = {event.asset_id for event in train}
    test_assets = {event.asset_id for event in test}
    return {
        "train_events": len(train),
        "test_events": len(test),
        "train_assets": sorted(train_assets),
        "test_assets": sorted(test_assets),
        "asset_overlap": sorted(train_assets & test_assets),
        "time_range_train": [
            min(event.event_time for event in train).isoformat(),
            max(event.event_time for event in train).isoformat(),
        ],
        "time_range_test": [
            min(event.event_time for event in test).isoformat(),
            max(event.event_time for event in test).isoformat(),
        ],
    }
