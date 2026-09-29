"""Policy & Security Engine for V.O.I.D.E.

Implements zero-trust tool execution policies, command risk classification,
workspace sandbox validation, and approval gating.
"""

from __future__ import annotations
import re
from typing import Any, Dict, Optional


class RiskTier:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PolicyDecision:
    def __init__(
        self,
        allowed: bool,
        risk_tier: str,
        requires_approval: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        self.allowed: bool = allowed
        self.risk_tier: str = risk_tier
        self.requires_approval: bool = requires_approval
        self.reason: Optional[str] = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "risk_tier": self.risk_tier,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
        }


class PolicyEngine:
    """Evaluates tool requests against safety rules and risk policies."""

    DANGEROUS_COMMAND_PATTERNS = [
        r"\bsudo\b",
        r"\brm\s+-(?:r|f|rf|fr)\s+[/~]",
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r"\bchmod\s+777\b",
        r"\bcurl\b.*\|\s*(?:bash|sh)\b",
        r"\bwget\b.*\|\s*(?:bash|sh)\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", # Fork bomb
    ]

    TOOL_TIER_MAPPING = {
        # Read-only
        "list_directory": RiskTier.LOW,
        "read_file": RiskTier.LOW,
        "search_files": RiskTier.LOW,
        "git_status": RiskTier.LOW,
        "git_diff": RiskTier.LOW,
        "git_log": RiskTier.LOW,
        "run_tests": RiskTier.LOW,
        "inspect_logs": RiskTier.LOW,
        "browser_read": RiskTier.LOW,
        "get_agent_state": RiskTier.LOW,
        # Mutative Workspace
        "write_file": RiskTier.MEDIUM,
        "apply_patch": RiskTier.MEDIUM,
        "git_commit": RiskTier.MEDIUM,
        "build_project": RiskTier.MEDIUM,
        "browser_navigate": RiskTier.MEDIUM,
        "browser_click": RiskTier.MEDIUM,
        "browser_type": RiskTier.MEDIUM,
        "browser_wait": RiskTier.LOW,
        # Interactive / Shell
        "terminal_start": RiskTier.LOW,
        "terminal_write": RiskTier.MEDIUM,
        "terminal_read": RiskTier.LOW,
        "terminal_signal": RiskTier.LOW,
        # Agent Control
        "create_checkpoint": RiskTier.LOW,
        "request_approval": RiskTier.LOW,
        "complete_task": RiskTier.LOW,
        # Engineering Data Intelligence Tools
        "inspect_dataset": RiskTier.LOW,
        "profile_quality": RiskTier.LOW,
        "prepare_dataset": RiskTier.LOW,
        "build_features": RiskTier.LOW,
        "fit_expected_model": RiskTier.LOW,
        "calculate_contextual_residual": RiskTier.LOW,
        "run_anomaly_detector": RiskTier.LOW,
        "find_anomaly_windows": RiskTier.LOW,
        "compare_equipment": RiskTier.LOW,
        "find_contributors": RiskTier.LOW,
        "validate_claim": RiskTier.LOW,
        "generate_chart": RiskTier.LOW,
        "generate_engineering_visual": RiskTier.LOW,
        "generate_report": RiskTier.LOW,
        "request_human": RiskTier.MEDIUM,
    }

    def __init__(self, workspace_root: str, auto_approve_medium: bool = True) -> None:
        self.workspace_root: str = workspace_root
        self.auto_approve_medium: bool = auto_approve_medium

    def evaluate(self, tool_name: str, arguments: Dict[str, Any]) -> PolicyDecision:
        """Evaluate a tool invocation and assign risk tier and permission."""
        if tool_name not in self.TOOL_TIER_MAPPING:
            return PolicyDecision(
                allowed=False,
                risk_tier=RiskTier.HIGH,
                requires_approval=True,
                reason=f"Unknown tool '{tool_name}' is not registered in security policy",
            )

        base_tier = self.TOOL_TIER_MAPPING[tool_name]

        # Inspect specific tool arguments for high-risk operations
        if tool_name == "terminal_write":
            cmd = arguments.get("command", "") or arguments.get("data", "")
            for pattern in self.DANGEROUS_COMMAND_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return PolicyDecision(
                        allowed=False,
                        risk_tier=RiskTier.HIGH,
                        requires_approval=True,
                        reason=f"High-risk command pattern matched: {pattern}",
                    )

        if tool_name in ("write_file", "apply_patch"):
            path = arguments.get("path", "")
            # Block modifications to sensitive system or git metadata files
            if ".git/" in path or path.startswith(".env") or path.endswith((".key", ".pem", ".pfx")):
                return PolicyDecision(
                    allowed=False,
                    risk_tier=RiskTier.HIGH,
                    requires_approval=True,
                    reason=f"Attempt to write to sensitive or protected path: {path}",
                )

        if base_tier == RiskTier.LOW:
            return PolicyDecision(allowed=True, risk_tier=RiskTier.LOW)

        if base_tier == RiskTier.MEDIUM:
            if self.auto_approve_medium:
                return PolicyDecision(allowed=True, risk_tier=RiskTier.MEDIUM, requires_approval=False)
            else:
                return PolicyDecision(allowed=False, risk_tier=RiskTier.MEDIUM, requires_approval=True, reason="Policy requires approval for medium risk operations")

        return PolicyDecision(
            allowed=False,
            risk_tier=RiskTier.HIGH,
            requires_approval=True,
            reason="High risk tier mandates explicit user authorization",
        )
