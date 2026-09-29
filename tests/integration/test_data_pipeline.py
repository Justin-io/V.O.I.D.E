"""Integration Tests for V.O.I.D.E. Data Intelligence Pipeline & IPC Bridge."""

import asyncio
import json
import os
import tempfile
import numpy as np
import pandas as pd
import pytest
import websockets

from voide.agent.policy.policy_engine import PolicyEngine
from voide.agent.runtime.ipc_server import IPCServer
from voide.agent.storage.state_store import StateStore
from voide.agent.tools.tool_registry import ToolBroker


@pytest.fixture
def test_dataset(tmp_path):
    """Generate a realistic HVAC chiller multi-channel time series dataset for testing."""
    np.random.seed(42)
    n = 300
    dates = pd.date_range("2026-06-01 00:00:00", periods=n, freq="30min")

    dfs = []
    for eq_id in ["CHILLER-01", "CHILLER-02", "CHILLER-03"]:
        load = np.random.uniform(300.0, 500.0, size=n)
        temp_out = np.random.uniform(20.0, 35.0, size=n)
        hour = np.array([d.hour for d in dates])
        
        # Expected energy: 0.22 * load + 0.5 * temp + noise
        energy = 0.22 * load + 0.5 * temp_out + 0.1 * hour + np.random.normal(0, 1.5, size=n)
        
        # Inject persistent contextual anomaly on CHILLER-03
        if eq_id == "CHILLER-03":
            energy[100:110] += 50.0  # +50 kWh unexpected lift

        df_eq = pd.DataFrame({
            "timestamp": dates.astype(str),
            "equipment_id": eq_id,
            "Chilled Water Rate (L/sec)": np.random.uniform(70.0, 95.0, size=n).round(1),
            "Cooling Water Temperature (C)": np.random.uniform(28.0, 33.0, size=n).round(1),
            "Building Load (RT)": load.round(1),
            "Chiller Energy Consumption (kWh)": energy.round(1),
            "Outside Temperature (F)": (temp_out * 1.8 + 32).round(1),
            "Dew Point (F)": np.random.uniform(60.0, 75.0, size=n).round(1),
            "Humidity (%)": np.random.uniform(60.0, 90.0, size=n).round(1),
            "Wind Speed (mph)": np.random.uniform(3.0, 15.0, size=n).round(1),
            "Pressure (in)": np.random.uniform(29.7, 30.1, size=n).round(2),
        })
        dfs.append(df_eq)

    full_df = pd.concat(dfs, ignore_index=True)
    csv_path = str(tmp_path / "test_hvac_chillers.csv")
    full_df.to_csv(csv_path, index=False)
    return csv_path


def test_tool_broker_data_pipeline_execution(test_dataset, tmp_path):
    """Verify ToolBroker data intelligence tools execute and persist state properly."""
    workspace_root = str(tmp_path / "workspace")
    os.makedirs(workspace_root, exist_ok=True)
    db_path = os.path.join(workspace_root, ".voide", "state.db")
    state_store = StateStore(db_path)
    policy_engine = PolicyEngine(workspace_root)
    broker = ToolBroker(workspace_root, state_store, policy_engine)

    proj_id = state_store.register_project(workspace_root, "TestDataProject")
    task_id = state_store.create_task(
        project_id=proj_id,
        objective="Data Intelligence Pipeline Test",
        workspace=workspace_root,
    )
    analysis_id = "an-integration-test"

    # 1. inspect_dataset
    res_inspect = broker.execute_tool(
        request_id="req-1",
        task_id=task_id,
        tool_name="inspect_dataset",
        arguments={"path": test_dataset},
    )
    assert res_inspect.status == "success"
    assert res_inspect.observation["row_count"] == 900
    assert res_inspect.observation["column_count"] == 11
    ds_id = res_inspect.observation["dataset_id"]

    # Verify StateStore dataset registration
    ds_rec = state_store.get_dataset(ds_id)
    assert ds_rec is not None
    assert ds_rec["row_count"] == 900

    # 2. profile_quality
    res_profile = broker.execute_tool(
        request_id="req-2",
        task_id=task_id,
        tool_name="profile_quality",
        arguments={"path": test_dataset, "dataset_id": ds_id},
    )
    assert res_profile.status == "success"
    assert res_profile.observation["data_health_score"] > 80.0
    assert "CHILLER-01" in res_profile.observation["entity_summary"]["entities"]

    # 3. prepare_dataset
    res_prep = broker.execute_tool(
        request_id="req-3",
        task_id=task_id,
        tool_name="prepare_dataset",
        arguments={"path": test_dataset, "dataset_id": ds_id},
    )
    assert res_prep.status == "success"
    assert res_prep.observation["prepared_rows"] == 900

    # 4. build_features
    res_feat = broker.execute_tool(
        request_id="req-4",
        task_id=task_id,
        tool_name="build_features",
        arguments={
            "dataset_id": ds_id,
            "path": test_dataset,
            "target_column": "Chiller Energy Consumption (kWh)",
            "load_column": "Building Load (RT)",
        },
    )
    assert res_feat.status == "success"
    assert "feat_hour" in res_feat.observation["feature_names"]

    # 5. fit_expected_model
    res_model = broker.execute_tool(
        request_id="req-5",
        task_id=task_id,
        tool_name="fit_expected_model",
        arguments={
            "dataset_id": ds_id,
            "path": test_dataset,
            "target_column": "Chiller Energy Consumption (kWh)",
        },
    )
    assert res_model.status == "success"
    assert res_model.observation["overall_r2"] > 0.60
    assert "CHILLER-03" in res_model.observation["entities"]

    # 6. run_anomaly_detector
    res_anom = broker.execute_tool(
        request_id="req-6",
        task_id=task_id,
        tool_name="run_anomaly_detector",
        arguments={
            "dataset_id": ds_id,
            "path": test_dataset,
            "analysis_id": analysis_id,
            "min_persistence": 3,
        },
    )
    assert res_anom.status == "success"
    assert res_anom.observation["total_anomalies_detected"] >= 1
    anomalies = state_store.list_anomalies(analysis_id)
    assert len(anomalies) >= 1

    # Verify Evidence object persisted in StateStore
    first_anom = anomalies[0]
    assert first_anom["evidence_id"] is not None
    ev_rec = state_store.get_evidence(first_anom["evidence_id"])
    assert ev_rec is not None
    assert "observations" in ev_rec

    # 7. validate_claim via Evidence Critic
    res_critic = broker.execute_tool(
        request_id="req-7",
        task_id=task_id,
        tool_name="validate_claim",
        arguments={"claim_text": "Chiller 3 compressor motor mechanical failure confirmed."},
    )
    assert res_critic.status == "success"
    assert res_critic.observation["has_unsupported_fault_attribution"]
    assert res_critic.observation["status"] == "REWRITTEN"

    # 8. generate_chart
    res_chart = broker.execute_tool(
        request_id="req-8",
        task_id=task_id,
        tool_name="generate_chart",
        arguments={
            "chart_type": "observed_vs_expected",
            "equipment_id": "CHILLER-03",
            "dataset_id": ds_id,
            "analysis_id": analysis_id,
        },
    )
    assert res_chart.status == "success"
    assert os.path.exists(res_chart.observation["file_path"])

    # 9. generate_engineering_visual (schematic)
    res_schematic = broker.execute_tool(
        request_id="req-9",
        task_id=task_id,
        tool_name="generate_engineering_visual",
        arguments={"analysis_id": analysis_id},
    )
    assert res_schematic.status == "success"
    assert os.path.exists(res_schematic.observation["file_path"])

    # 10. generate_report
    res_rep = broker.execute_tool(
        request_id="req-10",
        task_id=task_id,
        tool_name="generate_report",
        arguments={
            "analysis_id": analysis_id,
            "dataset_name": "test_hvac_chillers.csv",
            "dataset_id": ds_id,
        },
    )
    assert res_rep.status == "success"
    assert os.path.exists(res_rep.observation["file_path"])

    # Verify report in StateStore
    saved_rep = state_store.get_report(analysis_id)
    assert saved_rep is not None
    assert "Engineering Intelligence Report" in saved_rep["title"]


async def _async_test_run_demo_pipeline_websocket(csv_path):
    with tempfile.TemporaryDirectory() as tmpdir:
        port = 8798
        server = IPCServer(workspace_root=tmpdir, host="127.0.0.1", port=port)
        server_task = asyncio.create_task(server.start())
        await asyncio.sleep(0.2)

        try:
            uri = f"ws://127.0.0.1:{port}"
            async with websockets.connect(uri) as ws:
                # 1. HELLO greeting
                hello_raw = await ws.recv()
                hello = json.loads(hello_raw)
                assert hello["type"] == "HELLO"

                # 2. Trigger run_demo_pipeline
                analysis_id = "an-demo-e2e"
                await ws.send(json.dumps({
                    "action": "run_demo_pipeline",
                    "id": "100",
                    "payload": {
                        "path": csv_path,
                        "analysis_id": analysis_id,
                    },
                }))

                # Collect broadcasts until final RESPONSE
                stages_received = []
                response_msg = None

                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    msg = json.loads(raw)
                    if msg.get("type") == "DATA_PIPELINE_STAGE":
                        stages_received.append(msg["stage"])
                    elif msg.get("type") == "RESPONSE" and msg.get("id") == "100":
                        response_msg = msg
                        break

                assert response_msg is not None
                assert response_msg["success"] is True
                res = response_msg["result"]
                assert res["status"] == "COMPLETED"
                assert res["analysis_id"] == analysis_id
                assert res["row_count"] == 900
                assert res["model_r2"] > 0.60
                assert res["total_anomalies"] >= 1
                assert res["visual_artifacts_count"] >= 3
                assert os.path.exists(res["report_path"])

                # Check expected pipeline stages were broadcast
                for expected_stage in ["INGESTION", "PROFILING", "PREPARATION", "FEATURE_ENGINEERING", "ML_BASELINE", "ANOMALY_DETECTION", "CRITIC_VERIFICATION", "VISUALS_AND_REPORT", "COMPLETED"]:
                    assert expected_stage in stages_received

                # 3. Query get_anomalies
                await ws.send(json.dumps({
                    "action": "get_anomalies",
                    "id": "101",
                    "payload": {"analysis_id": analysis_id},
                }))
                anom_resp = json.loads(await ws.recv())
                assert anom_resp["success"] is True
                assert len(anom_resp["result"]) >= 1

                # 4. Query get_visual_artifacts
                await ws.send(json.dumps({
                    "action": "get_visual_artifacts",
                    "id": "102",
                    "payload": {"analysis_id": analysis_id},
                }))
                vis_resp = json.loads(await ws.recv())
                assert vis_resp["success"] is True
                assert len(vis_resp["result"]) >= 3

                # 5. Query get_report
                await ws.send(json.dumps({
                    "action": "get_report",
                    "id": "103",
                    "payload": {"analysis_id": analysis_id},
                }))
                rep_resp = json.loads(await ws.recv())
                assert rep_resp["success"] is True
                assert rep_resp["result"]["analysis_id"] == analysis_id
                assert "Engineering Intelligence Report" in rep_resp["result"]["title"]

        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass


def test_ipc_server_data_pipeline_e2e(test_dataset):
    """Verify WebSocket IPC server runs demo pipeline end-to-end with live stage broadcasts."""
    asyncio.run(_async_test_run_demo_pipeline_websocket(test_dataset))
