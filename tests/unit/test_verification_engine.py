"""Unit Tests for VerificationEngine."""

import os
import tempfile
import pytest
from voide.agent.verification.verification_engine import VerificationEngine


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_verification_file_exists(workspace):
    verifier = VerificationEngine(workspace)
    
    # Non-existent
    r1 = verifier.verify_criterion({"type": "file_exists", "path": "output.txt"})
    assert r1.passed is False

    # Existent
    with open(os.path.join(workspace, "output.txt"), "w") as f:
        f.write("done")
    r2 = verifier.verify_criterion({"type": "file_exists", "path": "output.txt"})
    assert r2.passed is True


def test_verification_file_contains(workspace):
    verifier = VerificationEngine(workspace)
    file_path = os.path.join(workspace, "auth.dart")
    with open(file_path, "w") as f:
        f.write("class AuthNotifier extends StateNotifier {\n  bool isLoggedIn = true;\n}\n")

    r1 = verifier.verify_criterion({"type": "file_contains", "path": "auth.dart", "content": "isLoggedIn = true;"})
    assert r1.passed is True

    r2 = verifier.verify_criterion({"type": "file_contains", "path": "auth.dart", "content": "loginFailed"})
    assert r2.passed is False


def test_verification_command_exit_zero(workspace):
    verifier = VerificationEngine(workspace)
    
    r_pass = verifier.verify_criterion({"type": "command_exit_zero", "command": "true"})
    assert r_pass.passed is True

    r_fail = verifier.verify_criterion({"type": "command_exit_zero", "command": "false"})
    assert r_fail.passed is False


def test_verify_all(workspace):
    verifier = VerificationEngine(workspace)
    with open(os.path.join(workspace, "app.py"), "w") as f:
        f.write("VERSION = '1.0.0'")

    criteria = [
        {"type": "file_exists", "path": "app.py"},
        {"type": "file_contains", "path": "app.py", "content": "1.0.0"},
        {"type": "command_exit_zero", "command": "python3 -c 'import sys; sys.exit(0)'"},
    ]

    report = verifier.verify_all(criteria)
    assert report["all_passed"] is True
    assert report["total"] == 3
    assert report["passed_count"] == 3
