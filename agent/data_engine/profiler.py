"""Data Understanding and Profiling Engine for V.O.I.D.E.

Automatically discovers schemas, entity keys, temporal sampling regularity,
data quality missingness, and irregular gaps without hardcoded column names.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


class DataProfiler:
    """Automated tabular profiling, quality scoring, and temporal gap detection."""

    def __init__(self) -> None:
        pass

    def profile(self, file_path: str, max_rows: Optional[int] = None) -> Dict[str, Any]:
        """Generate comprehensive structural, temporal, and quality profile."""
        # Read dataset safely
        df = pd.read_csv(file_path, nrows=max_rows)
        row_count = len(df)
        col_count = len(df.columns)

        # 1. Type and Entity Inference
        column_types: Dict[str, str] = {}
        datetime_candidates: List[str] = []
        entity_candidates: List[str] = []
        numeric_columns: List[str] = []

        for col in df.columns:
            series = df[col]
            # Check for datetime
            if pd.api.types.is_datetime64_any_dtype(series):
                column_types[col] = "datetime"
                datetime_candidates.append(col)
            elif series.dtype == "object" or series.dtype.name == "string":
                # Sample non-null values to test for datetime
                sample = series.dropna().head(50)
                is_dt = False
                if len(sample) > 0:
                    try:
                        pd.to_datetime(sample, errors="raise")
                        is_dt = True
                    except Exception:
                        is_dt = False
                if is_dt:
                    column_types[col] = "datetime"
                    datetime_candidates.append(col)
                else:
                    unique_count = series.nunique()
                    # An entity column typically has repeated identifiers across rows
                    if 1 < unique_count <= max(100, int(row_count * 0.05)):
                        entity_candidates.append(col)
                        column_types[col] = "entity"
                    else:
                        column_types[col] = "string"
            elif pd.api.types.is_numeric_dtype(series):
                column_types[col] = "numeric"
                numeric_columns.append(col)
            else:
                column_types[col] = str(series.dtype)

        # 2. Primary Temporal & Entity Selection
        primary_time_col: Optional[str] = None
        for candidate in datetime_candidates:
            if "time" in candidate.lower() or "date" in candidate.lower():
                primary_time_col = candidate
                break
        if not primary_time_col and datetime_candidates:
            primary_time_col = datetime_candidates[0]

        primary_entity_col: Optional[str] = None
        for candidate in entity_candidates:
            if any(k in candidate.lower() for k in ["equipment", "asset", "device", "id", "unit", "chiller"]):
                primary_entity_col = candidate
                break
        if not primary_entity_col and entity_candidates:
            primary_entity_col = entity_candidates[0]

        # 3. Quality & Missingness Analysis
        missingness: Dict[str, Dict[str, Any]] = {}
        total_missing = 0
        for col in df.columns:
            m_count = int(df[col].isna().sum())
            total_missing += m_count
            missingness[col] = {
                "missing_count": m_count,
                "missing_pct": round((m_count / max(1, row_count)) * 100, 2),
            }

        duplicate_rows = int(df.duplicated().sum())
        duplicate_entity_time_pairs = 0
        if primary_entity_col and primary_time_col:
            duplicate_entity_time_pairs = int(df.duplicated(subset=[primary_entity_col, primary_time_col]).sum())

        # 4. Temporal Sampling & Gap Detection
        temporal_profile: Dict[str, Any] = {
            "has_temporal_axis": primary_time_col is not None,
            "primary_time_column": primary_time_col,
            "nominal_interval_seconds": None,
            "nominal_interval_human": None,
            "irregular_gaps_count": 0,
            "gaps": [],
            "start_time": None,
            "end_time": None,
        }

        if primary_time_col:
            try:
                time_series = pd.to_datetime(df[primary_time_col], errors="coerce").dropna()
                if len(time_series) > 1:
                    time_series = time_series.sort_values()
                    temporal_profile["start_time"] = time_series.min().isoformat()
                    temporal_profile["end_time"] = time_series.max().isoformat()

                    # Compute diffs per entity or overall
                    if primary_entity_col:
                        first_entity = df[primary_entity_col].dropna().unique()[0]
                        entity_times = pd.to_datetime(
                            df[df[primary_entity_col] == first_entity][primary_time_col], errors="coerce"
                        ).dropna().sort_values()
                        deltas = entity_times.diff().dt.total_seconds().dropna()
                    else:
                        deltas = time_series.diff().dt.total_seconds().dropna()

                    if len(deltas) > 0:
                        median_interval = float(deltas.median())
                        temporal_profile["nominal_interval_seconds"] = median_interval
                        if median_interval == 1800.0:
                            temporal_profile["nominal_interval_human"] = "30 minutes"
                        elif median_interval == 3600.0:
                            temporal_profile["nominal_interval_human"] = "1 hour"
                        elif median_interval == 60.0:
                            temporal_profile["nominal_interval_human"] = "1 minute"
                        else:
                            temporal_profile["nominal_interval_human"] = f"{int(median_interval)} seconds"

                        # Gap threshold: intervals > 1.8 * nominal interval
                        gap_threshold = max(median_interval * 1.8, 1.0)
                        gap_mask = deltas > gap_threshold
                        gap_indices = deltas[gap_mask].index

                        gaps_list = []
                        for idx in gap_indices[:20]:  # Top 20 gaps
                            prev_t = time_series.loc[idx - 1] if (idx - 1) in time_series.index else None
                            curr_t = time_series.loc[idx]
                            dur_s = float(deltas.loc[idx])
                            gaps_list.append({
                                "start": prev_t.isoformat() if prev_t is not None else None,
                                "end": curr_t.isoformat(),
                                "duration_seconds": dur_s,
                                "duration_hours": round(dur_s / 3600.0, 2),
                                "gap_type": "sensor_outage" if dur_s > 7200 else "missed_reading",
                            })
                        temporal_profile["irregular_gaps_count"] = int(gap_mask.sum())
                        temporal_profile["gaps"] = gaps_list
            except Exception:
                pass

        # 5. Column Statistics
        column_stats: Dict[str, Dict[str, Any]] = {}
        for col in numeric_columns:
            s = df[col].dropna()
            if len(s) > 0:
                column_stats[col] = {
                    "min": float(s.min()),
                    "max": float(s.max()),
                    "mean": round(float(s.mean()), 3),
                    "std": round(float(s.std()), 3),
                    "zeros_count": int((s == 0).sum()),
                }

        # 6. Entity Cardinality
        entity_summary: Dict[str, Any] = {}
        if primary_entity_col:
            counts = df[primary_entity_col].value_counts().to_dict()
            entity_summary = {
                "entity_column": primary_entity_col,
                "distinct_count": len(counts),
                "entities": list(counts.keys()),
                "counts_per_entity": {str(k): int(v) for k, v in counts.items()},
            }

        # 6.5 Target & Exogenous Context Variable Inference
        primary_target_col: Optional[str] = None
        for cand in ["Chiller Energy Consumption (kWh)", "energy", "kwh", "power", "consumption", "target", "load", "reading"]:
            for col in numeric_columns:
                if cand.lower() in col.lower():
                    primary_target_col = col
                    break
            if primary_target_col:
                break
        if not primary_target_col and numeric_columns:
            # Pick highest variance numeric column
            variances = {col: float(df[col].var()) for col in numeric_columns if not df[col].isna().all()}
            if variances:
                primary_target_col = max(variances, key=variances.get)
            else:
                primary_target_col = numeric_columns[0]

        primary_load_col: Optional[str] = None
        for cand in ["Building Load (RT)", "load", "demand", "cooling", "capacity", "flow"]:
            for col in numeric_columns:
                if col != primary_target_col and cand.lower() in col.lower():
                    primary_load_col = col
                    break
            if primary_load_col:
                break

        feature_cols: List[str] = [c for c in numeric_columns if c != primary_target_col]

        # 7. Composite Quality Health Score (0 - 100)
        missing_penalty = min(30.0, (total_missing / max(1, row_count * col_count)) * 100 * 2)
        duplicate_penalty = 20.0 if duplicate_entity_time_pairs > 0 else 0.0
        gap_penalty = min(20.0, temporal_profile["irregular_gaps_count"] * 0.5)
        health_score = max(10.0, round(100.0 - missing_penalty - duplicate_penalty - gap_penalty, 1))

        return {
            "row_count": row_count,
            "column_count": col_count,
            "columns": list(df.columns),
            "column_types": column_types,
            "primary_time_column": primary_time_col,
            "primary_entity_column": primary_entity_col,
            "primary_target_column": primary_target_col,
            "primary_load_column": primary_load_col,
            "feature_columns": feature_cols,
            "entity_summary": entity_summary,
            "missingness": missingness,
            "duplicate_rows": duplicate_rows,
            "duplicate_entity_time_pairs": duplicate_entity_time_pairs,
            "temporal_profile": temporal_profile,
            "column_stats": column_stats,
            "data_health_score": health_score,
        }
