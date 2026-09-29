"""Deterministic Data Preparation Engine for V.O.I.D.E.

Enforces chronological sorting, gap classification, time-series segmentation,
and leakage-free temporal train/validation splitting.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


class DataPreparator:
    """Deterministic, time-aware preparation and segmentation pipeline."""

    def __init__(self) -> None:
        pass

    def prepare(
        self,
        df: pd.DataFrame,
        time_column: str,
        entity_column: Optional[str] = None,
        max_impute_consecutive: int = 2,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Clean, sort chronologically, segment continuous periods, and impute short gaps."""
        clean_df = df.copy()

        # 1. Clean column names
        clean_df.columns = [c.strip() for c in clean_df.columns]

        # 2. Parse timestamps with fallback synthesis
        if not time_column or time_column not in clean_df.columns:
            clean_df["_dt"] = pd.date_range("2026-01-01", periods=len(clean_df), freq="30min")
        else:
            clean_df["_dt"] = pd.to_datetime(clean_df[time_column], errors="coerce")
            if clean_df["_dt"].isna().all():
                clean_df["_dt"] = pd.date_range("2026-01-01", periods=len(clean_df), freq="30min")
            else:
                clean_df = clean_df.dropna(subset=["_dt"])

        # 3. Sort chronologically
        sort_cols = [entity_column, "_dt"] if entity_column and entity_column in clean_df.columns else ["_dt"]
        clean_df = clean_df.sort_values(by=sort_cols).reset_index(drop=True)

        # 4. Gap detection and segmenting
        clean_df["_segment_id"] = 0
        segment_counter = 0
        total_gaps_found = 0

        entities = [None] if not entity_column or entity_column not in clean_df.columns else clean_df[entity_column].unique()

        processed_dfs: List[pd.DataFrame] = []

        for ent in entities:
            if ent is not None:
                sub_df = clean_df[clean_df[entity_column] == ent].copy()
            else:
                sub_df = clean_df.copy()

            if len(sub_df) > 1:
                deltas = sub_df["_dt"].diff().dt.total_seconds()
                median_delta = deltas.median()
                gap_cutoff = max(median_delta * 1.8, 60.0) if pd.notna(median_delta) and median_delta > 0 else 3600.0

                is_gap = deltas > gap_cutoff
                total_gaps_found += int(is_gap.sum())

                # Create segments
                sub_segments = (is_gap).cumsum() + segment_counter
                sub_df["_segment_id"] = sub_segments
                segment_counter = int(sub_segments.max()) + 1
            else:
                sub_df["_segment_id"] = segment_counter
                segment_counter += 1

            # 5. Safe bounded imputation within segment
            numeric_cols = sub_df.select_dtypes(include=[np.number]).columns
            cols_to_impute = [c for c in numeric_cols if c not in ["_segment_id"]]

            # Bounded forward-fill followed by backward-fill up to max_impute_consecutive
            sub_df[cols_to_impute] = sub_df.groupby("_segment_id")[cols_to_impute].transform(
                lambda s: s.ffill(limit=max_impute_consecutive).bfill(limit=max_impute_consecutive)
            )

            # If still missing, fill with column median to prevent crash
            for col in cols_to_impute:
                if sub_df[col].isna().any():
                    col_med = sub_df[col].median()
                    sub_df[col] = sub_df[col].fillna(col_med if pd.notna(col_med) else 0.0)

            processed_dfs.append(sub_df)

        result_df = pd.concat(processed_dfs, ignore_index=True)
        result_df = result_df.sort_values(by=sort_cols).reset_index(drop=True)

        prep_report = {
            "initial_rows": len(df),
            "prepared_rows": len(result_df),
            "total_segments": segment_counter,
            "total_gaps_detected": total_gaps_found,
            "time_range": {
                "start": result_df["_dt"].min().isoformat(),
                "end": result_df["_dt"].max().isoformat(),
            },
        }

        return result_df, prep_report

    def temporal_split(
        self,
        df: pd.DataFrame,
        split_ratio: float = 0.70,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
        """Perform strictly chronological train/test split without future data leakage."""
        if "_dt" not in df.columns:
            raise ValueError("DataFrame must contain parsed '_dt' column for temporal split.")

        sorted_df = df.sort_values(by="_dt").reset_index(drop=True)
        split_idx = int(len(sorted_df) * split_ratio)

        train_df = sorted_df.iloc[:split_idx].copy()
        test_df = sorted_df.iloc[split_idx:].copy()

        cutoff_time = sorted_df.iloc[split_idx]["_dt"].isoformat()

        split_info = {
            "split_ratio": split_ratio,
            "train_rows": len(train_df),
            "test_rows": len(test_df),
            "train_start": train_df["_dt"].min().isoformat(),
            "train_end": train_df["_dt"].max().isoformat(),
            "test_start": test_df["_dt"].min().isoformat(),
            "test_end": test_df["_dt"].max().isoformat(),
            "cutoff_timestamp": cutoff_time,
        }

        return train_df, test_df, split_info
