"""Durable State Store for V.O.I.D.E. using SQLite.

Ensures task state survives restarts, crashes, model retries, and network drops.
Enforces zero-trust parameterized queries and atomic transactions.
"""

from __future__ import annotations
import json
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


class StateStore:
    """Thread-safe, transaction-oriented SQLite repository for V.O.I.D.E."""

    def __init__(self, db_path: str) -> None:
        self.db_path: str = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        with self._get_connection() as conn:
            conn.executescript(schema_sql)
            try:
                conn.execute("ALTER TABLE chat_sessions ADD COLUMN conversation_url TEXT")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE anomalies ADD COLUMN peak_z_score REAL DEFAULT 0.0")
            except Exception:
                pass

    # ----------------- Projects -----------------

    def register_project(self, root_path: str, name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        project_id = f"proj-{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (project_id, root_path, name, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(root_path) DO UPDATE SET name=excluded.name
                """,
                (project_id, os.path.realpath(root_path), name, json.dumps(metadata or {}), now),
            )
            row = conn.execute("SELECT project_id FROM projects WHERE root_path = ?", (os.path.realpath(root_path),)).fetchone()
            return str(row["project_id"])

    # ----------------- Tasks -----------------

    def create_task(
        self,
        project_id: str,
        objective: str,
        workspace: str,
        success_criteria: Optional[List[Dict[str, Any]]] = None,
        max_iterations: int = 25,
    ) -> str:
        task_id = f"task-{int(time.time())}-{uuid.uuid4().hex[:4]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, project_id, objective, workspace, status, phase,
                    success_criteria_json, iteration, max_iterations, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'AGENT_IDLE', 'PLANNING', ?, 0, ?, ?, ?)
                """,
                (task_id, project_id, objective, os.path.realpath(workspace), json.dumps(success_criteria or []), max_iterations, now, now),
            )
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["success_criteria"] = json.loads(data.get("success_criteria_json") or "[]")
            data["plan"] = json.loads(data["plan_json"]) if data.get("plan_json") else None
            return data

    def update_task_state(
        self,
        task_id: str,
        status: Optional[str] = None,
        phase: Optional[str] = None,
        current_step: Optional[int] = None,
        iteration_increment: int = 0,
        last_action: Optional[str] = None,
        last_observation: Optional[str] = None,
        pending_approval: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.cursor()
            updates: List[str] = ["updated_at = ?"]
            params: List[Any] = [now]

            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if phase is not None:
                updates.append("phase = ?")
                params.append(phase)
            if current_step is not None:
                updates.append("current_step = ?")
                params.append(current_step)
            if iteration_increment > 0:
                updates.append("iteration = iteration + ?")
                params.append(iteration_increment)
            if last_action is not None:
                updates.append("last_action = ?")
                params.append(last_action)
            if last_observation is not None:
                updates.append("last_observation = ?")
                params.append(last_observation)
            if pending_approval is not None:
                updates.append("pending_approval = ?")
                params.append(pending_approval)

            params.append(task_id)
            cur.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?", params)

    # ----------------- Plans -----------------

    def save_plan(self, task_id: str, steps: List[Dict[str, Any]], version: int = 1) -> str:
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO plans (plan_id, task_id, version, steps_json, current_step, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (plan_id, task_id, version, json.dumps(steps), now),
            )
            conn.execute(
                "UPDATE tasks SET plan_json = ?, updated_at = ? WHERE task_id = ?",
                (json.dumps(steps), now, task_id),
            )
        return plan_id

    # ----------------- Tool Calls & Observations -----------------

    def record_tool_call(
        self,
        request_id: str,
        task_id: str,
        tool: str,
        arguments: Dict[str, Any],
        risk_tier: str = "LOW",
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tool_calls (request_id, task_id, tool, arguments_json, status, risk_tier, started_at)
                VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (request_id, task_id, tool, json.dumps(arguments), risk_tier, now),
            )

    def complete_tool_call(
        self,
        request_id: str,
        status: str,
        observation_payload: Dict[str, Any],
        observation_type: str = "result",
    ) -> str:
        now = time.time()
        obs_id = f"obs-{uuid.uuid4().hex[:8]}"
        payload_str = json.dumps(observation_payload)
        import hashlib
        content_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        with self._get_connection() as conn:
            row = conn.execute("SELECT task_id FROM tool_calls WHERE request_id = ?", (request_id,)).fetchone()
            task_id = row["task_id"] if row else ""
            conn.execute(
                "UPDATE tool_calls SET status = ?, finished_at = ? WHERE request_id = ?",
                (status, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO observations (observation_id, request_id, task_id, type, payload_json, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (obs_id, request_id, task_id, observation_type, payload_str, content_hash, now),
            )
        return obs_id

    # ----------------- Checkpoints -----------------

    def create_checkpoint(
        self,
        task_id: str,
        phase: str,
        step: int,
        workspace_snapshot: Dict[str, Any],
        state_snapshot: Dict[str, Any],
    ) -> str:
        checkpoint_id = f"ckpt-{int(time.time())}-{uuid.uuid4().hex[:4]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (checkpoint_id, task_id, phase, step, workspace_snapshot_json, state_snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (checkpoint_id, task_id, phase, step, json.dumps(workspace_snapshot), json.dumps(state_snapshot), now),
            )
            conn.execute(
                "UPDATE tasks SET last_verified_checkpoint = ?, updated_at = ? WHERE task_id = ?",
                (checkpoint_id, now, task_id),
            )
        return checkpoint_id

    def get_latest_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["workspace_snapshot"] = json.loads(data["workspace_snapshot_json"])
            data["state_snapshot"] = json.loads(data["state_snapshot_json"])
            return data

    # ----------------- Events -----------------

    def emit_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
        task_id: Optional[str] = None,
        priority: str = "NORMAL",
        correlation_id: Optional[str] = None,
    ) -> str:
        event_id = f"evt-{int(time.time())}-{uuid.uuid4().hex[:4]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO events (event_id, event_type, source, task_id, priority, correlation_id, data_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, event_type, source, task_id, priority, correlation_id, json.dumps(data), now),
            )
        return event_id

    def get_events(self, task_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if task_id:
                rows = conn.execute(
                    "SELECT * FROM events WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                {
                    **dict(r),
                    "data": json.loads(r["data_json"]),
                }
                for r in reversed(rows)
            ]

    # ----------------- Approvals -----------------

    def request_approval(self, task_id: str, risk_tier: str, request_data: Dict[str, Any]) -> str:
        approval_id = f"appr-{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO approvals (approval_id, task_id, risk_tier, request_json, status, created_at)
                VALUES (?, ?, ?, ?, 'PENDING', ?)
                """,
                (approval_id, task_id, risk_tier, json.dumps(request_data), now),
            )
            conn.execute(
                "UPDATE tasks SET status = 'AGENT_AWAITING_APPROVAL', pending_approval = ?, updated_at = ? WHERE task_id = ?",
                (approval_id, now, task_id),
            )
        return approval_id

    def decide_approval(self, approval_id: str, approved: bool) -> Optional[Dict[str, Any]]:
        now = time.time()
        status = "APPROVED" if approved else "REJECTED"
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
            if not row:
                return None
            task_id = row["task_id"]
            conn.execute(
                "UPDATE approvals SET status = ?, decided_at = ? WHERE approval_id = ?",
                (status, now, approval_id),
            )
            next_status = "AGENT_EXECUTING" if approved else "AGENT_IDLE"
            conn.execute(
                "UPDATE tasks SET status = ?, pending_approval = NULL, updated_at = ? WHERE task_id = ?",
                (next_status, now, task_id),
            )
            data = dict(row)
            data["status"] = status
            data["decided_at"] = now
            return data

    # ----------------- Chat History & Sessions -----------------

    def create_chat_session(self, workspace_root: str, title: str = "New Chat", conversation_url: Optional[str] = None) -> Dict[str, Any]:
        session_id = f"chat-{int(time.time())}-{uuid.uuid4().hex[:4]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (session_id, workspace_root, title, conversation_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, os.path.realpath(workspace_root), title, conversation_url, now, now),
            )
        return {
            "session_id": session_id,
            "workspace_root": os.path.realpath(workspace_root),
            "title": title,
            "conversation_url": conversation_url,
            "created_at": now,
            "updated_at": now,
        }

    def update_session_url(self, session_id: str, conversation_url: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE chat_sessions SET conversation_url = ?, updated_at = ? WHERE session_id = ?",
                (conversation_url, time.time(), session_id),
            )
            return cur.rowcount > 0

    def get_chat_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_chat_sessions(self, workspace_root: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if workspace_root:
                rows = conn.execute(
                    """
                    SELECT s.*, count(m.message_id) as message_count
                    FROM chat_sessions s
                    LEFT JOIN chat_messages m ON s.session_id = m.session_id
                    WHERE s.workspace_root = ?
                    GROUP BY s.session_id
                    ORDER BY s.updated_at DESC
                    LIMIT ?
                    """,
                    (os.path.realpath(workspace_root), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT s.*, count(m.message_id) as message_count
                    FROM chat_sessions s
                    LEFT JOIN chat_messages m ON s.session_id = m.session_id
                    GROUP BY s.session_id
                    ORDER BY s.updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def ensure_chat_session(self, session_id: str, workspace_root: Optional[str] = None, title: str = "New Chat") -> None:
        now = time.time()
        ws = os.path.realpath(workspace_root) if workspace_root else os.path.dirname(os.path.dirname(os.path.abspath(self.db_path)))
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (session_id, workspace_root, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (session_id, ws, title, now, now),
            )

    def add_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        message_id = f"msg-{int(time.time())}-{uuid.uuid4().hex[:4]}"
        now = time.time()
        tool_json = json.dumps(tool_data) if tool_data else None
        ws = os.path.dirname(os.path.dirname(os.path.abspath(self.db_path)))
        with self._get_connection() as conn:
            # Defensive guarantee: Ensure parent session exists to prevent foreign key violations
            conn.execute(
                """
                INSERT INTO chat_sessions (session_id, workspace_root, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (session_id, ws, "Chat Session", now, now),
            )
            conn.execute(
                """
                INSERT INTO chat_messages (message_id, session_id, role, content, tool_data_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, tool_json, now),
            )
            # Update session's updated_at and update title if it's the first user message
            row_count = conn.execute(
                "SELECT count(*) as cnt FROM chat_messages WHERE session_id = ?", (session_id,)
            ).fetchone()["cnt"]
            if row_count <= 2 and role == "user":
                clean_title = content.strip().replace("\n", " ")[:40]
                conn.execute(
                    "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                    (clean_title, now, session_id),
                )
            else:
                conn.execute(
                    "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
                    (now, session_id),
                )
        return {
            "message_id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_data": tool_data,
            "timestamp": now,
        }

    def get_chat_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
            messages = []
            for r in rows:
                d = dict(r)
                d["tool_data"] = json.loads(d["tool_data_json"]) if d.get("tool_data_json") else None
                messages.append(d)
            return messages

    def delete_chat_session(self, session_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            return cur.rowcount > 0

    # ----------------- Data Intelligence Repositories -----------------

    def register_dataset(
        self,
        dataset_id: str,
        name: str,
        file_path: str,
        file_hash: str,
        row_count: int,
        column_count: int,
        format_type: str,
        schema_dict: Optional[Dict[str, Any]] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO datasets (
                    dataset_id, name, file_path, file_hash, row_count, column_count, format,
                    schema_json, provenance_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    name=excluded.name,
                    row_count=excluded.row_count,
                    column_count=excluded.column_count,
                    schema_json=excluded.schema_json,
                    provenance_json=excluded.provenance_json
                """,
                (
                    dataset_id,
                    name,
                    file_path,
                    file_hash,
                    row_count,
                    column_count,
                    format_type,
                    json.dumps(schema_dict or {}),
                    json.dumps(provenance or {}),
                    now,
                ),
            )
        return dataset_id

    def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["schema"] = json.loads(d["schema_json"]) if d.get("schema_json") else {}
            d["provenance"] = json.loads(d["provenance_json"]) if d.get("provenance_json") else {}
            return d

    def list_datasets(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM datasets ORDER BY created_at DESC").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["schema"] = json.loads(d["schema_json"]) if d.get("schema_json") else {}
                d["provenance"] = json.loads(d["provenance_json"]) if d.get("provenance_json") else {}
                results.append(d)
            return results

    def save_data_profile(self, profile_id: str, dataset_id: str, profile: Dict[str, Any]) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO data_profiles (profile_id, dataset_id, profile_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET profile_json=excluded.profile_json
                """,
                (profile_id, dataset_id, json.dumps(profile), now),
            )
        return profile_id

    def get_data_profile(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM data_profiles WHERE dataset_id = ? ORDER BY created_at DESC LIMIT 1",
                (dataset_id,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["profile"] = json.loads(d["profile_json"]) if d.get("profile_json") else {}
            return d

    def record_feature_set(
        self,
        feature_set_id: str,
        dataset_id: str,
        source_columns: List[str],
        transforms: List[Dict[str, Any]],
        feature_names: List[str],
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO feature_sets (
                    feature_set_id, dataset_id, source_columns_json, transforms_json, feature_names_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    feature_set_id,
                    dataset_id,
                    json.dumps(source_columns),
                    json.dumps(transforms),
                    json.dumps(feature_names),
                    now,
                ),
            )
        return feature_set_id

    def record_model(
        self,
        model_id: str,
        dataset_id: str,
        model_type: str,
        target_column: str,
        metrics: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO models (model_id, dataset_id, model_type, target_column, metrics_json, parameters_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET metrics_json=excluded.metrics_json, parameters_json=excluded.parameters_json
                """,
                (model_id, dataset_id, model_type, target_column, json.dumps(metrics), json.dumps(parameters), now),
            )
        return model_id

    def record_analysis(
        self,
        analysis_id: str,
        project_id: str,
        dataset_id: str,
        objective: str,
        status: str = "IN_PROGRESS",
        phase: str = "PLANNING",
        plan: Optional[List[Dict[str, Any]]] = None,
        summary: Optional[str] = None,
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO analyses (
                    analysis_id, project_id, dataset_id, objective, status, phase, plan_json, summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id) DO UPDATE SET
                    status=excluded.status,
                    phase=excluded.phase,
                    plan_json=excluded.plan_json,
                    summary=excluded.summary,
                    updated_at=excluded.updated_at
                """,
                (
                    analysis_id,
                    project_id,
                    dataset_id,
                    objective,
                    status,
                    phase,
                    json.dumps(plan or []),
                    summary,
                    now,
                    now,
                ),
            )
        return analysis_id

    def update_analysis_state(
        self,
        analysis_id: str,
        status: Optional[str] = None,
        phase: Optional[str] = None,
        plan: Optional[List[Dict[str, Any]]] = None,
        summary: Optional[str] = None,
    ) -> None:
        now = time.time()
        fields = ["updated_at = ?"]
        params: List[Any] = [now]
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if phase is not None:
            fields.append("phase = ?")
            params.append(phase)
        if plan is not None:
            fields.append("plan_json = ?")
            params.append(json.dumps(plan))
        if summary is not None:
            fields.append("summary = ?")
            params.append(summary)
        params.append(analysis_id)
        sql = f"UPDATE analyses SET {', '.join(fields)} WHERE analysis_id = ?"
        with self._get_connection() as conn:
            conn.execute(sql, tuple(params))

    def list_models_for_dataset(self, dataset_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM models WHERE dataset_id = ? ORDER BY created_at DESC", (dataset_id,)).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["metrics"] = json.loads(d["metrics_json"]) if d.get("metrics_json") else {}
                d["parameters"] = json.loads(d["parameters_json"]) if d.get("parameters_json") else {}
                results.append(d)
            return results

    def get_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("plan_json"):
                try:
                    parsed = json.loads(d["plan_json"])
                    if isinstance(parsed, dict) and "pipeline_meta" in parsed:
                        d.update(parsed["pipeline_meta"])
                        d["plan"] = parsed.get("steps", [])
                    elif isinstance(parsed, list):
                        d["plan"] = parsed
                    else:
                        d["plan"] = []
                except Exception:
                    d["plan"] = []
            else:
                d["plan"] = []
            return d

    def get_latest_analysis(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT 1").fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("plan_json"):
                try:
                    parsed = json.loads(d["plan_json"])
                    if isinstance(parsed, dict) and "pipeline_meta" in parsed:
                        d.update(parsed["pipeline_meta"])
                        d["plan"] = parsed.get("steps", [])
                    elif isinstance(parsed, list):
                        d["plan"] = parsed
                    else:
                        d["plan"] = []
                except Exception:
                    d["plan"] = []
            else:
                d["plan"] = []
            return d

    def record_anomaly(
        self,
        anomaly_id: str,
        analysis_id: str,
        equipment_id: str,
        start_time: str,
        end_time: str,
        severity: str,
        persistence_count: int,
        residual_score: float,
        multivariate_score: float,
        confidence: float,
        status: str,
        interpretation: str,
        evidence_id: Optional[str] = None,
        peak_z_score: float = 0.0,
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO anomalies (
                    anomaly_id, analysis_id, equipment_id, start_time, end_time, severity,
                    persistence_count, residual_score, peak_z_score, multivariate_score, confidence, status,
                    interpretation, evidence_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(anomaly_id) DO UPDATE SET
                    severity=excluded.severity,
                    persistence_count=excluded.persistence_count,
                    residual_score=excluded.residual_score,
                    peak_z_score=excluded.peak_z_score,
                    multivariate_score=excluded.multivariate_score,
                    confidence=excluded.confidence,
                    status=excluded.status,
                    interpretation=excluded.interpretation
                """,
                (
                    anomaly_id,
                    analysis_id,
                    equipment_id,
                    start_time,
                    end_time,
                    severity,
                    persistence_count,
                    residual_score,
                    peak_z_score,
                    multivariate_score,
                    confidence,
                    status,
                    interpretation,
                    evidence_id,
                    now,
                ),
            )
        return anomaly_id

    def list_anomalies(self, analysis_id: str, equipment_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if equipment_id:
                rows = conn.execute(
                    "SELECT * FROM anomalies WHERE analysis_id = ? AND equipment_id = ? ORDER BY severity DESC, start_time ASC",
                    (analysis_id, equipment_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM anomalies WHERE analysis_id = ? ORDER BY severity DESC, start_time ASC",
                    (analysis_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def update_anomaly_status(self, anomaly_id: str, status: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("UPDATE anomalies SET status = ? WHERE anomaly_id = ?", (status, anomaly_id))
            return cursor.rowcount > 0

    def record_evidence(
        self,
        evidence_id: str,
        anomaly_id: Optional[str],
        observations: Dict[str, Any],
        source_refs: List[str],
        metrics: Dict[str, Any],
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO evidence (evidence_id, anomaly_id, observations_json, source_refs_json, metrics_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    observations_json=excluded.observations_json,
                    source_refs_json=excluded.source_refs_json,
                    metrics_json=excluded.metrics_json
                """,
                (evidence_id, anomaly_id, json.dumps(observations), json.dumps(source_refs), json.dumps(metrics), now),
            )
        return evidence_id

    def get_evidence(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["observations"] = json.loads(d["observations_json"]) if d.get("observations_json") else {}
            d["source_refs"] = json.loads(d["source_refs_json"]) if d.get("source_refs_json") else []
            d["metrics"] = json.loads(d["metrics_json"]) if d.get("metrics_json") else {}
            return d

    def record_visual_artifact(
        self,
        artifact_id: str,
        analysis_id: str,
        visual_type: str,
        title: str,
        file_path: str,
        source_refs: Optional[List[str]] = None,
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO visual_artifacts (
                    artifact_id, analysis_id, visual_type, title, file_path, source_refs_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    analysis_id=excluded.analysis_id,
                    visual_type=excluded.visual_type,
                    title=excluded.title,
                    file_path=excluded.file_path,
                    source_refs_json=excluded.source_refs_json,
                    created_at=excluded.created_at
                """,
                (artifact_id, analysis_id, visual_type, title, file_path, json.dumps(source_refs or []), now),
            )
        return artifact_id

    def list_visual_artifacts(self, analysis_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = []
            if analysis_id:
                rows = conn.execute(
                    "SELECT * FROM visual_artifacts WHERE analysis_id = ? ORDER BY created_at ASC",
                    (analysis_id,),
                ).fetchall()
            if not rows:
                rows = conn.execute(
                    "SELECT * FROM visual_artifacts ORDER BY created_at DESC LIMIT 30"
                ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["source_refs"] = json.loads(d["source_refs_json"]) if d.get("source_refs_json") else []
                results.append(d)
            return results

    def save_report(
        self,
        report_id: str,
        analysis_id: str,
        title: str,
        content_markdown: str,
        file_path: str,
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO reports (report_id, analysis_id, title, content_markdown, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    title=excluded.title,
                    content_markdown=excluded.content_markdown,
                    file_path=excluded.file_path
                """,
                (report_id, analysis_id, title, content_markdown, file_path, now),
            )
        return report_id

    def get_report(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE analysis_id = ? ORDER BY created_at DESC LIMIT 1",
                (analysis_id,),
            ).fetchone()
            return dict(row) if row else None

    def record_human_decision(
        self,
        decision_id: str,
        analysis_id: str,
        anomaly_id: Optional[str],
        decision: str,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO human_decisions (decision_id, analysis_id, anomaly_id, decision, reason, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (decision_id, analysis_id, anomaly_id, decision, reason, notes, now),
            )
        return decision_id

    def record_recovery_event(
        self,
        recovery_id: str,
        analysis_id: Optional[str],
        failure_class: str,
        action_taken: str,
        attempt: int,
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO recovery_events (
                    recovery_id, analysis_id, failure_class, action_taken, attempt, result, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (recovery_id, analysis_id, failure_class, action_taken, attempt, result, json.dumps(details or {}), now),
            )
        return recovery_id

    def list_recovery_events(self, analysis_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if analysis_id:
                rows = conn.execute(
                    "SELECT * FROM recovery_events WHERE analysis_id = ? ORDER BY created_at ASC",
                    (analysis_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM recovery_events ORDER BY created_at ASC").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["details"] = json.loads(d["details_json"]) if d.get("details_json") else {}
                results.append(d)
            return results

