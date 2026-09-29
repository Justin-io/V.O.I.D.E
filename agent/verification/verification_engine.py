"""Verification Engine for V.O.I.D.E.

Enforces Section 34 and 35 completion contracts.
Never infers success from model intent; requires observable machine evidence.
"""

from __future__ import annotations
import os
import subprocess
from typing import Any, Dict, List, Optional


class VerificationResult:
    def __init__(
        self,
        passed: bool,
        criterion_type: str,
        evidence: Dict[str, Any],
        error_message: Optional[str] = None,
    ) -> None:
        self.passed: bool = passed
        self.criterion_type: str = criterion_type
        self.evidence: Dict[str, Any] = evidence
        self.error_message: Optional[str] = error_message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "criterion_type": self.criterion_type,
            "evidence": self.evidence,
            "error_message": self.error_message,
        }


class VerificationEngine:
    """Authoritative verifier of machine state against success criteria."""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root: str = os.path.realpath(workspace_root)

    def verify_criterion(self, criterion: Dict[str, Any]) -> VerificationResult:
        """Evaluate a single success criterion."""
        c_type = criterion.get("type", "").lower()

        if c_type == "file_exists":
            rel_path = criterion.get("path", "")
            full_path = os.path.join(self.workspace_root, rel_path)
            exists = os.path.exists(full_path)
            return VerificationResult(
                passed=exists,
                criterion_type="file_exists",
                evidence={"path": rel_path, "exists": exists},
                error_message=None if exists else f"File does not exist: {rel_path}",
            )

        elif c_type == "file_contains":
            rel_path = criterion.get("path", "")
            expected_content = criterion.get("content", "")
            full_path = os.path.join(self.workspace_root, rel_path)
            if not os.path.isfile(full_path):
                return VerificationResult(
                    passed=False,
                    criterion_type="file_contains",
                    evidence={"path": rel_path, "exists": False},
                    error_message=f"Target file not found: {rel_path}",
                )
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            matched = expected_content in content
            return VerificationResult(
                passed=matched,
                criterion_type="file_contains",
                evidence={"path": rel_path, "matched": matched},
                error_message=None if matched else "File does not contain expected snippet",
            )

        elif c_type in ("command_exit_zero", "unit_test", "build"):
            cmd = criterion.get("command")
            if not cmd:
                return VerificationResult(
                    passed=False,
                    criterion_type=c_type,
                    evidence={},
                    error_message="Missing command in criterion",
                )
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=criterion.get("timeout_seconds", 60),
            )
            passed = proc.returncode == 0
            return VerificationResult(
                passed=passed,
                criterion_type=c_type,
                evidence={
                    "command": cmd,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[-1000:],
                    "stderr": proc.stderr[-1000:],
                },
                error_message=None if passed else f"Command '{cmd}' failed with exit code {proc.returncode}",
            )

        elif c_type == "browser_element_exists":
            # Evaluates browser assertion evidence
            found = bool(criterion.get("element_found", False))
            return VerificationResult(
                passed=found,
                criterion_type="browser_element_exists",
                evidence=criterion,
                error_message=None if found else "Required browser element missing from verified DOM snapshot",
            )

        return VerificationResult(
            passed=False,
            criterion_type=c_type,
            evidence=criterion,
            error_message=f"Unsupported verification type: {c_type}",
        )

    def verify_all(self, criteria: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run all success criteria and assemble authoritative verification report."""
        if not criteria:
            return {
                "all_passed": True,
                "total": 0,
                "passed_count": 0,
                "results": [],
            }

        results: List[VerificationResult] = []
        all_passed = True

        for c in criteria:
            res = self.verify_criterion(c)
            results.append(res)
            if not res.passed:
                all_passed = False

        return {
            "all_passed": all_passed,
            "total": len(criteria),
            "passed_count": sum(1 for r in results if r.passed),
            "results": [r.to_dict() for r in results],
        }
