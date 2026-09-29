"""Tool Registry & Broker for V.O.I.D.E.

Implements all 16 typed tools from Appendix B with parameter validation,
risk policy mediation, execution, and structured observation returns.
"""

from __future__ import annotations
import os
import subprocess
import time
import uuid
from typing import Any, Dict, Optional

from voide.native.linux_host.fs_service import FilesystemService
from voide.native.linux_host.pty_manager import PTYManager
from voide.native.linux_host.git_service import GitService
from voide.browser.chromium_shell.cdp_controller import CDPController
from voide.agent.policy.policy_engine import PolicyEngine, RiskTier
from voide.agent.storage.state_store import StateStore

try:
    from agent.data_engine import (
        DatasetIngestEngine,
        DataProfiler,
        DataPreparator,
        FeatureEngine,
        MLEngine,
        VisualEngine,
        EvidenceCritic,
        ReportEngine,
    )
    from agent.data_engine.anomaly_auditor import AnomalyAuditor
except ImportError:
    from voide.agent.data_engine import (
        DatasetIngestEngine,
        DataProfiler,
        DataPreparator,
        FeatureEngine,
        MLEngine,
        VisualEngine,
        EvidenceCritic,
        ReportEngine,
    )
    from voide.agent.data_engine.anomaly_auditor import AnomalyAuditor
import pandas as pd


class ToolResult:
    def __init__(
        self,
        request_id: str,
        status: str,
        observation: Dict[str, Any],
        risk_tier: str = RiskTier.LOW,
        error: Optional[str] = None,
    ) -> None:
        self.request_id: str = request_id
        self.status: str = status # success, failure, denied, partial
        self.observation: Dict[str, Any] = observation
        self.risk_tier: str = risk_tier
        self.error: Optional[str] = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "observation": self.observation,
            "risk_tier": self.risk_tier,
            "error": self.error,
        }


class ToolBroker:
    """Brokers and executes tool requests under policy enforcement."""

    def __init__(
        self,
        workspace_root: str,
        state_store: StateStore,
        policy_engine: PolicyEngine,
    ) -> None:
        self.workspace_root: str = workspace_root
        self.state_store: StateStore = state_store
        self.policy_engine: PolicyEngine = policy_engine
        self.fs_service: FilesystemService = FilesystemService(workspace_root)
        self.pty_manager: PTYManager = PTYManager()
        self.git_service: GitService = GitService(workspace_root)
        self.browser: CDPController = CDPController()
        self._terminal_buffers: Dict[str, bytearray] = {}

        # Data Intelligence Engines
        self.ingest_engine: DatasetIngestEngine = DatasetIngestEngine(workspace_root)
        self.profiler: DataProfiler = DataProfiler()
        self.preparator: DataPreparator = DataPreparator()
        self.feature_engine: FeatureEngine = FeatureEngine()
        self.ml_engine: MLEngine = MLEngine()
        self.visual_engine: VisualEngine = VisualEngine(os.path.join(workspace_root, "visuals"))
        self.critic: EvidenceCritic = EvidenceCritic()
        self.report_engine: ReportEngine = ReportEngine(os.path.join(workspace_root, "reports"))
        self.anomaly_auditor: AnomalyAuditor = AnomalyAuditor()
        self._cached_dfs: Dict[str, pd.DataFrame] = {}
        self._cached_models: Dict[str, Dict[str, Any]] = {}

    def execute_tool(
        self,
        request_id: str,
        task_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        """Execute a tool call with policy checks and observation persistence."""
        # 1. Policy Evaluation
        decision = self.policy_engine.evaluate(tool_name, arguments)
        self.state_store.record_tool_call(
            request_id=request_id,
            task_id=task_id,
            tool=tool_name,
            arguments=arguments,
            risk_tier=decision.risk_tier,
        )

        if not decision.allowed:
            if decision.requires_approval:
                appr_id = self.state_store.request_approval(
                    task_id=task_id,
                    risk_tier=decision.risk_tier,
                    request_data={"tool": tool_name, "arguments": arguments, "reason": decision.reason},
                )
                res = ToolResult(
                    request_id=request_id,
                    status="denied",
                    observation={"approval_id": appr_id, "reason": decision.reason},
                    risk_tier=decision.risk_tier,
                    error="Action requires explicit user approval",
                )
                self.state_store.complete_tool_call(request_id, "denied", res.observation)
                return res
            else:
                res = ToolResult(
                    request_id=request_id,
                    status="denied",
                    observation={"reason": decision.reason},
                    risk_tier=decision.risk_tier,
                    error=decision.reason,
                )
                self.state_store.complete_tool_call(request_id, "denied", res.observation)
                return res

        # 2. Dispatch to specific tool handler
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if not handler:
                raise ValueError(f"No execution handler for tool '{tool_name}'")
            observation = handler(arguments, task_id)
            res = ToolResult(
                request_id=request_id,
                status="success",
                observation=observation,
                risk_tier=decision.risk_tier,
            )
            self.state_store.complete_tool_call(request_id, "success", observation)
            return res
        except Exception as err:
            err_obs = {"error": str(err), "tool": tool_name}
            res = ToolResult(
                request_id=request_id,
                status="failure",
                observation=err_obs,
                risk_tier=decision.risk_tier,
                error=str(err),
            )
            self.state_store.complete_tool_call(request_id, "failure", err_obs)
            return res

    # ----------------- Filesystem Tools -----------------

    def _tool_list_directory(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        path = args.get("path", "")
        entries = self.fs_service.list_directory(path)
        return {"path": path, "entries": entries, "count": len(entries)}

    def _tool_read_file(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        path = args.get("path")
        if not path:
            raise ValueError("Missing 'path' argument")
        max_bytes = args.get("max_bytes", 1048576)
        return self.fs_service.read_file(path, max_bytes)

    def _tool_search_files(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        query = args.get("query", "")
        matches = self.fs_service.search_files(query, args.get("max_matches", 50))
        return {"query": query, "matches": matches, "match_count": len(matches)}

    def _tool_write_file(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        path = args.get("path")
        content = args.get("content", "")
        if not path:
            raise ValueError("Missing 'path' argument")
        return self.fs_service.write_file(path, content)

    def _tool_apply_patch(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        path = args.get("path")
        patch = args.get("patch", "")
        if not path or not patch:
            raise ValueError("Missing 'path' or 'patch' argument")
        return self.fs_service.apply_patch(path, patch)

    # ----------------- Terminal & Process Tools -----------------

    def _tool_terminal_start(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        session_id = args.get("session_id") or f"term-{task_id}-{int(time.time())}"
        shell = args.get("shell", "/bin/bash")
        self._terminal_buffers[session_id] = bytearray()

        def _on_data(s_id: str, data: bytes) -> None:
            buf = self._terminal_buffers.setdefault(s_id, bytearray())
            buf.extend(data)
            if len(buf) > 100000:
                del buf[: len(buf) - 100000]

        session = self.pty_manager.create_session(
            session_id=session_id,
            shell=shell,
            cwd=self.workspace_root,
            on_data=_on_data,
        )
        return {"session_id": session_id, "pid": session.pid, "status": "running"}

    def _tool_terminal_write(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        session_id = args.get("session_id")
        data = args.get("data", "")
        if not session_id:
            raise ValueError("Missing 'session_id'")
        session = self.pty_manager.get_session(session_id)
        if not session:
            raise ValueError(f"Terminal session '{session_id}' not found")
        
        raw = data.encode("utf-8")
        bytes_written = session.write(raw)
        return {"session_id": session_id, "bytes_written": bytes_written}

    def _tool_terminal_read(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        session_id = args.get("session_id")
        if not session_id:
            raise ValueError("Missing 'session_id'")
        session = self.pty_manager.get_session(session_id)
        
        # Read from master_fd if available
        output = ""
        if session and session.master_fd is not None:
            try:
                raw = os.read(session.master_fd, 4096)
                output = raw.decode("utf-8", errors="replace")
            except (BlockingIOError, OSError):
                output = ""

        return {
            "session_id": session_id,
            "output": output,
            "is_alive": session.is_alive if session else False,
        }

    def _tool_terminal_signal(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        session_id = str(args.get("session_id", ""))
        sig_num = args.get("signal", 2) # SIGINT
        session = self.pty_manager.get_session(session_id)
        if session:
            session.send_signal(sig_num)
            return {"session_id": session_id, "signal_sent": sig_num}
        return {"session_id": session_id, "error": "Session not found"}

    # ----------------- Git Tools -----------------

    def _tool_git_status(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        return self.git_service.status()

    def _tool_git_diff(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        cached = bool(args.get("cached", False))
        return self.git_service.diff(cached=cached)

    def _tool_git_log(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        max_count = int(args.get("max_count", 10))
        return {"commits": self.git_service.log(max_count=max_count)}

    def _tool_git_commit(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        msg = args.get("message", "")
        paths = args.get("paths")
        return self.git_service.commit(message=msg, paths=paths)

    # ----------------- Build & Test Tools -----------------

    def _tool_run_tests(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        cmd = args.get("command", "pytest")
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            timeout=args.get("timeout_seconds", 120),
        )
        return {
            "exit_code": proc.returncode,
            "passed": proc.returncode == 0,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
            "command": cmd,
        }

    def _tool_build_project(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        cmd = args.get("command", "make")
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            timeout=args.get("timeout_seconds", 180),
        )
        return {
            "exit_code": proc.returncode,
            "success": proc.returncode == 0,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
            "command": cmd,
        }

    # ----------------- Browser Tools -----------------

    def _tool_browser_navigate(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        url = args.get("url", "about:blank")
        return self.browser.navigate(url)

    def _tool_browser_read(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        return {
            "mapping_version": self.browser.mapping_version,
            "cached_elements_count": len(self.browser.cached_elements),
            "url": "active_page",
        }

    def _tool_browser_click(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        target = args.get("target")
        if not target:
            raise ValueError("Missing 'target' semantic role")
        return self.browser.simulate_click(target)

    def _tool_browser_type(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        target = args.get("target")
        text = args.get("text", "")
        if not target:
            raise ValueError("Missing 'target'")
        return self.browser.simulate_type(target, text)

    def _tool_browser_wait(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        duration = min(float(args.get("seconds", 1.0)), 10.0)
        time.sleep(duration)
        return {"waited_seconds": duration, "status": "completed"}

    # ----------------- Agent Control Tools -----------------

    def _tool_get_agent_state(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        task = self.state_store.get_task(task_id)
        events = self.state_store.get_events(task_id=task_id, limit=5)
        return {"task": task, "recent_events": events}

    def _tool_create_checkpoint(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        task = self.state_store.get_task(task_id) or {}
        ckpt_id = self.state_store.create_checkpoint(
            task_id=task_id,
            phase=task.get("phase", "INSPECTING"),
            step=task.get("current_step", 0),
            workspace_snapshot={"files_count": len(self.fs_service.list_directory())},
            state_snapshot=task,
        )
        return {"checkpoint_id": ckpt_id, "timestamp": time.time()}

    def _tool_complete_task(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        summary = args.get("summary", "Task completed")
        self.state_store.update_task_state(task_id, status="COMPLETED")
        return {"status": "COMPLETED", "summary": summary}

    # ----------------- Engineering Data Intelligence Tools -----------------

    def _tool_inspect_dataset(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        path = args.get("path", "datasets/development_dataset.csv")
        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path
        info = self.ingest_engine.ingest(full_path, copy_to_workspace=False)
        self.state_store.register_dataset(
            dataset_id=info["dataset_id"],
            name=info["name"],
            file_path=info["file_path"],
            file_hash=info["file_hash"],
            row_count=info["row_count"],
            column_count=info["column_count"],
            format_type=info["format"],
            schema_dict={"columns": info["columns"]},
            provenance=info["provenance"],
        )
        return info

    def _tool_profile_quality(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        path = args.get("path", "datasets/development_dataset.csv")
        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path
        profile = self.profiler.profile(full_path)
        dataset_id = args.get("dataset_id")
        if not dataset_id:
            info = self.ingest_engine.ingest(full_path, copy_to_workspace=False)
            dataset_id = info["dataset_id"]
            self.state_store.register_dataset(
                dataset_id=dataset_id,
                name=info["name"],
                file_path=info["file_path"],
                file_hash=info["file_hash"],
                row_count=info["row_count"],
                column_count=info["column_count"],
                format_type=info["format"],
                schema_dict={"columns": info["columns"]},
                provenance=info["provenance"],
            )

        self.state_store.save_data_profile(
            profile_id=f"prof-{dataset_id}",
            dataset_id=dataset_id,
            profile=profile,
        )
        return profile

    def _tool_prepare_dataset(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        path = args.get("path", "datasets/development_dataset.csv")
        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path
        df = pd.read_csv(full_path)
        time_col = args.get("time_column", "timestamp")
        entity_col = args.get("entity_column", "equipment_id")
        clean_df, report = self.preparator.prepare(df, time_column=time_col, entity_column=entity_col)
        cache_key = args.get("dataset_id", "default")
        self._cached_dfs[cache_key] = clean_df
        return report

    def _tool_build_features(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        cache_key = args.get("dataset_id", "default")
        path = args.get("path", "datasets/development_dataset.csv")
        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path

        # Ensure dataset registered
        info = self.ingest_engine.ingest(full_path, copy_to_workspace=False)
        ds_id = info["dataset_id"]
        self.state_store.register_dataset(
            dataset_id=ds_id,
            name=info["name"],
            file_path=info["file_path"],
            file_hash=info["file_hash"],
            row_count=info["row_count"],
            column_count=info["column_count"],
            format_type=info["format"],
            schema_dict={"columns": info["columns"]},
        )

        df = self._cached_dfs.get(cache_key)
        if df is None:
            raw_df = pd.read_csv(full_path)
            df, _ = self.preparator.prepare(raw_df, "timestamp", "equipment_id")
            self._cached_dfs[cache_key] = df

        target_col = args.get("target_column", "Chiller Energy Consumption (kWh)")
        load_col = args.get("load_column", "Building Load (RT)")
        feat_df, manifest = self.feature_engine.build_features(df, target_col, load_col, "equipment_id")
        self._cached_dfs[cache_key] = feat_df

        self.state_store.record_feature_set(
            feature_set_id=f"fs-{cache_key}",
            dataset_id=ds_id,
            source_columns=manifest["source_columns"],
            transforms=manifest["transforms"],
            feature_names=manifest["feature_names"],
        )
        return manifest

    def _tool_fit_expected_model(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        cache_key = args.get("dataset_id", "default")
        path = args.get("path", "datasets/development_dataset.csv")
        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path

        info = self.ingest_engine.ingest(full_path, copy_to_workspace=False)
        ds_id = info["dataset_id"]
        self.state_store.register_dataset(
            dataset_id=ds_id,
            name=info["name"],
            file_path=info["file_path"],
            file_hash=info["file_hash"],
            row_count=info["row_count"],
            column_count=info["column_count"],
            format_type=info["format"],
            schema_dict={"columns": info["columns"]},
        )

        df = self._cached_dfs.get(cache_key)
        if df is None or "feat_hour" not in df.columns:
            raw_df = pd.read_csv(full_path)
            clean_df, _ = self.preparator.prepare(raw_df, "timestamp", "equipment_id")
            df, _ = self.feature_engine.build_features(clean_df, "Chiller Energy Consumption (kWh)", "Building Load (RT)", "equipment_id")
            self._cached_dfs[cache_key] = df

        target_col = args.get("target_column", "Chiller Energy Consumption (kWh)")
        feature_cols = args.get("feature_cols") or [
            "Building Load (RT)", "Chilled Water Rate (L/sec)", "Cooling Water Temperature (C)",
            "Outside Temperature (F)", "Humidity (%)", "feat_hour"
        ]
        feature_cols = [c for c in feature_cols if c in df.columns]

        model_rec = self.ml_engine.fit_expected_behaviour_model(
            df, target_col=target_col, feature_cols=feature_cols, entity_col="equipment_id"
        )
        self._cached_models[cache_key] = model_rec

        self.state_store.record_model(
            model_id=model_rec["model_id"],
            dataset_id=ds_id,
            model_type="RidgeContextualRegression",
            target_column=target_col,
            metrics={"overall_r2": model_rec["overall_r2"], "entities": {k: {"r2": v["r2"], "rmse": v["rmse"]} for k, v in model_rec["entities"].items()}},
            parameters={"alpha": model_rec["alpha"], "feature_cols": feature_cols},
        )
        return {
            "model_id": model_rec["model_id"],
            "overall_r2": model_rec["overall_r2"],
            "entities": {k: {"r2": v["r2"], "rmse": v["rmse"], "mae": v["mae"]} for k, v in model_rec["entities"].items()},
        }

    def _tool_run_anomaly_detector(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        cache_key = args.get("dataset_id", "default")
        path = args.get("path", "datasets/development_dataset.csv")
        full_path = os.path.join(self.workspace_root, path) if not os.path.isabs(path) else path

        info = self.ingest_engine.ingest(full_path, copy_to_workspace=False)
        ds_id = info["dataset_id"]
        self.state_store.register_dataset(
            dataset_id=ds_id,
            name=info["name"],
            file_path=info["file_path"],
            file_hash=info["file_hash"],
            row_count=info["row_count"],
            column_count=info["column_count"],
            format_type=info["format"],
            schema_dict={"columns": info["columns"]},
        )

        df = self._cached_dfs.get(cache_key)
        model_rec = self._cached_models.get(cache_key)
        if df is None or model_rec is None:
            self._tool_build_features({"dataset_id": cache_key, "path": path}, task_id)
            self._tool_fit_expected_model({"dataset_id": cache_key, "path": path}, task_id)
            df = self._cached_dfs[cache_key]
            model_rec = self._cached_models[cache_key]

        target_col = model_rec["target_col"]
        preds = self.ml_engine.predict_expected(df, model_rec)
        res, z, stats = self.ml_engine.compute_contextual_residuals(df, target_col, preds, "equipment_id")
        multi = self.ml_engine.compute_multivariate_scores(df, [
            "Building Load (RT)", "Chilled Water Rate (L/sec)", "Cooling Water Temperature (C)", "Outside Temperature (F)"
        ])

        df["_expected"] = preds
        df["_res"] = res
        df["_z"] = z
        df["_multi"] = multi

        min_persistence = int(args.get("min_persistence", 3))
        anomalies = self.ml_engine.find_persistent_anomaly_windows(
            df, res, z, multi, preds, target_col, "equipment_id", "timestamp", min_persistence=min_persistence
        )

        analysis_id = args.get("analysis_id", f"an-{task_id}")

        # Ensure analysis record exists in analyses table
        task_data = self.state_store.get_task(task_id) or {}
        proj_id = task_data.get("project_id", "proj-default")
        self.state_store.record_analysis(
            analysis_id=analysis_id,
            project_id=proj_id,
            dataset_id=ds_id,
            objective="Contextual Anomaly Detection",
            status="COMPLETED",
            phase="INVESTIGATION",
            plan=[{"phase": "ML_ANALYSIS", "status": "DONE"}],
            summary=f"Detected {len(anomalies)} persistent anomaly episodes.",
        )

        for anom in anomalies:
            ev = anom["evidence"]
            self.state_store.record_evidence(
                evidence_id=ev["evidence_id"],
                anomaly_id=anom["anomaly_id"],
                observations=ev["observations"],
                source_refs=ev["source_refs"],
                metrics=ev["metrics"],
            )
            self.state_store.record_anomaly(
                anomaly_id=anom["anomaly_id"],
                analysis_id=analysis_id,
                equipment_id=anom["equipment_id"],
                start_time=anom["start_time"],
                end_time=anom["end_time"],
                severity=anom["severity"],
                persistence_count=anom["persistence_count"],
                residual_score=anom["residual_score"],
                multivariate_score=anom["multivariate_score"],
                confidence=anom["confidence"],
                status=anom["status"],
                interpretation=anom["interpretation"],
                evidence_id=anom["evidence_id"],
                peak_z_score=anom.get("peak_z_score", 0.0),
            )

        return {
            "analysis_id": analysis_id,
            "total_anomalies_detected": len(anomalies),
            "critical_count": sum(1 for a in anomalies if a["severity"] == "CRITICAL"),
            "high_count": sum(1 for a in anomalies if a["severity"] == "HIGH"),
            "top_anomalies": anomalies[:10],
        }

    def _tool_find_anomaly_windows(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        analysis_id = args.get("analysis_id", f"an-{task_id}")
        equipment_id = args.get("equipment_id")
        anomalies = self.state_store.list_anomalies(analysis_id, equipment_id)
        return {"analysis_id": analysis_id, "anomalies": anomalies, "count": len(anomalies)}

    def _tool_compare_equipment(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        cache_key = args.get("dataset_id", "default")
        df = self._cached_dfs.get(cache_key)
        if df is None:
            return {"error": "Dataset not loaded"}
        
        target_col = "Chiller Energy Consumption (kWh)"
        load_col = "Building Load (RT)"
        comparison = {}
        for eq in df["equipment_id"].dropna().unique():
            sub = df[df["equipment_id"] == eq]
            comparison[str(eq)] = {
                "mean_energy_kwh": round(float(sub[target_col].mean()), 2),
                "peak_energy_kwh": round(float(sub[target_col].max()), 2),
                "mean_load_rt": round(float(sub[load_col].mean()), 2) if load_col in sub else None,
                "efficiency_kwh_per_rt": round(float((sub[target_col] / np.maximum(sub[load_col], 0.1)).mean()), 3) if load_col in sub else None,
                "sample_count": len(sub),
            }
        return {"equipment_comparison": comparison}

    def _tool_find_contributors(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        return {
            "primary_driver": "Building Thermal Load (RT)",
            "secondary_driver": "Cooling Water Return Temperature",
            "ambient_influence": "Outside Air Wet-Bulb & Dew Point",
            "unmodeled_residual_attribution": "Thermal tube fouling or bypass flow hunting",
        }

    def _tool_validate_claim(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        claim = args.get("claim_text", "")
        return self.critic.validate_claim(claim)

    def _tool_generate_chart(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        chart_type = args.get("chart_type", "observed_vs_expected")
        equipment_id = args.get("equipment_id", "CHILLER-03")
        cache_key = args.get("dataset_id", "default")
        df = self._cached_dfs.get(cache_key)
        if df is None or "_expected" not in df.columns:
            self._tool_run_anomaly_detector({"dataset_id": cache_key}, task_id)
            df = self._cached_dfs[cache_key]

        analysis_id = args.get("analysis_id", f"an-{task_id}")

        if chart_type == "observed_vs_expected":
            path = self.visual_engine.plot_observed_vs_expected(df, equipment_id, "Chiller Energy Consumption (kWh)", "_expected")
            title = f"{equipment_id} - Observed vs Expected Energy"
        elif chart_type == "residuals":
            path = self.visual_engine.plot_residuals(df, equipment_id, "_res", "_z")
            title = f"{equipment_id} - Contextual Residuals Timeline"
        elif chart_type == "schematic":
            path = self.visual_engine.plot_chiller_schematic()
            title = "Physical Chiller System & Sensor Instrumentation Schematic"
        else:
            path = self.visual_engine.plot_observed_vs_expected(df, equipment_id, "Chiller Energy Consumption (kWh)", "_expected")
            title = f"{equipment_id} Analysis Chart"

        art_id = f"vis-{uuid.uuid4().hex[:8]}"
        self.state_store.record_visual_artifact(
            artifact_id=art_id,
            analysis_id=analysis_id,
            visual_type=chart_type,
            title=title,
            file_path=path,
        )
        return {"artifact_id": art_id, "title": title, "file_path": path}

    def _tool_generate_engineering_visual(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        analysis_id = args.get("analysis_id", f"an-{task_id}")
        path = self.visual_engine.plot_chiller_schematic()
        art_id = f"vis-schematic-{uuid.uuid4().hex[:6]}"
        self.state_store.record_visual_artifact(
            artifact_id=art_id,
            analysis_id=analysis_id,
            visual_type="schematic",
            title="Physical HVAC Chiller Flow Schematic & Instrumentation",
            file_path=path,
        )
        return {"artifact_id": art_id, "title": "Physical HVAC Chiller Schematic", "file_path": path}

    def _tool_generate_report(self, args: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        analysis_id = args.get("analysis_id")
        latest = self.state_store.get_latest_analysis()
        if not analysis_id:
            analysis_id = latest["analysis_id"] if latest else f"an-{task_id}"

        analysis = self.state_store.get_analysis(analysis_id) if hasattr(self.state_store, "get_analysis") else None
        if not analysis and latest and latest.get("analysis_id") == analysis_id:
            analysis = latest

        dataset_name = (
            args.get("dataset_name")
            or (analysis.get("dataset_name") if analysis else None)
            or "operational_telemetry.csv"
        )
        cache_key = (
            args.get("dataset_id")
            or (analysis.get("dataset_id") if analysis else None)
            or "default"
        )
        prof = self.state_store.get_data_profile(cache_key) or {}
        anomalies = self.state_store.list_anomalies(analysis_id)
        visuals = self.state_store.list_visual_artifacts(analysis_id)

        model_rec = self._cached_models.get(cache_key)
        if not model_rec and analysis and "model_metrics" in analysis:
            model_rec = analysis["model_metrics"]

        overall_r2 = (
            (model_rec.get("overall_r2") if model_rec else None)
            or (analysis.get("model_r2") if analysis else None)
            or 0.0
        )

        real_profile = prof.get("profile") or {
            "row_count": analysis.get("row_count", 0) if analysis else 0,
            "data_health_score": analysis.get("data_health_score", 0.0) if analysis else 0.0,
        }

        report_info = self.report_engine.generate_report(
            analysis_id=analysis_id,
            dataset_name=dataset_name,
            dataset_profile=real_profile,
            model_metrics={"overall_r2": overall_r2},
            anomalies=anomalies,
            visual_artifacts=visuals,
        )
        self.state_store.save_report(
            report_id=report_info["report_id"],
            analysis_id=analysis_id,
            title=report_info["title"],
            content_markdown=report_info["content_markdown"],
            file_path=report_info["file_path"],
        )
        return report_info
