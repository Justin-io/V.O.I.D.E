"""Unit Tests for StateStore (Durable SQLite repository)."""

import os
import tempfile
import pytest
from voide.agent.storage.state_store import StateStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_state.db")
        store = StateStore(db_path)
        yield store


def test_project_registration(temp_store):
    pid1 = temp_store.register_project("/tmp/test_repo", "Test Repo", {"lang": "python"})
    assert pid1.startswith("proj-")

    # Re-register same root path updates name and preserves project_id
    pid2 = temp_store.register_project("/tmp/test_repo", "Updated Repo")
    assert pid1 == pid2


def test_task_lifecycle(temp_store):
    pid = temp_store.register_project("/tmp/p1", "Project 1")
    criteria = [{"type": "file_exists", "path": "main.py"}]
    tid = temp_store.create_task(
        project_id=pid,
        objective="Fix authentication bug",
        workspace="/tmp/p1",
        success_criteria=criteria,
        max_iterations=10,
    )
    assert tid.startswith("task-")

    task = temp_store.get_task(tid)
    assert task["objective"] == "Fix authentication bug"
    assert task["status"] == "AGENT_IDLE"
    assert task["phase"] == "PLANNING"
    assert task["iteration"] == 0
    assert len(task["success_criteria"]) == 1

    temp_store.update_task_state(
        tid,
        status="AGENT_EXECUTING",
        phase="INSPECTING",
        current_step=1,
        iteration_increment=1,
        last_action="search_files(auth)",
        last_observation="Found 3 matches",
    )

    updated = temp_store.get_task(tid)
    assert updated["status"] == "AGENT_EXECUTING"
    assert updated["phase"] == "INSPECTING"
    assert updated["iteration"] == 1
    assert updated["current_step"] == 1
    assert "search_files" in updated["last_action"]


def test_tool_call_and_observation(temp_store):
    pid = temp_store.register_project("/tmp/p2", "P2")
    tid = temp_store.create_task(pid, "Test Task", "/tmp/p2")

    req_id = "req-test-101"
    temp_store.record_tool_call(
        request_id=req_id,
        task_id=tid,
        tool="read_file",
        arguments={"path": "auth.py"},
        risk_tier="LOW",
    )

    obs_id = temp_store.complete_tool_call(
        request_id=req_id,
        status="success",
        observation_payload={"lines": 100, "content": "class Auth: pass"},
    )
    assert obs_id.startswith("obs-")


def test_checkpoints(temp_store):
    pid = temp_store.register_project("/tmp/p3", "P3")
    tid = temp_store.create_task(pid, "Checkpoint Task", "/tmp/p3")

    ckpt_id = temp_store.create_checkpoint(
        task_id=tid,
        phase="IMPLEMENTING",
        step=3,
        workspace_snapshot={"files": ["a.py", "b.py"]},
        state_snapshot={"phase": "IMPLEMENTING"},
    )
    assert ckpt_id.startswith("ckpt-")

    latest = temp_store.get_latest_checkpoint(tid)
    assert latest is not None
    assert latest["phase"] == "IMPLEMENTING"
    assert latest["step"] == 3
    assert "a.py" in latest["workspace_snapshot"]["files"]


def test_approvals_flow(temp_store):
    pid = temp_store.register_project("/tmp/p4", "P4")
    tid = temp_store.create_task(pid, "High Risk Task", "/tmp/p4")

    appr_id = temp_store.request_approval(
        task_id=tid,
        risk_tier="HIGH",
        request_data={"command": "rm -rf build/"},
    )
    assert appr_id.startswith("appr-")

    t = temp_store.get_task(tid)
    assert t["status"] == "AGENT_AWAITING_APPROVAL"
    assert t["pending_approval"] == appr_id

    # User approves
    decided = temp_store.decide_approval(appr_id, approved=True)
    assert decided is not None
    assert decided["status"] == "APPROVED"

    t2 = temp_store.get_task(tid)
    assert t2["status"] == "AGENT_EXECUTING"
    assert t2["pending_approval"] is None


def test_event_emission_and_retrieval(temp_store):
    evt_id = temp_store.emit_event(
        event_type="FILE_CHANGED",
        source="fs_watcher",
        data={"file": "auth.py"},
        task_id="task-001",
    )
    assert evt_id.startswith("evt-")

    events = temp_store.get_events("task-001", limit=10)
    assert len(events) >= 1
    assert events[-1]["event_type"] == "FILE_CHANGED"
    assert events[-1]["data"]["file"] == "auth.py"


def test_chat_sessions_flow(temp_store):
    ws = "/tmp/voide_test_workspace"
    session = temp_store.create_chat_session(ws, "Initial Chat")
    assert session["session_id"].startswith("chat-")
    assert session["title"] == "Initial Chat"

    # Add user message
    msg1 = temp_store.add_chat_message(session["session_id"], "user", "build calculator.py")
    assert msg1["message_id"].startswith("msg-")

    # Add tool message
    msg2 = temp_store.add_chat_message(
        session["session_id"],
        "tool",
        "",
        tool_data={"tool": "write_file", "path": "calculator.py", "status": "SUCCESS"}
    )
    assert msg2["tool_data"]["tool"] == "write_file"

    # Add assistant message
    temp_store.add_chat_message(session["session_id"], "assistant", "I have written calculator.py.")

    # Retrieve messages
    msgs = temp_store.get_chat_messages(session["session_id"])
    assert len(msgs) == 3
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "tool"
    assert msgs[2]["role"] == "assistant"

    # List sessions
    sessions = temp_store.list_chat_sessions(ws)
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 3

    # Delete session
    assert temp_store.delete_chat_session(session["session_id"]) is True
    assert len(temp_store.list_chat_sessions(ws)) == 0


def test_chat_sessions_foreign_key_safety(temp_store):
    """Ensures adding a message with uninitialized session never triggers IntegrityError."""
    orphan_session = "unregistered-session-999"
    # Calling add_chat_message on unregistered session must auto-ensure session and succeed
    msg = temp_store.add_chat_message(orphan_session, "user", "Hello V.O.I.D.E.")
    assert msg["message_id"].startswith("msg-")
    assert msg["session_id"] == orphan_session

    msgs = temp_store.get_chat_messages(orphan_session)
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Hello V.O.I.D.E."

    # ensure_chat_session is idempotent
    temp_store.ensure_chat_session(orphan_session, "/tmp/ws")
    msgs2 = temp_store.get_chat_messages(orphan_session)
    assert len(msgs2) == 1


def test_chat_session_conversation_url(temp_store):
    ws = "/tmp/voide_test_workspace"
    session = temp_store.create_chat_session(ws, "Thread Session", conversation_url="https://chatgpt.com/c/test-uuid")
    assert session["conversation_url"] == "https://chatgpt.com/c/test-uuid"

    temp_store.update_session_url(session["session_id"], "https://chatgpt.com/c/updated-uuid")
    fetched = temp_store.get_chat_session(session["session_id"])
    assert fetched is not None
    assert fetched["conversation_url"] == "https://chatgpt.com/c/updated-uuid"



