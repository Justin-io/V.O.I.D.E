"""Persistent Linux PTY Manager for V.O.I.D.E.

Provides asynchronous, persistent pseudo-terminal sessions with isolation
between user, agent, and build operations.
"""

from __future__ import annotations
import asyncio
import fcntl
import os
import pty
import signal
import struct
import termios
from typing import Callable, Dict, Optional


class PTYSession:
    """Encapsulates a single long-lived pseudo-terminal process."""

    def __init__(
        self,
        session_id: str,
        shell: str,
        cwd: str,
        env: Optional[Dict[str, str]] = None,
        on_data: Optional[Callable[[str, bytes], None]] = None,
    ) -> None:
        self.session_id: str = session_id
        self.shell: str = shell
        self.cwd: str = cwd
        self.env: Dict[str, str] = env or os.environ.copy()
        self.on_data: Optional[Callable[[str, bytes], None]] = on_data
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.is_alive: bool = False
        self._reader_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Fork process attached to pseudo-terminal."""
        pid, master_fd = pty.fork()
        if pid == 0:
            # Child process
            try:
                os.chdir(self.cwd)
            except Exception:
                pass
            for k, v in self.env.items():
                os.environ[k] = v
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLORTERM"] = "truecolor"
            os.execlp(self.shell, self.shell)
        else:
            # Parent process
            self.pid = pid
            self.master_fd = master_fd
            self.is_alive = True
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def write(self, data: bytes) -> int:
        """Write raw bytes to terminal standard input."""
        if not self.is_alive or self.master_fd is None:
            raise RuntimeError(f"Session {self.session_id} is not alive")
        return os.write(self.master_fd, data)

    def resize(self, cols: int, rows: int) -> None:
        """Resize terminal window dimensions via ioctl."""
        if not self.is_alive or self.master_fd is None:
            return
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def send_signal(self, sig: int) -> None:
        """Send POSIX signal to child process group."""
        if self.pid and self.is_alive:
            try:
                os.kill(self.pid, sig)
            except ProcessLookupError:
                self.is_alive = False

    def close(self) -> None:
        """Terminate session and release file descriptors."""
        self.is_alive = False
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, os.WNOHANG)
            except (ProcessLookupError, ChildProcessError):
                pass
            self.pid = None


class PTYManager:
    """Manages active PTY sessions."""

    def __init__(self) -> None:
        self.sessions: Dict[str, PTYSession] = {}

    def create_session(
        self,
        session_id: str,
        shell: str = "/bin/bash",
        cwd: str = ".",
        env: Optional[Dict[str, str]] = None,
        on_data: Optional[Callable[[str, bytes], None]] = None,
    ) -> PTYSession:
        if session_id in self.sessions:
            raise ValueError(f"Session {session_id} already exists")
        session = PTYSession(session_id, shell, cwd, env, on_data)
        session.start()
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[PTYSession]:
        return self.sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session:
            session.close()
            return True
        return False

    def close_all(self) -> None:
        for session in list(self.sessions.values()):
            session.close()
        self.sessions.clear()
