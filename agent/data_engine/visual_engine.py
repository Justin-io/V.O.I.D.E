"""Visual Intelligence Engine for V.O.I.D.E. (White Theme & Minimalist Styling)

Generates high-resolution, publication-quality engineering charts and
schematic visual explanations using matplotlib (Agg headless renderer)
with crisp white/light aesthetic matching modern SaaS/Linear design.
"""

from __future__ import annotations
import os
import uuid
from typing import Any, Dict, List, Optional
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd


class VisualEngine:
    """Renderer for time series, contextual residual envelopes, and HVAC schematics."""

    def __init__(self, visuals_dir: str) -> None:
        self.visuals_dir = os.path.realpath(visuals_dir)
        os.makedirs(self.visuals_dir, exist_ok=True)
        # Apply clean default styling
        plt.style.use("default")

    def _apply_clean_white_style(self, fig: plt.Figure, ax: plt.Axes) -> None:
        """Apply modern, minimalist white palette to plot."""
        fig.patch.set_facecolor("#FFFFFF")
        ax.set_facecolor("#F8FAFC")
        ax.grid(True, linestyle="--", alpha=0.6, color="#E2E8F0")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#CBD5E1")
        ax.spines["bottom"].set_color("#CBD5E1")
        ax.tick_params(colors="#64748B", labelsize=9)

    def plot_observed_vs_expected(
        self,
        df: pd.DataFrame,
        equipment_id: str,
        observed_col: str,
        expected_col: str,
        entity_col: Optional[str] = "equipment_id",
        time_col: str = "_dt",
        max_points: int = 1500,
    ) -> str:
        """Render Observed vs Expected Energy timeline with variance envelope in white theme."""
        if entity_col and entity_col in df.columns:
            sub = df[df[entity_col] == equipment_id].sort_values(by=time_col).copy()
        else:
            sub = df.sort_values(by=time_col).copy()

        if len(sub) == 0:
            sub = df.sort_values(by=time_col).copy()

        if len(sub) > max_points:
            step = len(sub) // max_points
            sub = sub.iloc[::step]

        fig, ax = plt.subplots(figsize=(12, 5), dpi=140)
        self._apply_clean_white_style(fig, ax)

        times = pd.to_datetime(sub[time_col])
        obs = sub[observed_col].values
        exp = sub[expected_col].values

        ax.plot(times, exp, label="Expected Contextual Baseline (ŷ)", color="#2563EB", linewidth=1.6, alpha=0.95)
        ax.plot(times, obs, label="Observed Sensor Reading (y)", color="#F59E0B", linewidth=1.1, alpha=0.85)

        # Translucent confidence envelope around expected
        res_std = float(np.std(obs - exp))
        ax.fill_between(times, exp - 2 * res_std, exp + 2 * res_std, color="#BFDBFE", alpha=0.45, label="Expected Envelope (±2σ)")

        # Highlight large anomalies
        anom_mask = np.abs(obs - exp) > (2.5 * res_std)
        if np.any(anom_mask):
            ax.scatter(times[anom_mask], obs[anom_mask], color="#EF4444", s=22, label="Significant Anomaly (>2.5σ)", zorder=5)

        ax.set_title(f"{equipment_id} — Observed vs Contextual Baseline Energy Consumption", fontsize=12, color="#0F172A", fontweight="bold", pad=12)
        ax.set_xlabel("Timeline", fontsize=10, color="#475569")
        ax.set_ylabel("Energy Consumption (kWh)", fontsize=10, color="#475569")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        fig.autofmt_xdate()
        ax.legend(loc="upper right", framealpha=0.95, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=9, labelcolor="#1E293B")

        plt.tight_layout()
        clean_id = "".join(c for c in equipment_id.lower() if c.isalnum() or c == "_")
        dash_id = equipment_id.lower().replace(" ", "-")
        out_path = os.path.join(self.visuals_dir, f"obs_vs_exp_{clean_id}.png")
        fig.savefig(out_path, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

        import shutil
        for alt_name in (
            f"obs_vs_exp_{dash_id}.png",
            f"observed_vs_expected_{dash_id}.png",
            f"observed_vs_expected_{clean_id}.png",
        ):
            alt_p = os.path.join(self.visuals_dir, alt_name)
            if alt_p != out_path:
                try:
                    shutil.copyfile(out_path, alt_p)
                except Exception:
                    pass

        return out_path

    def plot_residuals(
        self,
        df: pd.DataFrame,
        equipment_id: str,
        residual_col: str = "_res",
        z_col: str = "_z",
        entity_col: Optional[str] = "equipment_id",
        time_col: str = "_dt",
        max_points: int = 1500,
    ) -> str:
        """Render Residual deviation timeline with statistical ±2.5σ control limits in white theme."""
        if entity_col and entity_col in df.columns:
            sub = df[df[entity_col] == equipment_id].sort_values(by=time_col).copy()
        else:
            sub = df.sort_values(by=time_col).copy()

        if len(sub) == 0:
            sub = df.sort_values(by=time_col).copy()

        if len(sub) > max_points:
            step = len(sub) // max_points
            sub = sub.iloc[::step]

        fig, ax = plt.subplots(figsize=(12, 4.5), dpi=140)
        self._apply_clean_white_style(fig, ax)

        times = pd.to_datetime(sub[time_col])
        res = sub[residual_col].values

        ax.plot(times, res, color="#0284C7", linewidth=1.1, label="Contextual Residual e = y - ŷ")
        ax.axhline(0, color="#94A3B8", linestyle="-", linewidth=1.0, alpha=0.8)

        # Statistical limits
        res_std = float(np.std(res))
        upper_lim = 2.5 * res_std
        lower_lim = -2.5 * res_std
        ax.axhline(upper_lim, color="#DC2626", linestyle="--", linewidth=1.2, label="+2.5σ Upper Control Limit")
        ax.axhline(lower_lim, color="#DC2626", linestyle="--", linewidth=1.2, label="-2.5σ Lower Control Limit")

        # Shading
        ax.fill_between(times, upper_lim, np.maximum(res, upper_lim), color="#FCA5A5", alpha=0.4)
        ax.fill_between(times, lower_lim, np.minimum(res, lower_lim), color="#FCA5A5", alpha=0.4)

        ax.set_title(f"{equipment_id} — Contextual Residual Timeline & Control Envelope (ASHRAE Guideline 14)", fontsize=12, color="#0F172A", fontweight="bold", pad=12)
        ax.set_xlabel("Timeline", fontsize=10, color="#475569")
        ax.set_ylabel("Residual Δ (kWh)", fontsize=10, color="#475569")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        fig.autofmt_xdate()
        ax.legend(loc="lower left", framealpha=0.95, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=9, labelcolor="#1E293B")

        plt.tight_layout()
        clean_id = "".join(c for c in equipment_id.lower() if c.isalnum() or c == "_")
        dash_id = equipment_id.lower().replace(" ", "-")
        out_path = os.path.join(self.visuals_dir, f"residuals_{clean_id}.png")
        fig.savefig(out_path, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

        import shutil
        alt_res = os.path.join(self.visuals_dir, f"residuals_{dash_id}.png")
        if alt_res != out_path:
            try:
                shutil.copyfile(out_path, alt_res)
            except Exception:
                pass

        return out_path

    def plot_anomaly_zoom(
        self,
        df: pd.DataFrame,
        anomaly_record: Dict[str, Any],
        observed_col: str,
        expected_col: str,
        load_col: Optional[str] = None,
        entity_col: Optional[str] = "equipment_id",
        time_col: str = "_dt",
    ) -> str:
        """Render high-resolution multi-panel zoom into an individual persistent anomaly episode in white theme."""
        eq = anomaly_record.get("equipment_id", "FLEET")
        start_t = pd.to_datetime(anomaly_record["start_time"])
        end_t = pd.to_datetime(anomaly_record["end_time"])

        # Window: 48h padding around episode
        pad = pd.Timedelta(hours=48)
        win_start = start_t - pad
        win_end = end_t + pad

        if entity_col and entity_col in df.columns:
            sub = df[(df[entity_col] == eq) & (df[time_col] >= win_start) & (df[time_col] <= win_end)].sort_values(by=time_col)
            if len(sub) == 0:
                sub = df[df[entity_col] == eq].head(120)
        else:
            sub = df[(df[time_col] >= win_start) & (df[time_col] <= win_end)].sort_values(by=time_col)
            if len(sub) == 0:
                sub = df.head(120)

        has_load = load_col and load_col in sub.columns
        rows = 3 if has_load else 2

        fig, axes = plt.subplots(rows, 1, figsize=(12, 3 * rows), dpi=140, sharex=True)
        fig.patch.set_facecolor("#FFFFFF")

        times = pd.to_datetime(sub[time_col])

        # Panel 1: Observed vs Expected
        ax1 = axes[0]
        self._apply_clean_white_style(fig, ax1)
        ax1.plot(times, sub[observed_col], label="Observed Energy (kWh)", color="#F59E0B", linewidth=1.8)
        ax1.plot(times, sub[expected_col], label="Expected Baseline (kWh)", color="#2563EB", linewidth=1.6, linestyle="--")
        ax1.axvspan(start_t, end_t, color="#EF4444", alpha=0.18, label=f"Anomaly Window ({anomaly_record['persistence_count']} intervals)")
        ax1.set_ylabel("Energy (kWh)", fontsize=10, color="#475569")
        ax1.set_title(f"Episode Zoom: {eq} — Severity: {anomaly_record['severity']} (Excess: {anomaly_record.get('evidence', {}).get('observations', {}).get('cumulative_excess_kwh', 0):.1f} kWh)", fontsize=11, color="#0F172A", fontweight="bold")
        ax1.legend(loc="upper right", framealpha=0.95, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=8, labelcolor="#1E293B")

        # Panel 2: Operating Context / Building Load if present
        if has_load:
            ax2 = axes[1]
            self._apply_clean_white_style(fig, ax2)
            ax2.plot(times, sub[load_col], label=f"Context Demand: {load_col}", color="#059669", linewidth=1.5)
            ax2.axvspan(start_t, end_t, color="#EF4444", alpha=0.18)
            ax2.set_ylabel("Demand", fontsize=10, color="#475569")
            ax2.legend(loc="upper right", framealpha=0.95, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=8, labelcolor="#1E293B")
            ax_res = axes[2]
        else:
            ax_res = axes[1]

        # Final Panel: Residual
        self._apply_clean_white_style(fig, ax_res)
        res = sub[observed_col] - sub[expected_col]
        ax_res.plot(times, res, label="Contextual Residual (kWh)", color="#D946EF", linewidth=1.5)
        ax_res.axhline(0, color="#94A3B8", linestyle="-", linewidth=0.8)
        ax_res.axvspan(start_t, end_t, color="#EF4444", alpha=0.18)
        ax_res.set_ylabel("Residual (kWh)", fontsize=10, color="#475569")
        ax_res.set_xlabel("Timeline", fontsize=10, color="#475569")
        ax_res.xaxis.set_major_formatter(mdates.DateFormatter("%b %d %H:%M"))
        fig.autofmt_xdate()
        ax_res.legend(loc="upper right", framealpha=0.95, facecolor="#FFFFFF", edgecolor="#E2E8F0", fontsize=8, labelcolor="#1E293B")

        plt.tight_layout()
        anom_id_clean = "".join(c for c in anomaly_record["anomaly_id"] if c.isalnum() or c in "-_")
        out_path = os.path.join(self.visuals_dir, f"anomaly_zoom_{anom_id_clean}.png")
        fig.savefig(out_path, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        return out_path

    def plot_chiller_schematic(self, equipment_id: Optional[str] = None, state_status: Optional[str] = None) -> str:
        """Render a clean white-theme engineering HVAC chiller flow schematic with sensor callouts."""
        fig, ax = plt.subplots(figsize=(11, 6), dpi=140)
        fig.patch.set_facecolor("#FFFFFF")
        ax.set_facecolor("#F8FAFC")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 70)
        ax.axis("off")

        # Evaporator Box
        ax.add_patch(plt.Rectangle((12, 20), 22, 24, facecolor="#EFF6FF", edgecolor="#3B82F6", linewidth=2))
        ax.text(23, 33, "EVAPORATOR", color="#1E3A8A", weight="bold", fontsize=11, ha="center")
        ax.text(23, 27, "Chilled Water Loop\n44°F - 54°F", color="#3B82F6", fontsize=8, ha="center")

        # Compressor Box
        ax.add_patch(plt.Rectangle((42, 42), 16, 18, facecolor="#FFF7ED", edgecolor="#F97316", linewidth=2))
        ax.text(50, 52, "COMPRESSOR", color="#9A3412", weight="bold", fontsize=11, ha="center")
        ax.text(50, 46, "Refrigerant Lift\nEnergy Draw (kWh)", color="#C2410C", fontsize=8, ha="center")

        # Condenser Box
        ax.add_patch(plt.Rectangle((66, 20), 22, 24, facecolor="#FDF2F8", edgecolor="#EC4899", linewidth=2))
        ax.text(77, 33, "CONDENSER", color="#9D174D", weight="bold", fontsize=11, ha="center")
        ax.text(77, 27, "Cooling Water Loop\n85°F - 95°F", color="#DB2777", fontsize=8, ha="center")

        # Expansion Valve
        ax.add_patch(plt.Polygon([[47, 16], [53, 22], [53, 16], [47, 22]], facecolor="#F1F5F9", edgecolor="#64748B", linewidth=1.5))
        ax.text(50, 10, "Expansion Valve", color="#475569", fontsize=8, weight="bold", ha="center")

        # Connecting pipes / arrows
        ax.annotate("", xy=(42, 50), xytext=(28, 44), arrowprops=dict(arrowstyle="->", color="#D97706", lw=2.5))
        ax.annotate("", xy=(72, 44), xytext=(58, 50), arrowprops=dict(arrowstyle="->", color="#D97706", lw=2.5))
        ax.annotate("", xy=(30, 20), xytext=(47, 19), arrowprops=dict(arrowstyle="->", color="#2563EB", lw=2.5))
        ax.annotate("", xy=(53, 19), xytext=(70, 20), arrowprops=dict(arrowstyle="->", color="#DB2777", lw=2.5))

        # Sensor Callout Badges
        sensors = [
            (10, 52, "SENSOR: Chilled Water Rate (L/sec)", "#0284C7"),
            (10, 8, "SENSOR: Building Load (RT)", "#059669"),
            (50, 65, "TARGET: Energy Consumption (kWh)", "#D97706"),
            (78, 52, "SENSOR: Cooling Water Temp (°C)", "#C026D3"),
            (78, 8, "CONTEXT: Ambient Weather & Humidity", "#6D28D9"),
        ]
        for x, y, label, col in sensors:
            ax.add_patch(plt.Rectangle((x - 2, y - 2), 27, 4.5, facecolor="#FFFFFF", edgecolor=col, linewidth=1.5))
            ax.text(x + 11.5, y, label, color=col, fontsize=7.5, weight="bold", ha="center", va="center")

        title = "V.O.I.D.E. Physical HVAC Chiller System & Sensor Instrumentation Schematic"
        if equipment_id:
            title += f" [{equipment_id}]"
        if state_status:
            title += f" — {state_status}"
        ax.set_title(title, fontsize=11, color="#0F172A", weight="bold", y=0.96)

        plt.tight_layout()
        filename = f"chiller_schematic_{equipment_id.lower()}.png" if equipment_id else "chiller_schematic.png"
        out_path = os.path.join(self.visuals_dir, filename)
        fig.savefig(out_path, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        return out_path

    generate_chiller_schematic = plot_chiller_schematic
