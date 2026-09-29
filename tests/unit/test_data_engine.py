"""Unit tests for V.O.I.D.E. Data Intelligence Plane (agent/data_engine/)."""

import os
import pytest
import numpy as np
import pandas as pd

from voide.agent.data_engine.dataset_ingest import DatasetIngestEngine
from voide.agent.data_engine.profiler import DataProfiler
from voide.agent.data_engine.preparator import DataPreparator
from voide.agent.data_engine.feature_engine import FeatureEngine
from voide.agent.data_engine.ml_engine import MLEngine
from voide.agent.data_engine.critic import EvidenceCritic
from voide.agent.data_engine.visual_engine import VisualEngine
from voide.agent.data_engine.report_engine import ReportEngine


@pytest.fixture
def sample_csv(tmp_path):
    """Generate a deterministic synthetic dataset resembling HVAC chiller telemetry."""
    n_rows = 150
    timestamps = pd.date_range("2020-04-01 00:00:00", periods=n_rows, freq="30min")
    
    # Introduce one artificial 3-hour gap at index 75
    ts_list = list(timestamps[:75]) + list(timestamps[75:] + pd.Timedelta(hours=3))
    
    records = []
    for i, ts in enumerate(ts_list):
        for chiller in ["CHILLER-01", "CHILLER-02", "CHILLER-03"]:
            load = 250.0 + 50.0 * np.sin(i / 10.0)
            # Normal power consumption: ~0.35 * load + noise
            power = 0.35 * load + np.random.normal(0, 1.5)
            # Inject persistent anomaly into CHILLER-03 at steps 90-100
            if chiller == "CHILLER-03" and 90 <= i <= 100:
                power += 55.0  # Excessive unexpected consumption
                
            records.append({
                "timestamp": str(ts),
                "equipment_id": chiller,
                "Chiller Energy Consumption (kWh)": power,
                "Building Load (RT)": load,
                "Outdoor Air Temperature (C)": 28.0 + 5.0 * np.sin(i / 24.0),
                "Chilled Water Supply Temp (C)": 6.8,
                "Chilled Water Return Temp (C)": 12.2,
            })
            
    df = pd.DataFrame(records)
    csv_file = tmp_path / "test_chillers.csv"
    df.to_csv(csv_file, index=False)
    return str(csv_file)


def test_dataset_ingest_engine(sample_csv, tmp_path):
    workspace = str(tmp_path / "workspace")
    ingest = DatasetIngestEngine(workspace)
    summary = ingest.ingest(sample_csv, copy_to_workspace=True)
    
    assert summary["row_count"] == 450
    assert summary["column_count"] == 7
    assert len(summary["file_hash"]) == 64
    assert "Chiller Energy Consumption (kWh)" in summary["columns"]
    assert "equipment_id" in summary["columns"]
    assert summary["format"] == "csv"
    assert os.path.exists(summary["file_path"])


def test_data_profiler(sample_csv):
    profiler = DataProfiler()
    profile = profiler.profile(sample_csv)
    
    assert profile["row_count"] == 450
    assert profile["column_count"] == 7
    assert set(profile["entity_summary"]["entities"]) == {"CHILLER-01", "CHILLER-02", "CHILLER-03"}
    assert profile["temporal_profile"]["nominal_interval_human"] == "30 minutes"
    assert profile["temporal_profile"]["irregular_gaps_count"] >= 1
    assert profile["data_health_score"] > 70.0
    assert "Chiller Energy Consumption (kWh)" in profile["columns"]


def test_data_preparator(sample_csv):
    df = pd.read_csv(sample_csv)
    preparator = DataPreparator()
    prep_df, report = preparator.prepare(
        df,
        time_column="timestamp",
        entity_column="equipment_id",
    )
    
    assert "_dt" in prep_df.columns
    assert "_segment_id" in prep_df.columns
    assert report["total_segments"] >= 2
    assert report["prepared_rows"] == 450

    # Test temporal train/test split
    train_df, test_df, split_info = preparator.temporal_split(prep_df, split_ratio=0.7)
    assert len(train_df) + len(test_df) == 450
    assert split_info["train_rows"] == len(train_df)
    assert split_info["test_rows"] == len(test_df)
    assert train_df["_dt"].max() <= test_df["_dt"].min()


def test_feature_engine(sample_csv):
    df = pd.read_csv(sample_csv)
    preparator = DataPreparator()
    prep_df, _ = preparator.prepare(df, time_column="timestamp", entity_column="equipment_id")
    
    feat_engine = FeatureEngine()
    feat_df, feat_report = feat_engine.build_features(
        prep_df,
        target_col="Chiller Energy Consumption (kWh)",
        load_col="Building Load (RT)",
        entity_col="equipment_id",
    )
    
    assert "feat_hour" in feat_df.columns
    assert "feat_dayofweek" in feat_df.columns
    assert "feat_energy_per_load" in feat_df.columns
    assert "feat_chillerenerg_roll_mean_3" in feat_df.columns
    assert len(feat_report["feature_names"]) >= 4


def test_ml_engine_contextual_baseline_and_anomaly_detection(sample_csv):
    df = pd.read_csv(sample_csv)
    preparator = DataPreparator()
    prep_df, _ = preparator.prepare(df, time_column="timestamp", entity_column="equipment_id")
    
    feat_engine = FeatureEngine()
    feat_df, _ = feat_engine.build_features(
        prep_df,
        target_col="Chiller Energy Consumption (kWh)",
        load_col="Building Load (RT)",
        entity_col="equipment_id",
    )
    
    ml = MLEngine()
    context_features = [
        "Building Load (RT)",
        "Outdoor Air Temperature (C)",
        "feat_hour",
    ]
    model_record = ml.fit_expected_behaviour_model(
        feat_df,
        target_col="Chiller Energy Consumption (kWh)",
        feature_cols=context_features,
        entity_col="equipment_id",
    )
    
    assert "overall_r2" in model_record
    assert model_record["overall_r2"] > 0.6
    assert "CHILLER-03" in model_record["entities"]
    assert model_record["entities"]["CHILLER-03"]["r2"] > 0.45
    
    # Predict expected values
    expected = ml.predict_expected(feat_df, model_record)
    assert len(expected) == len(feat_df)
    
    residuals, z_scores, stats = ml.compute_contextual_residuals(
        feat_df,
        target_col="Chiller Energy Consumption (kWh)",
        expected_values=expected,
        entity_col="equipment_id",
    )
    assert len(residuals) == len(feat_df)
    assert len(z_scores) == len(feat_df)
    
    multi_scores = ml.compute_multivariate_scores(feat_df, context_features)
    assert len(multi_scores) == len(feat_df)
    
    # Detect persistent anomalies
    anomalies = ml.find_persistent_anomaly_windows(
        df=feat_df,
        residuals=residuals,
        residual_z_scores=z_scores,
        multivariate_scores=multi_scores,
        expected_values=expected,
        target_col="Chiller Energy Consumption (kWh)",
        entity_col="equipment_id",
        time_col="timestamp",
        min_persistence=3,
        z_threshold=2.2,
    )
    
    # Verify injected anomaly on CHILLER-03 is captured
    ch3_anomalies = [a for a in anomalies if a["equipment_id"] == "CHILLER-03"]
    assert len(ch3_anomalies) >= 1
    top = ch3_anomalies[0]
    assert top["persistence_count"] >= 3
    assert top["residual_score"] > 35.0  # +55 kWh injected
    assert top["severity"] in ("CRITICAL", "HIGH")


def test_evidence_critic_guardrail():
    critic = EvidenceCritic()
    
    # 1. Speculative compressor bearing mechanical failure -> rewritten
    bad_claim = "Chiller 3 compressor bearing mechanical failure detected causing severe breakdown."
    res = critic.validate_claim(bad_claim)
    assert res["has_unsupported_fault_attribution"]
    assert res["status"] == "REWRITTEN"
    assert "specific mechanical fault not established" in res["validated_claim"]
    assert len(res["violations"]) >= 1
    
    # 2. Factual contextual residual statement -> validated unchanged
    good_claim = "Persistent contextual energy deviation of +64.6 kWh observed across 6 steps."
    res_good = critic.validate_claim(good_claim)
    assert not res_good["has_unsupported_fault_attribution"]
    assert res_good["status"] == "VALIDATED"
    assert res_good["validated_claim"] == good_claim


def test_visual_engine_and_report_generation(sample_csv, tmp_path):
    df = pd.read_csv(sample_csv)
    preparator = DataPreparator()
    prep_df, _ = preparator.prepare(df, time_column="timestamp", entity_column="equipment_id")
    
    feat_engine = FeatureEngine()
    feat_df, _ = feat_engine.build_features(
        prep_df,
        target_col="Chiller Energy Consumption (kWh)",
        load_col="Building Load (RT)",
        entity_col="equipment_id",
    )
    
    ml = MLEngine()
    context_features = ["Building Load (RT)", "Outdoor Air Temperature (C)", "feat_hour"]
    model_record = ml.fit_expected_behaviour_model(
        feat_df,
        target_col="Chiller Energy Consumption (kWh)",
        feature_cols=context_features,
        entity_col="equipment_id",
    )
    expected = ml.predict_expected(feat_df, model_record)
    feat_df["_expected"] = expected
    
    residuals, z_scores, _ = ml.compute_contextual_residuals(
        feat_df,
        target_col="Chiller Energy Consumption (kWh)",
        expected_values=expected,
        entity_col="equipment_id",
    )
    feat_df["_residual"] = residuals
    feat_df["_residual_z"] = z_scores
    multi_scores = ml.compute_multivariate_scores(feat_df, context_features)
    
    anomalies = ml.find_persistent_anomaly_windows(
        df=feat_df,
        residuals=residuals,
        residual_z_scores=z_scores,
        multivariate_scores=multi_scores,
        expected_values=expected,
        target_col="Chiller Energy Consumption (kWh)",
        entity_col="equipment_id",
        time_col="timestamp",
        min_persistence=3,
    )
    
    visuals_dir = str(tmp_path / "visuals")
    vis = VisualEngine(visuals_dir=visuals_dir)
    
    chart1 = vis.plot_observed_vs_expected(
        df=feat_df,
        equipment_id="CHILLER-03",
        observed_col="Chiller Energy Consumption (kWh)",
        expected_col="_expected",
    )
    chart2 = vis.plot_residuals(
        df=feat_df,
        equipment_id="CHILLER-03",
        residual_col="_residual",
        z_col="_residual_z",
    )
    schematic = vis.generate_chiller_schematic(equipment_id="CHILLER-03", state_status="CRITICAL ANOMALY")
    
    assert os.path.exists(chart1)
    assert os.path.exists(chart2)
    assert os.path.exists(schematic)
    
    reports_dir = str(tmp_path / "reports")
    rep_engine = ReportEngine(reports_dir=reports_dir)
    report_res = rep_engine.generate_report(
        analysis_id="an-unit-test",
        dataset_name="test_chillers.csv",
        dataset_profile={"row_count": len(df), "data_health_score": 92.5},
        model_metrics=model_record,
        anomalies=anomalies,
        visual_artifacts=[{"title": "Obs vs Exp", "file_path": chart1}],
    )
    
    assert os.path.exists(report_res["markdown_path"])
    assert os.path.exists(report_res["html_path"])
    with open(report_res["markdown_path"], "r", encoding="utf-8") as f:
        content = f.read()
    assert "Engineering Data Intelligence Report" in content
    assert "CHILLER-03" in content
