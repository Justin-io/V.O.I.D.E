"""Unit Tests for PTYManager."""

import os
import time
from voide.native.linux_host.pty_manager import PTYManager


def test_pty_lifecycle():
    manager = PTYManager()
    session_id = "test-session-1"
    
    session = manager.create_session(
        session_id=session_id,
        shell="/bin/sh",
        cwd="/tmp",
    )
    assert session.is_alive is True
    assert session.pid is not None
    assert session.master_fd is not None

    # Write command
    session.write(b"echo 'VOIDE_PTY_READY'\n")
    time.sleep(0.3)

    # Read output
    output = os.read(session.master_fd, 4096).decode("utf-8", errors="ignore")
    assert "VOIDE_PTY_READY" in output

    # Resize terminal
    session.resize(cols=120, rows=40)

    # Teardown
    closed = manager.close_session(session_id)
    assert closed is True
    assert session.is_alive is False
