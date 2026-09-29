"""Feature Intelligence Engine for V.O.I.D.E.

Builds temporal calendar features, rolling contextual statistics, and operating ratios
with full lineage tracking and zero cross-gap leakage.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class FeatureEngine:
    """Automated feature generation for engineering and time-series datasets."""

    def __init__(self) -> None:
        pass

    def build_features(
        self,
        df: pd.DataFrame,
        target_col: str,
        load_col: Optional[str] = None,
        entity_col: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Generate calendar, contextual, rolling, and ratio features."""
        feat_df = df.copy()
        generated_features: List[str] = []
        transforms: List[Dict[str, Any]] = []

        if "_dt" not in feat_df.columns:
            raise ValueError("DataFrame requires '_dt' datetime column.")

        # 1. Calendar Cyclical Features (sin/cos encoding for linear regressions)
        feat_df["feat_hour"] = feat_df["_dt"].dt.hour
        feat_df["feat_sin_hour"] = np.sin(2 * np.pi * feat_df["feat_hour"] / 24.0)
        feat_df["feat_cos_hour"] = np.cos(2 * np.pi * feat_df["feat_hour"] / 24.0)
        feat_df["feat_dayofweek"] = feat_df["_dt"].dt.dayofweek
        feat_df["feat_sin_dow"] = np.sin(2 * np.pi * feat_df["feat_dayofweek"] / 7.0)
        feat_df["feat_cos_dow"] = np.cos(2 * np.pi * feat_df["feat_dayofweek"] / 7.0)
        feat_df["feat_month"] = feat_df["_dt"].dt.month
        feat_df["feat_is_working_hour"] = (
            (feat_df["feat_hour"] >= 8) & (feat_df["feat_hour"] <= 18) & (feat_df["feat_dayofweek"] < 5)
        ).astype(int)

        cal_features = [
            "feat_hour", "feat_sin_hour", "feat_cos_hour",
            "feat_dayofweek", "feat_sin_dow", "feat_cos_dow",
            "feat_month", "feat_is_working_hour"
        ]
        generated_features.extend(cal_features)
        transforms.append({
            "type": "calendar",
            "source": "_dt",
            "features": cal_features,
        })

        # 2. Contextual Ratio Features
        if load_col and load_col in feat_df.columns:
            # Energy per unit load ratio: kWh / RT
            ratio_name = "feat_energy_per_load"
            safe_load = np.maximum(feat_df[load_col].fillna(1.0).values, 0.1)
            feat_df[ratio_name] = feat_df[target_col].fillna(0.0).values / safe_load
            generated_features.append(ratio_name)
            transforms.append({
                "type": "ratio",
                "numerator": target_col,
                "denominator": load_col,
                "feature": ratio_name,
            })

        # 3. Rolling Statistics (grouped by entity and segment to prevent gap leakage)
        group_keys = []
        if entity_col and entity_col in feat_df.columns:
            group_keys.append(entity_col)
        if "_segment_id" in feat_df.columns:
            group_keys.append("_segment_id")

        candidate_signals = [c for c in [target_col, load_col] if c and c in feat_df.columns]

        for col in candidate_signals:
            col_clean = "".join(c for c in col if c.isalnum())[:12].lower()
            mean_col = f"feat_{col_clean}_roll_mean_3"
            std_col = f"feat_{col_clean}_roll_std_3"

            if group_keys:
                grouped = feat_df.groupby(group_keys)[col]
                feat_df[mean_col] = grouped.transform(lambda s: s.rolling(3, min_periods=1).mean())
                feat_df[std_col] = grouped.transform(lambda s: s.rolling(3, min_periods=1).std().fillna(0.0))
            else:
                feat_df[mean_col] = feat_df[col].rolling(3, min_periods=1).mean()
                feat_df[std_col] = feat_df[col].rolling(3, min_periods=1).std().fillna(0.0)

            generated_features.extend([mean_col, std_col])
            transforms.append({
                "type": "rolling_stats",
                "source": col,
                "window": 3,
                "features": [mean_col, std_col],
            })

        feature_manifest = {
            "source_columns": [c for c in [target_col, load_col] if c],
            "feature_names": generated_features,
            "transforms": transforms,
            "total_features_generated": len(generated_features),
        }

        return feat_df, feature_manifest
