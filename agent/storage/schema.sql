-- V.O.I.D.E. Durable Task & Agent State Schema (SQLite)
-- Strictly parameterized, transaction-safe, crash-resilient

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    root_path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    workspace TEXT NOT NULL,
    status TEXT NOT NULL, -- AGENT_IDLE, AGENT_EXECUTING, AGENT_AWAITING_APPROVAL, COMPLETED, ERROR_RECOVERY
    phase TEXT NOT NULL,  -- PLANNING, INSPECTING, IMPLEMENTING, TESTING, VERIFYING, ANALYZE_FAIL, FIXING
    plan_json TEXT,
    current_step INTEGER NOT NULL DEFAULT 0,
    success_criteria_json TEXT NOT NULL DEFAULT '[]',
    iteration INTEGER NOT NULL DEFAULT 0,
    max_iterations INTEGER NOT NULL DEFAULT 25,
    last_action TEXT,
    last_observation TEXT,
    last_verified_checkpoint TEXT,
    pending_approval TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    steps_json TEXT NOT NULL,
    current_step INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tool_calls (
    request_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    tool TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    status TEXT NOT NULL, -- pending, running, success, failure, denied
    risk_tier TEXT NOT NULL DEFAULT 'LOW', -- LOW, MEDIUM, HIGH
    started_at REAL NOT NULL,
    finished_at REAL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(request_id) REFERENCES tool_calls(request_id) ON DELETE CASCADE,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step INTEGER NOT NULL,
    workspace_snapshot_json TEXT NOT NULL,
    state_snapshot_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    task_id TEXT,
    priority TEXT NOT NULL DEFAULT 'NORMAL',
    correlation_id TEXT,
    data_json TEXT NOT NULL DEFAULT '{}',
    timestamp REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS browser_mappings (
    mapping_version INTEGER NOT NULL,
    page_key TEXT NOT NULL,
    elements_json TEXT NOT NULL,
    confidence_summary_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (mapping_version, page_key)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    risk_tier TEXT NOT NULL,
    request_json TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, APPROVED, REJECTED
    user_id TEXT NOT NULL DEFAULT 'local_user',
    created_at REAL NOT NULL,
    decided_at REAL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tool_calls_task ON tool_calls(task_id);
CREATE INDEX IF NOT EXISTS idx_observations_task ON observations(task_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);

-- Chat History & Persistent Conversations
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    workspace_root TEXT NOT NULL,
    title TEXT NOT NULL,
    conversation_url TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL, -- user, assistant, tool
    content TEXT NOT NULL,
    tool_data_json TEXT,
    timestamp REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_workspace ON chat_sessions(workspace_root);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

-- ============================================================================
-- Engineering Data Intelligence Domain Entities
-- ============================================================================

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    row_count INTEGER,
    column_count INTEGER,
    format TEXT NOT NULL,
    schema_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS data_profiles (
    profile_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feature_sets (
    feature_set_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    source_columns_json TEXT NOT NULL,
    transforms_json TEXT NOT NULL,
    feature_names_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    model_type TEXT NOT NULL,
    target_column TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT NOT NULL,
    plan_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    equipment_id TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    severity TEXT NOT NULL, -- LOW, MEDIUM, HIGH, CRITICAL
    persistence_count INTEGER NOT NULL DEFAULT 1,
    residual_score REAL NOT NULL,
    peak_z_score REAL NOT NULL DEFAULT 0.0,
    multivariate_score REAL NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL, -- CANDIDATE, CONFIRMED, REJECTED, UNDER_REVIEW
    interpretation TEXT,
    evidence_id TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY(analysis_id) REFERENCES analyses(analysis_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    anomaly_id TEXT,
    observations_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS external_sources (
    source_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    source_type TEXT NOT NULL,
    retrieved_at REAL NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visual_artifacts (
    artifact_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    visual_type TEXT NOT NULL,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    FOREIGN KEY(analysis_id) REFERENCES analyses(analysis_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(analysis_id) REFERENCES analyses(analysis_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS human_decisions (
    decision_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    anomaly_id TEXT,
    decision TEXT NOT NULL, -- APPROVED, REJECTED, MODIFIED, REQUEST_INFO
    reason TEXT,
    notes TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY(analysis_id) REFERENCES analyses(analysis_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recovery_events (
    recovery_id TEXT PRIMARY KEY,
    analysis_id TEXT,
    failure_class TEXT NOT NULL, -- DATA, PARSER, SCHEMA, FEATURE, MODEL, TOOL, EXTERNAL, EVIDENCE, AGENT
    action_taken TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    result TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_datasets_hash ON datasets(file_hash);
CREATE INDEX IF NOT EXISTS idx_anomalies_analysis ON anomalies(analysis_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_equipment ON anomalies(equipment_id);
CREATE INDEX IF NOT EXISTS idx_visual_artifacts_analysis ON visual_artifacts(analysis_id);
CREATE INDEX IF NOT EXISTS idx_reports_analysis ON reports(analysis_id);

