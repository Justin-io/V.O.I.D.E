"""Integration Tests for AgentCore Closed-Loop Task Execution."""

import os
import tempfile
import pytest

from voide.agent.adapters.llm_adapter import DeterministicReasoningAdapter, LLMResponse
from voide.agent.runtime.agent_core import AgentCore, AgentStatus, AgentPhase
from voide.agent.storage.state_store import StateStore


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create buggy auth code
        auth_file = os.path.join(tmpdir, "auth.py")
        with open(auth_file, "w") as f:
            f.write("def authenticate(user, password):\n    return False  # Bug\n")

        # Create test script
        test_file = os.path.join(tmpdir, "test_auth.py")
        with open(test_file, "w") as f:
            f.write(
                "import sys, auth\n"
                "if not auth.authenticate('admin', 'secret'):\n"
                "    print('FAIL: Invalid authentication')\n"
                "    sys.exit(1)\n"
                "print('PASS: Authenticated')\n"
                "sys.exit(0)\n"
            )
        yield tmpdir


def test_closed_loop_e2e_task(workspace):
    db_path = os.path.join(workspace, ".voide", "state.db")
    state_store = StateStore(db_path)
    proj_id = state_store.register_project(workspace, "AuthProject")

    # Scripted sequence of actions simulating model reasoning and recovery
    patch_content = (
        "--- auth.py\n"
        "+++ auth.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def authenticate(user, password):\n"
        "-    return False  # Bug\n"
        "+    return True\n"
    )

    plan = [
        # 1. Inspect
        LLMResponse("read_file", {"path": "auth.py"}, hypothesis="Inspect auth implementation"),
        # 2. Run test to observe failure
        LLMResponse("run_tests", {"command": "python3 test_auth.py"}, hypothesis="Confirm failure"),
        # 3. Patch file
        LLMResponse("apply_patch", {"path": "auth.py", "patch": patch_content}, hypothesis="Fix bug"),
        # 4. Re-run tests to confirm fix
        LLMResponse("run_tests", {"command": "python3 test_auth.py"}, hypothesis="Verify fix passes"),
        # 5. Propose completion
        LLMResponse("complete_task", {"summary": "Authentication bug resolved and tests passing"}, is_completed=True),
    ]

    adapter = DeterministicReasoningAdapter(action_plan=plan)
    core = AgentCore(
        workspace_root=workspace,
        state_store=state_store,
        llm_adapter=adapter,
    )

    success_criteria = [
        {"type": "file_contains", "path": "auth.py", "content": "return True"},
        {"type": "command_exit_zero", "command": "python3 test_auth.py"},
    ]

    task_id = core.start_task(
        project_id=proj_id,
        objective="Fix authentication bug and verify test_auth.py passes",
        success_criteria=success_criteria,
    )

    # Drive task through agent loop
    result = core.run_until_completion(task_id, max_steps=10)

    assert result["final_status"] == AgentStatus.COMPLETED
    assert result["total_steps"] == 5

    final_task = state_store.get_task(task_id)
    assert final_task is not None
    assert final_task["status"] == AgentStatus.COMPLETED
    assert final_task["phase"] == AgentPhase.COMPLETED

    # Verify durable checkpoint was created
    latest_ckpt = state_store.get_latest_checkpoint(task_id)
    assert latest_ckpt is not None
    assert latest_ckpt["phase"] == AgentPhase.COMPLETED
    assert latest_ckpt["workspace_snapshot"]["verified"] is True
