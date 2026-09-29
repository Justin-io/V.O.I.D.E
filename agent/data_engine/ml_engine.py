"""ML Intelligence Engine for V.O.I.D.E.

Pure, vectorized numpy/pandas implementations for:
1. Expected-behaviour Ridge regression
2. Contextual residual calculation
3. Multivariate Mahalanobis operational anomaly scoring
4. Temporal persistence sequence clustering
5. Multi-signal evidence fusion
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class MLEngine:
    """Zero-dependency, deterministic ML and evidence fusion engine."""

    def __init__(self) -> None:
        self.models: Dict[str, Dict[str, Any]] = {}

    def fit_expected_behaviour_model(
        self,
        df: pd.DataFrame,
        target_col: str,
        feature_cols: List[str],
        entity_col: Optional[str] = None,
        alpha: float = 1.0,
    ) -> Dict[str, Any]:
        """Fit regularized linear models predicting expected target behaviour from operating context."""
        valid_df = df.dropna(subset=[target_col] + feature_cols).copy()
        if len(valid_df) < 20:
            raise ValueError(f"Insufficient samples to fit model: {len(valid_df)}")

        entities = valid_df[entity_col].unique() if entity_col and entity_col in valid_df.columns else [None]

        trained_entities: Dict[str, Dict[str, Any]] = {}
        total_ss_res = 0.0
        total_ss_tot = 0.0

        for ent in entities:
            if ent is not None:
                ent_df = valid_df[valid_df[entity_col] == ent]
            else:
                ent_df = valid_df

            X_raw = ent_df[feature_cols].values
            y = ent_df[target_col].values

            # Normalize features
            x_mean = np.mean(X_raw, axis=0)
            x_std = np.std(X_raw, axis=0)
            x_std[x_std == 0.0] = 1.0
            X_norm = (X_raw - x_mean) / x_std

            # Add bias/intercept column
            N = len(X_norm)
            X = np.hstack([np.ones((N, 1)), X_norm])

            # Ridge regression: w = (X^T X + alpha * I)^(-1) X^T y
            p = X.shape[1]
            reg_eye = np.eye(p) * alpha
            reg_eye[0, 0] = 0.0  # Do not regularize intercept

            try:
                w = np.linalg.solve(X.T @ X + reg_eye, X.T @ y)
            except np.linalg.LinAlgError:
                w, _, _, _ = np.linalg.lstsq(X, y, rcond=None)

            y_pred = X @ w
            residuals = y - y_pred

            ss_res = float(np.sum(residuals**2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            r2 = 1.0 - (ss_res / max(ss_tot, 1e-6))
            rmse = float(np.sqrt(np.mean(residuals**2)))
            mae = float(np.mean(np.abs(residuals)))

            total_ss_res += ss_res
            total_ss_tot += ss_tot

            y_mean = float(np.mean(y))
            cv_rmse = round((rmse / max(abs(y_mean), 1e-6)) * 100.0, 2)
            nmbe = round((float(np.sum(residuals)) / max((N - 1) * y_mean, 1e-6)) * 100.0, 2)

            key = str(ent) if ent is not None else "GLOBAL"
            trained_entities[key] = {
                "weights": w.tolist(),
                "x_mean": x_mean.tolist(),
                "x_std": x_std.tolist(),
                "r2": round(r2, 4),
                "rmse": round(rmse, 4),
                "mae": round(mae, 4),
                "cv_rmse": cv_rmse,
                "nmbe": nmbe,
                "ashrae_compliant": bool(cv_rmse <= 30.0 and abs(nmbe) <= 10.0),
                "residual_mean": float(np.mean(residuals)),
                "residual_std": float(np.std(residuals)),
                "sample_count": N,
            }

        overall_r2 = 1.0 - (total_ss_res / max(total_ss_tot, 1e-6))

        model_id = f"model-expected-{uuid.uuid4().hex[:8]}"
        model_record = {
            "model_id": model_id,
            "target_col": target_col,
            "feature_cols": feature_cols,
            "entity_col": entity_col,
            "entities": trained_entities,
            "overall_r2": round(overall_r2, 4),
            "alpha": alpha,
        }
        self.models[model_id] = model_record
        return model_record

    def predict_expected(
        self,
        df: pd.DataFrame,
        model_record: Dict[str, Any],
    ) -> np.ndarray:
        """Predict expected target values using trained entity models."""
        target_col = model_record["target_col"]
        feature_cols = model_record["feature_cols"]
        entity_col = model_record["entity_col"]
        models_by_entity = model_record["entities"]

        preds = np.zeros(len(df))

        entities = df[entity_col].unique() if entity_col and entity_col in df.columns else [None]

        for ent in entities:
            key = str(ent) if ent is not None else "GLOBAL"
            m = models_by_entity.get(key) or models_by_entity.get("GLOBAL")
            if not m:
                continue

            if ent is not None:
                mask = (df[entity_col] == ent).values
            else:
                mask = np.ones(len(df), dtype=bool)

            if not np.any(mask):
                continue

            sub_df = df[mask]
            X_raw = sub_df[feature_cols].fillna(0.0).values
            x_mean = np.array(m["x_mean"])
            x_std = np.array(m["x_std"])
            X_norm = (X_raw - x_mean) / x_std

            N = len(X_norm)
            X = np.hstack([np.ones((N, 1)), X_norm])
            w = np.array(m["weights"])
            preds[mask] = X @ w

        return preds

    def compute_contextual_residuals(
        self,
        df: pd.DataFrame,
        target_col: str,
        expected_values: np.ndarray,
        entity_col: Optional[str] = None,
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """Calculate contextual residual and normalized z-scores per entity."""
        observed = df[target_col].fillna(0.0).values
        residuals = observed - expected_values

        z_scores = np.zeros_like(residuals)

        entity_stats: Dict[str, Dict[str, float]] = {}
        entities = df[entity_col].unique() if entity_col and entity_col in df.columns else [None]

        for ent in entities:
            if ent is not None:
                mask = (df[entity_col] == ent).values
            else:
                mask = np.ones(len(df), dtype=bool)

            ent_res = residuals[mask]
            res_mean = float(np.mean(ent_res))
            res_std = float(np.std(ent_res))
            if res_std <= 0.0:
                res_std = 1.0

            z_scores[mask] = (ent_res - res_mean) / res_std
            key = str(ent) if ent is not None else "GLOBAL"
            entity_stats[key] = {
                "residual_mean": round(res_mean, 3),
                "residual_std": round(res_std, 3),
            }

        return residuals, z_scores, entity_stats

    def compute_multivariate_scores(
        self,
        df: pd.DataFrame,
        operational_cols: List[str],
    ) -> np.ndarray:
        """Compute multivariate Mahalanobis distance metric across operating features."""
        valid_cols = [c for c in operational_cols if c in df.columns]
        if not valid_cols:
            return np.zeros(len(df))

        X = df[valid_cols].fillna(df[valid_cols].median()).values
        d = X.shape[1]

        mu = np.mean(X, axis=0)
        cov = np.cov(X, rowvar=False)

        # Ridge regularize covariance matrix for stable inversion
        if d == 1:
            cov_inv = np.array([[1.0 / max(float(cov), 1e-4)]])
        else:
            cov_reg = cov + np.eye(d) * 1e-4
            try:
                cov_inv = np.linalg.inv(cov_reg)
            except np.linalg.LinAlgError:
                cov_inv = np.linalg.pinv(cov_reg)

        diff = X - mu
        # (diff @ cov_inv) * diff sum across columns
        dist_sq = np.sum((diff @ cov_inv) * diff, axis=1)
        dist_sq = np.maximum(dist_sq, 0.0)
        # Normalized score
        m_score = np.sqrt(dist_sq / max(d, 1))
        return m_score

    def find_persistent_anomaly_windows(
        self,
        df: pd.DataFrame,
        residuals: np.ndarray,
        residual_z_scores: np.ndarray,
        multivariate_scores: np.ndarray,
        expected_values: np.ndarray,
        target_col: str,
        entity_col: str,
        time_col: str,
        min_persistence: int = 3,
        z_threshold: float = 2.2,
        multi_threshold: float = 1.8,
    ) -> List[Dict[str, Any]]:
        """Cluster sequential point anomalies into high-confidence persistent anomaly windows."""
        eval_df = df.copy()
        eval_df["_res"] = residuals
        eval_df["_z"] = residual_z_scores
        eval_df["_multi"] = multivariate_scores
        eval_df["_expected"] = expected_values
        eval_df["_observed"] = eval_df[target_col].values

        if "_dt" in eval_df.columns:
            eval_df["_time"] = eval_df["_dt"]
        else:
            eval_df["_time"] = pd.to_datetime(eval_df[time_col], errors="coerce")

        anomaly_windows: List[Dict[str, Any]] = []

        if entity_col and entity_col in eval_df.columns:
            entities = eval_df[entity_col].dropna().unique()
        else:
            eval_df["_entity"] = "FLEET"
            entity_col = "_entity"
            entities = ["FLEET"]

        for ent in entities:
            sub = eval_df[eval_df[entity_col] == ent].sort_values(by="_time").reset_index(drop=True)

            # Mark anomaly condition
            # 1. Strong residual deviation (|z| >= z_threshold) OR
            # 2. Moderate residual (|z| >= 1.7) combined with elevated multivariate score
            condition = (np.abs(sub["_z"]) >= z_threshold) | (
                (np.abs(sub["_z"]) >= 1.7) & (sub["_multi"] >= multi_threshold)
            )

            # Find contiguous runs
            current_window: List[int] = []

            for i in range(len(sub)):
                if condition.iloc[i]:
                    if not current_window:
                        current_window.append(i)
                    else:
                        # Check timestamp continuity
                        prev_time = sub["_time"].iloc[current_window[-1]]
                        curr_time = sub["_time"].iloc[i]
                        delta_sec = (curr_time - prev_time).total_seconds()
                        if delta_sec <= 3600.0:  # Allow up to 1h gap for continuity
                            current_window.append(i)
                        else:
                            # Flush previous window if persistent
                            if len(current_window) >= min_persistence:
                                anomaly_windows.append(
                                    self._build_anomaly_record(sub, current_window, ent)
                                )
                            current_window = [i]
                else:
                    if len(current_window) >= min_persistence:
                        anomaly_windows.append(
                            self._build_anomaly_record(sub, current_window, ent)
                        )
                    current_window = []

            if len(current_window) >= min_persistence:
                anomaly_windows.append(
                    self._build_anomaly_record(sub, current_window, ent)
                )

        # Sort by peak residual magnitude descending
        anomaly_windows.sort(key=lambda x: abs(x["residual_score"]), reverse=True)
        return anomaly_windows

    def _build_anomaly_record(
        self,
        sub: pd.DataFrame,
        indices: List[int],
        entity: Any,
    ) -> Dict[str, Any]:
        """Assemble a traceable anomaly window record and evidence object."""
        window_rows = sub.iloc[indices]
        t_min = window_rows["_time"].min()
        t_max = window_rows["_time"].max()
        start_t = t_min.isoformat() if hasattr(t_min, "isoformat") else str(t_min)
        end_t = t_max.isoformat() if hasattr(t_max, "isoformat") else str(t_max)
        persistence = len(indices)
        dur_sec = (t_max - t_min).total_seconds() if hasattr(t_max - t_min, "total_seconds") else persistence * 1800.0
        dur_hours = round(max(dur_sec / 3600.0, persistence * 0.5), 2)

        obs_mean = float(window_rows["_observed"].mean())
        exp_mean = float(window_rows["_expected"].mean())
        res_mean = float(window_rows["_res"].mean())
        res_max = float(window_rows["_res"].abs().max())
        peak_z = float(window_rows["_z"].abs().max())
        multi_mean = float(window_rows["_multi"].mean())
        cumulative_excess = round(float(np.sum(np.maximum(window_rows["_res"].values, 0.0)) * (dur_hours / max(persistence, 1))), 2)

        # Determine severity
        if persistence >= 5 and peak_z >= 3.5:
            severity = "CRITICAL"
        elif persistence >= 3 and peak_z >= 2.5:
            severity = "HIGH"
        elif persistence >= 3:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        # Evidence confidence (0.0 to 1.0)
        confidence = min(0.98, 0.50 + (persistence * 0.05) + min(0.30, peak_z * 0.08))

        anomaly_id = f"anom-{str(entity).lower()[:4]}-{str(start_t)[:10]}-{uuid.uuid4().hex[:4]}"
        evidence_id = f"evid-{uuid.uuid4().hex[:8]}"

        interpretation = (
            f"Persistent contextual energy deviation detected on {entity}. "
            f"Observed consumption averaged {obs_mean:.1f} kWh vs expected {exp_mean:.1f} kWh "
            f"(mean residual delta: {res_mean:+.1f} kWh, peak z-score: {peak_z:.2f}\u03c3, cumulative excess: {cumulative_excess:.1f} kWh) "
            f"persisting continuously across {persistence} intervals ({dur_hours:.1f} hrs). "
            f"Specific physical or mechanical failure is NOT established from available telemetry alone."
        )

        evidence = {
            "evidence_id": evidence_id,
            "anomaly_id": anomaly_id,
            "entity": str(entity),
            "start_time": start_t,
            "end_time": end_t,
            "observations": {
                "observed_mean_kwh": round(obs_mean, 2),
                "expected_mean_kwh": round(exp_mean, 2),
                "residual_mean_kwh": round(res_mean, 2),
                "peak_residual_kwh": round(res_max, 2),
                "peak_z_score": round(peak_z, 2),
                "cumulative_excess_kwh": cumulative_excess,
                "multivariate_mean_score": round(multi_mean, 2),
                "persistence_intervals": persistence,
                "duration_hours": dur_hours,
            },
            "source_refs": [
                f"{entity} observations between {start_t} and {end_t}",
                "OLS/Ridge contextual regression baseline",
                "Mahalanobis multivariate operational state vector",
            ],
            "metrics": {
                "confidence": round(confidence, 3),
                "severity": severity,
            },
        }

        return {
            "anomaly_id": anomaly_id,
            "evidence_id": evidence_id,
            "equipment_id": str(entity),
            "start_time": start_t,
            "end_time": end_t,
            "severity": severity,
            "persistence_count": persistence,
            "residual_score": round(res_mean, 2),
            "peak_z_score": round(peak_z, 2),
            "multivariate_score": round(multi_mean, 2),
            "confidence": round(confidence, 3),
            "status": "CONFIRMED",
            "interpretation": interpretation,
            "evidence": evidence,
        }
