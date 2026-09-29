"""Unit tests for AnomalyAuditor multi-layer telemetry pipeline."""

import os
import pytest
from agent.data_engine.anomaly_auditor import AnomalyAuditor


@pytest.fixture
def dataset_path():
    path = "datasets/development_dataset.csv"
    if not os.path.exists(path):
        pytest.skip(f"Dataset not found at {path}")
    return path


def test_anomaly_auditor_structure(dataset_path):
    auditor = AnomalyAuditor()
    report = auditor.audit(dataset_path)

    assert report["row_count"] == 25003
    assert report["column_count"] == 11
    assert "CHILLER-01" in report["entities"]
    assert "CHILLER-02" in report["entities"]
    assert "CHILLER-03" in report["entities"]

    # Verify all 4 classes are present
    assert "classes" in report
    classes = report["classes"]
    assert "hard_sensor_errors" in classes
    assert "sustained_regimes" in classes
    assert "contradictions" in classes
    assert "data_availability" in classes

    assert classes["hard_sensor_errors"]["count"] > 0
    assert classes["sustained_regimes"]["count"] > 0
    assert classes["contradictions"]["count"] > 0
    assert classes["data_availability"]["count"] > 0


def test_thermodynamic_consistency_metrics(dataset_path):
    auditor = AnomalyAuditor()
    report = auditor.audit(dataset_path)

    tm = report["thermodynamic_metrics"]
    assert tm["valid_observations"] == 24983
    assert abs(tm["residual_mean"] - 0.29) < 0.05
    assert abs(tm["residual_std"] - 1.16) < 0.05


def test_data_availability_metrics(dataset_path):
    auditor = AnomalyAuditor()
    report = auditor.audit(dataset_path)

    am = report["availability_metrics"]
    assert am["total_missing_cells"] == 128
    assert am["affected_rows"] == 90
    assert am["missing_block_count"] == 18
    assert am["coverage_gap_count"] == 25


def test_high_confidence_anomalies_detected(dataset_path):
    auditor = AnomalyAuditor()
    report = auditor.audit(dataset_path)

    hca = report["high_confidence_anomalies"]
    assert len(hca) >= 20

    # Key benchmark timestamps from data analysis
    benchmarks = [
        "2019-08-27",  # Multi-sensor transient
        "2019-09-27",  # Load sensor collapse
        "2019-11-19",  # Flow depression saturation
        "2020-01-07",  # Stuck outside temperature
        "2020-01-27",  # Load surge
        "2020-01-28",  # Energy anomaly
        "2020-03-31",  # Stuck load
        "2020-04-13",  # Wind speed discrepancy
        "2020-04-16",  # Thermodynamic humidity violation
        "2020-04-20",  # CW temp offset
        "2020-05-03",  # Corrupted meter surges
        "2020-05-14",  # Load plateau
    ]

    for b in benchmarks:
        matched = [a for a in hca if b in str(a.get("timestamp"))]
        assert len(matched) > 0, f"Expected anomaly around {b} not found in high-confidence list"
