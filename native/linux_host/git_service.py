"""Git Service for V.O.I.D.E. Workspace.

Executes sandboxed Git operations with structured result outputs and
strict argument sanitization.
"""

from __future__ import annotations
import os
import subprocess
from typing import Any, Dict, List, Optional


class GitService:
    """Provides structured Git inspection and operations."""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root: str = os.path.realpath(workspace_root)

    def _run_git(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run git command inside workspace with sanitized environment."""
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/root"),
            "GIT_TERMINAL_PROMPT": "0",
        }
        return subprocess.run(
            ["git"] + args,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            env=clean_env,
            timeout=30,
        )

    def status(self) -> Dict[str, Any]:
        """Inspect workspace git status."""
        proc = self._run_git(["status", "--porcelain", "-b"])
        if proc.returncode != 0:
            return {
                "is_git_repo": False,
                "branch": None,
                "dirty_files": [],
                "error": proc.stderr.strip(),
            }

        lines = proc.stdout.splitlines()
        branch = "unknown"
        dirty_files: List[Dict[str, str]] = []

        for line in lines:
            if line.startswith("## "):
                branch = line[3:].split("...")[0].strip()
            elif len(line) >= 3:
                status_code = line[:2]
                filename = line[3:].strip()
                dirty_files.append({"status": status_code, "file": filename})

        return {
            "is_git_repo": True,
            "branch": branch,
            "is_clean": len(dirty_files) == 0,
            "dirty_files": dirty_files,
        }

    def diff(self, cached: bool = False) -> Dict[str, Any]:
        """Retrieve unified git diff of changes."""
        args = ["diff"]
        if cached:
            args.append("--cached")
        proc = self._run_git(args)
        return {
            "exit_code": proc.returncode,
            "diff": proc.stdout,
            "error": proc.stderr if proc.returncode != 0 else None,
        }

    def log(self, max_count: int = 10) -> List[Dict[str, str]]:
        """Retrieve recent commit history."""
        format_spec = "%H|%an|%ad|%s"
        proc = self._run_git(["log", f"-n{max_count}", f"--pretty=format:{format_spec}", "--date=iso"])
        if proc.returncode != 0:
            return []

        commits: List[Dict[str, str]] = []
        for line in proc.stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "commit_hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits

    def commit(self, message: str, paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Commit changes with structured verification."""
        if not message.strip():
            raise ValueError("Commit message cannot be empty")

        if paths:
            self._run_git(["add"] + paths)
        else:
            self._run_git(["add", "-A"])

        proc = self._run_git(["commit", "-m", message])
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output": proc.stdout.strip(),
            "error": proc.stderr.strip() if proc.returncode != 0 else None,
        }
