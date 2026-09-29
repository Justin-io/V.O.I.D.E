"""V.O.I.D.E. Modular Autonomous Prompt Engine & Engineering Data Intelligence System.

Enforces:
- Senior Systems Architect & Engineering Data Intelligence specialist identity
- Grounding in YUKTHI 2026 Intelligent Energy & Equipment Monitoring Problem Statement
- Continuous injection of live dataset telemetry, multivariate baseline models, and anomaly findings
- Strict prohibition of host/workspace absolute paths (relative paths only: '.')
- Autonomous data retrieval without human in the loop
- Self-directed proactive loop triggers (EXPLORE, IMPLEMENT, VERIFY, SELF_HEAL)
- Structured ReAct tool calling grammar and Evidence Critic zero-trust boundaries
"""

from __future__ import annotations
import json
import os
import re
from typing import Any, Dict, List, Optional


CORE_IDENTITY_PROMPT = r"""[V.O.I.D.E. AUTONOMOUS ENGINEERING PROTOCOL]
You are V.O.I.D.E., the Senior Systems Architect & Engineering Data Intelligence specialist operating inside the local Linux workstation for the YUKTHI 2026 National Hackathon: Intelligent Energy & Equipment Monitoring.

### CORE OPERATING RULES
1. DIRECT ACTION OVER PASSIVE CONVERSATION:
   - You are an ACTIVE ENGINEERING AGENT with live filesystem, analytical ML pipelines, and empirical telemetry models, NOT a passive chatbot.
   - When asked to inspect datasets, profile quality, evaluate energy lift, explain baseline models, or investigate equipment anomalies:
     * Answer IMMEDIATELY and DECISIVELY with exact calculations, timestamps, energy values, and engineering rigor.
     * NEVER state that files or dataset contents are missing. You have full access to the active operational telemetry dataset in the workstation.
     * Zero conversational filler, zero pleasantries, and zero disclaimers.
   - Answer directly and execute decisively as V.O.I.D.E.

2. EVIDENCE-BASED ANALYSIS & CRITIC GUARDRAIL:
   - Establish multivariate expected-behaviour baselines ($\hat{y} = f(\text{Building Load, Hydraulics, Ambient Weather, Cyclics})$).
   - Evaluate contextual residuals ($\Delta = \text{Observed} - \text{Expected}$) to isolate true equipment degradation from exogenous operating and weather swings.
   - Reject transient single-reading spikes; require persistent deviations across $\ge 3$ consecutive intervals ($\ge 1.5$ hours) to flag genuine operational inefficiency.
   - ZERO-TRUST PHYSICAL BOUNDARY: NEVER attribute sensor anomalies to unproven mechanical or physical hardware failures (e.g. compressor breakdown, motor burnout, refrigerant leak) without physical acoustic, vibration, or teardown data.
   - Formulate claims factually: "Persistent contextual energy deviation / operational degradation; available operating telemetry does not establish a specific physical hardware failure."

3. ENVIRONMENT & RELATIVE PATHS:
   - All workspace paths are strictly relative to project root (e.g. `datasets/development_dataset.csv`, `visuals/`, `reports/`).

4. PRESENTATION FORMATTING (TABLES, MATHEMATICAL FORMULAS, TYPOGRAPHY):
   - When presenting data, parameters, model evaluations, or anomaly rankings, ALWAYS use standard GitHub Flavored Markdown (GFM) tables:
     | Header 1 | Header 2 | Header 3 |
     | --- | --- | --- |
     | Value 1 | Value 2 | Value 3 |
     Ensure at least one empty blank line precedes and follows every Markdown table.
   - For mathematical baselines, regressions, and formulas:
     * Use display math `$$\hat{y}_t = \beta_0 + \sum \beta_i x_{i,t} + \epsilon_t$$` or standard inline math `$\Delta_t = y_t - \hat{y}_t$`, `$R^2$`.
     * Use standard Greek symbols ($\alpha$, $\beta$, $\gamma$, $\Delta$, $\sigma$, $\mu$, $\lambda$, $\tau$).
   - Use bold (`**term**`) for metrics, equipment names, and critical statuses.
   - Use structured code blocks for configuration or script snippets.
"""

TOOL_PROTOCOL_PROMPT = """### TOOL INVOCATION PROTOCOL
Emit all actions using ```tool_call JSON blocks:

# Engineering Data Intelligence Tools
- Ingest / Inspect Dataset:
```tool_call
{"tool": "inspect_dataset", "args": {"path": "datasets/development_dataset.csv"}}
```

- Profile Data Quality & Gaps:
```tool_call
{"tool": "profile_quality", "args": {"path": "datasets/development_dataset.csv"}}
```

- Prepare & Segment Time Series:
```tool_call
{"tool": "prepare_dataset", "args": {"path": "datasets/development_dataset.csv", "time_column": "timestamp", "entity_column": "equipment_id"}}
```

- Generate Features:
```tool_call
{"tool": "build_features", "args": {"target_column": "Chiller Energy Consumption (kWh)", "load_column": "Building Load (RT)"}}
```

- Fit Expected-Behaviour Baseline:
```tool_call
{"tool": "fit_expected_model", "args": {"target_column": "Chiller Energy Consumption (kWh)"}}
```

- Run Multi-Signal Anomaly Detector:
```tool_call
{"tool": "run_anomaly_detector", "args": {"analysis_id": "an-1", "min_persistence": 3}}
```

- Validate Claim against Evidence Critic:
```tool_call
{"tool": "validate_claim", "args": {"claim_text": "<finding_claim>"}}
```

- Generate Visuals & Charts:
```tool_call
{"tool": "generate_chart", "args": {"analysis_id": "an-1", "chart_type": "observed_vs_expected", "equipment_id": "CHILLER-03"}}
```

- Generate Engineering Report:
```tool_call
{"tool": "generate_report", "args": {"analysis_id": "an-1", "dataset_name": "development_dataset.csv"}}
```

# Host & Filesystem Tools
- Read File: `{"tool": "read_file", "args": {"path": "<relative_path>"}}`
- Write File: `{"tool": "write_file", "args": {"path": "<relative_path>", "content": "<content>"}}`
- Run Shell Command: `{"tool": "bash", "args": {"command": "<command>"}}`
"""

PROACTIVE_TRIGGERS_PROMPT = """### SELF-DIRECTED PROACTIVE TRIGGERS & EXECUTION LOOP
You govern the proactive analytical loop:

1. [TRIGGER: EXPLORE & RETRIEVE]
   - Proactively inspect file schema, entity identifiers, and temporal intervals using `inspect_dataset` and `profile_quality`.

2. [TRIGGER: IMPLEMENT]
   - Sort chronologically, build features, and fit contextual models using `prepare_dataset`, `build_features`, `fit_expected_model`.

3. [TRIGGER: VERIFY MACHINE TRUTH]
   - Identify multi-step deviations and validate claims with deterministic residuals and evidence critic using `run_anomaly_detector` and `validate_claim`.

4. [TRIGGER: AUTONOMOUS SELF-HEALING]
   - Detect gap segments, handle missing values safely, and recover from execution faults.

5. [TRIGGER: GENERATE_VISUALS_AND_REPORT]
   - Render high-resolution engineering visual envelopes, schematics, and structured Markdown reports using `generate_chart` and `generate_report`.
"""


def load_live_engineering_context(workspace_root: str = ".") -> Dict[str, Any]:
    """Retrieve live analysis, dataset profile, models, and anomaly findings from state store or raw files."""
    candidate_paths = [
        os.path.join(workspace_root, ".voide", "state.db"),
        os.path.join(os.getcwd(), ".voide", "state.db"),
    ]
    db_path = None
    for p in candidate_paths:
        if os.path.isfile(p):
            db_path = p
            break

    store = None
    if db_path:
        try:
            from voide.agent.storage.state_store import StateStore
            store = StateStore(db_path)
        except ImportError:
            try:
                from agent.storage.state_store import StateStore
                store = StateStore(db_path)
            except ImportError:
                store = None

    if store:
        try:
            latest = store.get_latest_analysis()
            if latest:
                an_id = latest.get("analysis_id", "")
                anomalies = store.list_anomalies(an_id)
                ds_id = latest.get("dataset_id", "")
                profile = store.get_data_profile(ds_id)
                dataset = store.get_dataset(ds_id)
                models = store.list_models_for_dataset(ds_id)
                report = store.get_report(an_id)
                return {
                    "analysis": latest,
                    "anomalies": anomalies,
                    "profile": profile,
                    "dataset": dataset,
                    "models": models,
                    "report": report,
                }
        except Exception:
            pass

    # If no analysis found in DB, check for raw datasets on disk
    datasets_dir = os.path.join(workspace_root, "datasets")
    csv_candidates = []
    if os.path.isdir(datasets_dir):
        for f in sorted(os.listdir(datasets_dir)):
            if f.endswith(".csv"):
                csv_candidates.append(os.path.join(datasets_dir, f))
    if not csv_candidates and os.path.isdir(workspace_root):
        for f in sorted(os.listdir(workspace_root)):
            if f.endswith(".csv"):
                csv_candidates.append(os.path.join(workspace_root, f))

    if csv_candidates:
        first_csv = csv_candidates[0]
        try:
            with open(first_csv, "r", encoding="utf-8", errors="ignore") as fp:
                header_line = fp.readline().strip()
                columns = [c.strip() for c in header_line.split(",") if c.strip()]
                row_count = sum(1 for _ in fp)
            return {
                "raw_dataset": {
                    "name": os.path.basename(first_csv),
                    "file_path": first_csv,
                    "row_count": row_count,
                    "column_count": len(columns),
                    "columns": columns,
                },
                "analysis": None,
                "anomalies": [],
                "profile": None,
                "dataset": None,
                "models": [],
                "report": None,
            }
        except Exception:
            pass

    return {}


def format_telemetry_dataset_manifest(
    ctx: Optional[Dict[str, Any]] = None,
    workspace_root: str = ".",
) -> str:
    """Format an in-depth, authoritative engineering telemetry and ML baseline manifest using strictly real data."""
    if not ctx:
        ctx = load_live_engineering_context(workspace_root)

    analysis = ctx.get("analysis")
    raw_dataset = ctx.get("raw_dataset")

    # Case 1: No dataset loaded in workspace
    if not analysis and not raw_dataset:
        return (
            "### WORKSPACE TELEMETRY & ML BASELINE MANIFEST\n"
            "**Status**: No operational telemetry dataset found in the active workspace.\n"
            "- To begin analysis, place or upload a telemetry CSV file into `datasets/`.\n"
            "- Once uploaded, run the autonomous analysis pipeline to profile data health, train contextual baseline models, and detect persistent anomalies."
        )

    # Case 2: Raw dataset exists, but analysis pipeline has not been executed yet
    if not analysis and raw_dataset:
        cols_str = ", ".join(f"`{c}`" for c in raw_dataset.get("columns", []))
        return (
            "### ACTIVE WORKSPACE TELEMETRY MANIFEST\n"
            f"- **Dataset File**: `{raw_dataset.get('name')}`\n"
            f"- **Total Raw Observations**: **{raw_dataset.get('row_count', 0):,} rows**\n"
            f"- **Telemetry Channels ({raw_dataset.get('column_count', 0)})**: {cols_str}\n"
            "- **Pipeline Status**: **RAW TELEMETRY LOADED (PIPELINE PENDING)**\n"
            "- **Contextual Baseline Models**: Not yet fitted. Run the analysis pipeline to train multivariate Ridge baseline regressions.\n"
            "- **Anomaly Detection**: 0 episodes evaluated. Multi-step persistence detection requires pipeline execution.\n\n"
            "*Direct the engineer to trigger `run_analysis_pipeline` or click 'RUN AUTONOMOUS ANALYSIS' in the overview interface to compute real baseline metrics and detect operational deviations.*"
        )

    # Case 3: Live analysis present with real calculations
    dataset = ctx.get("dataset") or {}
    profile_wrapper = ctx.get("profile") or {}
    profile = profile_wrapper.get("profile") if "profile" in profile_wrapper else profile_wrapper
    anomalies = ctx.get("anomalies") or []
    models = ctx.get("models") or []

    ds_name = analysis.get("dataset_name") or dataset.get("name") or "operational_telemetry.csv"
    row_count = analysis.get("row_count") or dataset.get("row_count") or (profile.get("row_count") if profile else 0)
    col_count = analysis.get("column_count") or dataset.get("column_count") or (profile.get("column_count") if profile else 0)
    health_score = analysis.get("data_health_score") or (profile.get("data_health_score") if profile else None)
    model_r2 = analysis.get("model_r2")

    entities = analysis.get("entities") or (profile.get("entity_summary", {}).get("entities") if profile else [])

    # Model metrics
    model_metrics = analysis.get("model_metrics") or {}
    ent_models = model_metrics.get("entities") if isinstance(model_metrics, dict) and "entities" in model_metrics else {}
    if not ent_models and models:
        for m in models:
            eq = m.get("model_id", "").split("-")[-1].upper()
            ent_models[eq] = m.get("metrics", {})

    anom_count = len(anomalies) if anomalies else (analysis.get("anomalies_detected") or 0)
    excess_energy_sum = sum(a.get("residual_score", 0.0) for a in anomalies if a.get("residual_score", 0.0) > 0.0)

    # Dynamic baseline table from real model metrics
    table_lines = []
    if ent_models:
        table_lines = [
            "| Equipment ID | Baseline $R^2$ | RMSE (kWh) | CV(RMSE) % | NMBE % | ASHRAE Guideline 14 Compliance |",
            "|:---|:---|:---|:---|:---|:---|",
        ]
        for eq, em in ent_models.items():
            r2_val = em.get("r2")
            rmse_val = em.get("rmse")
            cv_val = em.get("cv_rmse")
            nmbe_val = em.get("nmbe", 0.0)
            ashrae_comp = em.get("ashrae_compliant", (cv_val is not None and cv_val <= 30.0))

            r2_str = f"{r2_val:.4f}" if r2_val is not None else "N/A"
            rmse_str = f"{rmse_val:.2f}" if rmse_val is not None else "N/A"
            cv_str = f"{cv_val:.2f}%" if cv_val is not None else "N/A"
            nmbe_str = f"{nmbe_val:.2f}%" if nmbe_val is not None else "0.00%"
            comp_str = "PASS (<= 30% CV(RMSE))" if ashrae_comp else "FAIL (> 30% CV(RMSE))"
            table_lines.append(f"| `{eq}` | {r2_str} | {rmse_str} | {cv_str} | {nmbe_str} | **{comp_str}** |")

    # Dynamic anomaly lines from real anomalies
    # Exact severity distribution and prioritized anomaly ranking
    sev_weights = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    sorted_anomalies = sorted(
        anomalies,
        key=lambda x: (sev_weights.get(x.get("severity", "").upper(), 0), abs(x.get("residual_score", 0.0))),
        reverse=True,
    )
    from collections import Counter
    sev_counts = Counter(a.get("severity", "MEDIUM").upper() for a in anomalies)
    crit_count = sev_counts.get("CRITICAL", 0)
    high_count = sev_counts.get("HIGH", 0)
    med_count = sev_counts.get("MEDIUM", 0)
    low_count = sev_counts.get("LOW", 0)

    top_anom_lines = []
    if sorted_anomalies:
        for idx, a in enumerate(sorted_anomalies[:8], 1):
            p_cnt = a.get("persistence_count", 1)
            duration_hr = p_cnt * 0.5  # 30 min nominal cadence
            pz = a.get("peak_z_score", 0.0)
            top_anom_lines.append(
                f"{idx}. `{a.get('equipment_id')}` | Interval: {a.get('start_time')} to {a.get('end_time')} "
                f"| Persistence: {p_cnt} intervals ({duration_hr:.1f}h) "
                f"| Peak Z-Score: {pz:.2f}\u03c3 | Residual Delta: {a.get('residual_score', 0):+.1f} kWh | Severity: **{a.get('severity')}**"
            )
    else:
        top_anom_lines.append("*No persistent anomaly episodes detected above statistical thresholds.*")

    # Dynamic roles
    roles = profile.get("roles", {}) if profile else {}
    roles_lines = []
    if roles:
        for role_name, col_name in roles.items():
            roles_lines.append(f"  * **{role_name.replace('_', ' ').title()}**: `{col_name}`")
    elif profile and profile.get("column_profiles"):
        col_names = [c["name"] for c in profile.get("column_profiles", [])]
        roles_lines.append(f"  * **Available Channels**: {', '.join(f'`{c}`' for c in col_names)}")

    roles_section = ("#### Discovered Operational Variable Roles:\n" + "\n".join(roles_lines) + "\n\n") if roles_lines else ""

    health_str = f"**{health_score:.1f} / 100**" if health_score is not None else "N/A"
    r2_str = f" ($R^2 = {model_r2:.4f}$)" if model_r2 is not None else ""
    entities_str = ", ".join(f"`{e}`" for e in entities) if entities else "Fleet"

    manifest_parts = [
        "### ACTIVE WORKSPACE TELEMETRY & ML BASELINE MANIFEST",
        "The system is grounded in the live operational dataset and calculated ML baseline results:\n",
        f"- **Active Dataset File**: `{ds_name}` (Total Observations: **{row_count:,} rows**, **{col_count} telemetry channels**)",
        f"- **Telemetry Quality Health Score**: {health_str}",
        f"- **Monitored Fleet Entities**: {entities_str}\n",
    ]
    if roles_section:
        manifest_parts.append(roles_section)

    if table_lines:
        manifest_parts.append(
            f"#### Multivariate Contextual Baseline Model Performance{r2_str}:\n"
            f"Expected power consumption $\\hat{{y}}_t$ is computed via multivariate Ridge regression incorporating contextual and cyclic features:\n\n"
            + "\n".join(table_lines) + "\n\n"
        )

    manifest_parts.append(
        f"#### Persistent Anomaly Episodes & Energy Lift Findings:\n"
        f"- **Total Detected Persistent Episodes**: **{anom_count} episodes** across the fleet.\n"
        f"- **Exact Severity Breakdown**: **{crit_count} CRITICAL**, **{high_count} HIGH**, **{med_count} MEDIUM**, **{low_count} LOW**.\n"
        f"- **Persistence Standard**: Contiguous abnormal residual across $\\ge 3$ consecutive intervals ($\\ge 1.5$ hours). Isolated single-reading spikes are rejected as sensor noise.\n"
        f"- **Total Cumulative Fleet Excess Energy Lift**: **{excess_energy_sum:.1f} kWh** above expected baseline.\n"
        f"- **Top Monitored Anomaly Episodes (Prioritized by Criticality & Impact)**:\n"
        + "\n".join(top_anom_lines) + "\n\n"
    )

    manifest_parts.append(
        "#### Evidence Critic Zero-Trust Guardrail:\n"
        "- Telemetry strictly proves contextual energy deviation (elevated kWh relative to cooling load demand and ambient weather).\n"
        "- NEVER attribute anomalies to internal mechanical failures (e.g. compressor valve rupture, bearing failure, motor burnout) without physical acoustic/vibration sensors or physical inspection.\n"
        "- Always classify findings as: 'Persistent contextual energy deviation / operational degradation'."
    )

    return "\n".join(manifest_parts)


def format_preset_intent_directives(
    query: str,
    excess_energy: Optional[float] = None,
    overall_r2: Optional[float] = None,
    health_score: Optional[float] = None,
    anomaly_count: Optional[int] = None,
    entities: Optional[List[str]] = None,
) -> str:
    """Provide targeted engineering execution directives based on user query intent and real dataset context."""
    q = query.lower()
    directives = []

    ent_str = ", ".join(f"`{e}`" for e in entities) if entities else "the monitored equipment units"
    excess_str = f"{excess_energy:.1f} kWh" if excess_energy is not None and excess_energy > 0 else "calculated excess"
    anom_str = f"{anomaly_count} persistent anomaly episodes" if anomaly_count is not None else "detected anomaly episodes"
    r2_str = f" ($R^2 = {overall_r2:.4f}$)" if overall_r2 is not None else ""
    health_str = f" ({health_score:.1f}/100)" if health_score is not None else ""

    if any(k in q for k in ["lift", "energy lift", "excess energy", "excess kwh", "consumption"]):
        directives.append(
            r"- INTENT: EQUIPMENT ENERGY LIFT ANALYSIS" "\n"
            rf"  * Quantify the excess energy draw ($\Delta = \text{{Observed}} - \text{{Expected}}$) across {ent_str}." "\n"
            rf"  * Report the measured fleet excess energy lift ({excess_str}) across {anom_str}." "\n"
            rf"  * Compare individual unit contributions across {ent_str}, highlighting persistent episodes (durations $\ge 1.5$ hours)." "\n"
            rf"  * Explain how operating conditions (load demand, flow rates, and operating temperatures) correlate with the lift."
        )

    if any(k in q for k in ["baseline", "contextual baseline", "model", "r2", "r^2", "ashrae"]):
        directives.append(
            r"- INTENT: CONTEXTUAL BASELINE MODEL EXPLANATION" "\n"
            rf"  * Detail the multivariate regression formulation $\hat{{y}}_t = f(\text{{Operating Load}}, \text{{Hydraulics}}, \text{{Temperatures}}, \text{{Weather}}, \sin/\cos \text{{Cyclics}})$." "\n"
            rf"  * Cite the exact overall baseline fit{r2_str} and individual equipment metrics against ASHRAE Guideline 14 criteria ($CV(RMSE) \le 30\%$, $|NMBE| \le 10\%$). If models are not yet trained, state that baseline pipeline must be run." "\n"
            rf"  * Contrast this against naive static thresholds, explaining why contextual modeling eliminates false alarms during weather and cooling demand swings."
        )

    if any(k in q for k in ["critic", "evidence", "claim", "guardrail", "zero-trust", "root cause"]):
        directives.append(
            r"- INTENT: EVIDENCE CRITIC VALIDATION" "\n"
            r"  * Explain the zero-trust boundary separating telemetry-supported evidence from unsupported physical root-cause claims." "\n"
            r"  * Emphasize why sensor telemetry proves energy lift and inefficient heat exchange, but CANNOT establish internal mechanical failures (like compressor motor burnout) without vibration or acoustic sensors." "\n"
            r"  * Present the validated claim format required for operational facility sign-off."
        )

    if any(k in q for k in ["report", "executive", "summary", "briefing", "overview"]):
        directives.append(
            r"- INTENT: EXECUTIVE ENGINEERING REPORT" "\n"
            rf"  * Synthesize the complete engineering investigation into a structured executive report." "\n"
            rf"  * Include Dataset Health{health_str}, Baseline Fit{r2_str}, Persistent Anomalies ({anom_str}), Measured Excess Energy ({excess_str}), and prioritized operational action items."
        )

    if not directives:
        directives.append(
            r"- INTENT: GENERAL ENGINEERING INQUIRY" "\n"
            rf"  * Answer directly and authoritatively, citing empirical dataset parameters, baseline statistics{r2_str}, and detected persistent anomaly episodes ({anom_str}, {excess_str} excess)."
        )

    return "### ACTIVE INQUIRY DIRECTIVE\n" + "\n".join(directives)


def build_initial_prompt(
    user_query: str,
    manifests: Optional[List[str]] = None,
    tech_stack: Optional[List[str]] = None,
    file_tree: Optional[List[str]] = None,
    attached_files: Optional[Dict[str, str]] = None,
    engineering_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Construct modular initial prompt with comprehensive telemetry and baseline intelligence."""
    clean_query = user_query.strip()
    manifests_str = ", ".join(manifests) if manifests else "None detected"
    stack_str = ", ".join(tech_stack) if tech_stack else "Generic / Linux"
    tree_str = "\n".join(f"- {f}" for f in file_tree) if file_tree else "- (Project Root)"

    attached_section = ""
    if attached_files:
        snippets = []
        for path, content in attached_files.items():
            ext = path.split(".")[-1] if "." in path else ""
            snippets.append(f"=== File: {path} ===\n```{ext}\n{content.strip()}\n```")
        attached_section = (
            "### ATTACHED WORKSPACE SOURCE CODE (LOADED FROM LOCAL DISK)\n"
            "The following live workspace files are attached directly from the local filesystem:\n\n"
            + "\n\n".join(snippets) + "\n\n"
            "All source code above is complete and loaded from the active workspace.\n"
            "Analyze and explain this source code directly. Never claim files are missing or that you lack source bodies.\n\n"
        )

    if not engineering_context:
        engineering_context = load_live_engineering_context()

    telemetry_manifest = format_telemetry_dataset_manifest(engineering_context)

    anoms = engineering_context.get("anomalies") or []
    analysis = engineering_context.get("analysis") or {}
    prof_wrapper = engineering_context.get("profile") or {}
    prof = prof_wrapper.get("profile") if "profile" in prof_wrapper else prof_wrapper

    excess_energy_sum = sum(a.get("residual_score", 0.0) for a in anoms if a.get("residual_score", 0.0) > 0.0)
    m_r2 = analysis.get("model_r2")
    h_score = analysis.get("data_health_score") or (prof.get("data_health_score") if prof else None)
    anom_c = len(anoms) if anoms else analysis.get("anomalies_detected")
    entities = analysis.get("entities") or (prof.get("entity_summary", {}).get("entities") if prof else [])

    intent_directives = format_preset_intent_directives(
        clean_query,
        excess_energy=excess_energy_sum if excess_energy_sum > 0 else None,
        overall_r2=m_r2,
        health_score=h_score,
        anomaly_count=anom_c,
        entities=entities,
    )

    return (
        f"{CORE_IDENTITY_PROMPT}\n\n"
        f"{TOOL_PROTOCOL_PROMPT}\n\n"
        f"{PROACTIVE_TRIGGERS_PROMPT}\n\n"
        f"### ACTIVE PROJECT CONTEXT\n"
        f"Project Root: . (Current Working Directory)\n"
        f"Tech Stack: {stack_str}\n"
        f"Manifests: {manifests_str}\n"
        f"Key Files:\n{tree_str}\n\n"
        f"{telemetry_manifest}\n\n"
        f"{intent_directives}\n\n"
        f"{attached_section}"
        f"### USER REQUEST\n"
        f"Request: {clean_query}\n\n"
        f"### INSTRUCTION\n"
        f"Respond directly and authoritatively to the user's request. Draw directly upon the active telemetry dataset manifest, baseline model statistics, and persistent anomaly episodes. No conversational filler or meta-disclaimers."
    )


def build_observation_prompt(
    executed_tools: List[Dict[str, Any]],
    turn: int,
    max_turns: int,
) -> str:
    """Format tool observations and inject targeted self-directed triggers."""
    obs_lines: List[str] = [f"[V.O.I.D.E. TOOL OBSERVATIONS - TURN {turn}/{max_turns}]"]
    has_error = False
    has_file_write = False
    has_retrieval = False
    has_verification = False

    for t in executed_tools:
        tool_name = t.get("tool", "unknown")
        status = t.get("status", "UNKNOWN")

        if status in ("ERROR", "FAILED") or t.get("exit_code", 0) != 0:
            has_error = True

        if tool_name == "read_file":
            has_retrieval = True
            content = t.get("content", "")
            start = t.get("start_line", 1)
            lines = content.splitlines()
            numbered = "\n".join(f"{start + idx}: {line}" for idx, line in enumerate(lines[:120]))
            obs_lines.append(
                f"Tool 'read_file' ({t.get('path')}): Status {status}, Lines {start}-{start + len(lines) - 1} of {t.get('total_lines', len(lines))}\n"
                f"Content:\n{numbered}"
            )
        elif tool_name == "search_files":
            has_retrieval = True
            matches = t.get("matches", [])
            obs_lines.append(
                f"Tool 'search_files' ('{t.get('query')}'): Found {len(matches)} match(es):\n"
                f"{json.dumps(matches[:15], indent=2)}"
            )
        elif tool_name == "list_directory":
            has_retrieval = True
            entries = t.get("entries", [])
            obs_lines.append(
                f"Tool 'list_directory' ({t.get('path') or '.'}): {len(entries)} entries:\n"
                f"{json.dumps(entries[:30], indent=2)}"
            )
        elif tool_name == "bash":
            has_verification = True
            exit_code = t.get("exit_code", 0)
            obs_lines.append(
                f"Tool 'bash' (`{t.get('command')}`): Exit Code {exit_code}\n"
                f"Stdout:\n{t.get('stdout', '').strip()[:1500]}\n"
                f"Stderr:\n{t.get('stderr', '').strip()[:1500]}"
            )
        elif tool_name in ("bash_start", "check_process", "wait_process"):
            obs_lines.append(
                f"Tool '{tool_name}' ({t.get('process_id')}): Status {status}\n"
                f"Details:\n{json.dumps(t, indent=2)}"
            )
        elif tool_name in ("write_file", "patch_file"):
            has_file_write = True
            obs_lines.append(f"Tool '{tool_name}' ({t.get('path')}): Status {status} - {t.get('message', '')}")
        else:
            obs_lines.append(f"Tool '{tool_name}': {json.dumps(t)}")

    if has_error:
        trigger_directive = (
            "### ACTIVE PROACTIVE TRIGGER: [AUTONOMOUS SELF-HEALING]\n"
            "An error or non-zero exit code occurred during execution. "
            "Analyze the failure and stack trace above, locate the defect, and emit a corrective `patch_file` or `write_file` tool call immediately. "
            "Do NOT ask the engineer. Fix the issue autonomously."
        )
    elif has_file_write and not has_verification:
        trigger_directive = (
            "### ACTIVE PROACTIVE TRIGGER: [VERIFY MACHINE TRUTH]\n"
            "File modifications were applied successfully. "
            "Now proactively verify your changes using `bash` (e.g. run test suite, compile check, or linter) "
            "to prove zero syntax errors or regressions."
        )
    elif has_retrieval and not has_file_write:
        trigger_directive = (
            "### ACTIVE PROACTIVE TRIGGER: [IMPLEMENT]\n"
            "Required context and files have been retrieved. "
            "Now proactively proceed with implementation using `patch_file` (for surgical edits) or `write_file` (for new modules)."
        )
    else:
        trigger_directive = (
            "### ACTIVE PROACTIVE TRIGGER: [EVALUATION & COMPLETION]\n"
            "If all implementation and verification steps are complete with verified machine truth, provide a crisp, technical summary of what was accomplished. "
            "If further proactive actions (more tests, build steps, or tracking) are required, emit the next `tool_call`."
        )

    obs_lines.append(f"\n{trigger_directive}")
    return "\n".join(obs_lines)


def build_followup_prompt(
    user_query: str,
    attached_files: Optional[Dict[str, str]] = None,
    engineering_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Construct concise follow-up prompt with live telemetry awareness."""
    clean_query = user_query.strip()
    attached_section = ""
    if attached_files:
        snippets = []
        for path, content in attached_files.items():
            ext = path.split(".")[-1] if "." in path else ""
            snippets.append(f"=== File: {path} ===\n```{ext}\n{content.strip()}\n```")
        attached_section = (
            "### UPDATED WORKSPACE FILES (LOADED FROM LOCAL DISK)\n"
            + "\n\n".join(snippets) + "\n\n"
        )

    if not engineering_context:
        engineering_context = load_live_engineering_context()

    telemetry_manifest = format_telemetry_dataset_manifest(engineering_context)

    anoms = engineering_context.get("anomalies") or []
    analysis = engineering_context.get("analysis") or {}
    prof_wrapper = engineering_context.get("profile") or {}
    prof = prof_wrapper.get("profile") if "profile" in prof_wrapper else prof_wrapper

    excess_energy_sum = sum(a.get("residual_score", 0.0) for a in anoms if a.get("residual_score", 0.0) > 0.0)
    m_r2 = analysis.get("model_r2")
    h_score = analysis.get("data_health_score") or (prof.get("data_health_score") if prof else None)
    anom_c = len(anoms) if anoms else analysis.get("anomalies_detected")
    entities = analysis.get("entities") or (prof.get("entity_summary", {}).get("entities") if prof else [])

    intent_directives = format_preset_intent_directives(
        clean_query,
        excess_energy=excess_energy_sum if excess_energy_sum > 0 else None,
        overall_r2=m_r2,
        health_score=h_score,
        anomaly_count=anom_c,
        entities=entities,
    )

    return (
        f"[V.O.I.D.E. CONVERSATION CONTINUATION]\n"
        f"Continue operating as V.O.I.D.E. Senior Systems Architect & Engineering Data Intelligence specialist.\n\n"
        f"{telemetry_manifest}\n\n"
        f"{intent_directives}\n\n"
        f"{attached_section}"
        f"User Request: {clean_query}\n\n"
        f"Respond directly and authoritatively with exact empirical calculations and metrics without conversational filler or disclaimers."
    )
