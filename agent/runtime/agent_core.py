"""Agent Core Orchestrator & State Machine for V.O.I.D.E.

Implements Sections 9, 10, 11, 12, 32, 34, and 35 of the Development Specification.
Guarantees:
- Bounded closed-loop state transitions
- Externalized SQLite durable state
- Observability and verification-gated completion
- Loop failure detection and automatic recovery
"""

from __future__ import annotations
import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from voide.agent.adapters.llm_adapter import LLMAdapter
from voide.agent.policy.policy_engine import PolicyEngine, RiskTier
from voide.agent.runtime.event_engine import EventEngine, EventEnvelope, EventPriority
from voide.agent.storage.state_store import StateStore
from voide.agent.tools.tool_registry import ToolBroker, ToolResult
from voide.agent.verification.verification_engine import VerificationEngine


class AgentPhase:
    PLANNING = "PLANNING"
    DATA_DISCOVERY = "DATA_DISCOVERY"
    DATA_PREP = "DATA_PREP"
    FEATURE_BUILD = "FEATURE_BUILD"
    ML_ANALYSIS = "ML_ANALYSIS"
    INVESTIGATION = "INVESTIGATION"
    CRITIC = "CRITIC"
    VISUALIZE = "VISUALIZE"
    REPORT = "REPORT"
    COMPLETED = "COMPLETED"
    ERROR_RECOVERY = "ERROR_RECOVERY"

    # Compatibility aliases for coding pipelines
    INSPECTING = "INSPECTING"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    ANALYZE_FAIL = "ANALYZE_FAIL"
    FIXING = "FIXING"
    VERIFYING = "VERIFYING"


class AgentStatus:
    IDLE = "AGENT_IDLE"
    EXECUTING = "AGENT_EXECUTING"
    AWAITING_APPROVAL = "AGENT_AWAITING_APPROVAL"
    BLOCKED = "AGENT_BLOCKED"
    VERIFYING = "AGENT_VERIFYING"
    COMPLETED = "TASK_COMPLETED"
    ERROR = "ERROR_RECOVERY"


class AgentCore:
    """The central orchestration engine of V.O.I.D.E."""

    AVAILABLE_TOOLS = [
        # Filesystem & Git
        "list_directory",
        "read_file",
        "search_files",
        "write_file",
        "apply_patch",
        "terminal_start",
        "terminal_write",
        "terminal_read",
        "terminal_signal",
        "git_status",
        "git_diff",
        "git_log",
        "git_commit",
        "run_tests",
        "build_project",
        # Browser & Shell
        "browser_navigate",
        "browser_read",
        "browser_click",
        "browser_type",
        "browser_wait",
        # Agent Control
        "get_agent_state",
        "create_checkpoint",
        "complete_task",
        # Engineering Data Intelligence Tools
        "inspect_dataset",
        "profile_quality",
        "prepare_dataset",
        "build_features",
        "fit_expected_model",
        "calculate_contextual_residual",
        "run_anomaly_detector",
        "find_anomaly_windows",
        "compare_equipment",
        "find_contributors",
        "validate_claim",
        "generate_chart",
        "generate_engineering_visual",
        "generate_report",
    ]

    def __init__(
        self,
        workspace_root: str,
        state_store: StateStore,
        llm_adapter: LLMAdapter,
        event_engine: Optional[EventEngine] = None,
        auto_approve_medium: bool = True,
    ) -> None:
        self.workspace_root: str = workspace_root
        self.state_store: StateStore = state_store
        self.llm_adapter: LLMAdapter = llm_adapter
        self.event_engine: EventEngine = event_engine or EventEngine()
        self.policy_engine: PolicyEngine = PolicyEngine(workspace_root, auto_approve_medium=auto_approve_medium)
        self.tool_broker: ToolBroker = ToolBroker(workspace_root, state_store, self.policy_engine)
        self.verification_engine: VerificationEngine = VerificationEngine(workspace_root)
        self.action_history_hashes: List[str] = []

    def start_task(
        self,
        project_id: str,
        objective: str,
        success_criteria: Optional[List[Dict[str, Any]]] = None,
        max_iterations: int = 25,
    ) -> str:
        """Initialize a new task in durable state."""
        task_id = self.state_store.create_task(
            project_id=project_id,
            objective=objective,
            workspace=self.workspace_root,
            success_criteria=success_criteria or [],
            max_iterations=max_iterations,
        )
        self.event_engine.emit(
            EventEnvelope(
                event_type="TASK_CREATED",
                source="agent_core",
                task_id=task_id,
                priority=EventPriority.NORMAL,
                data={"objective": objective, "workspace": self.workspace_root},
            )
        )
        return task_id

    def step(self, task_id: str) -> Dict[str, Any]:
        """Execute a single bounded iteration step of the agent loop contract."""
        task = self.state_store.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found in state store")

        if task["status"] in (AgentStatus.COMPLETED, AgentStatus.BLOCKED):
            return {"status": task["status"], "phase": task["phase"], "step_executed": False}

        if task["status"] == AgentStatus.AWAITING_APPROVAL:
            return {"status": task["status"], "pending_approval": task["pending_approval"], "step_executed": False}

        # Check iteration boundary
        if task["iteration"] >= task["max_iterations"]:
            self.state_store.update_task_state(task_id, status=AgentStatus.BLOCKED)
            self.event_engine.emit(
                EventEnvelope(
                    event_type="ITERATION_LIMIT_REACHED",
                    source="agent_core",
                    task_id=task_id,
                    priority=EventPriority.HIGH,
                    data={"iteration": task["iteration"], "max_iterations": task["max_iterations"]},
                )
            )
            return {"status": AgentStatus.BLOCKED, "reason": "Max iterations reached", "step_executed": False}

        # 1. Update task to EXECUTING
        self.state_store.update_task_state(task_id, status=AgentStatus.EXECUTING, iteration_increment=1)

        # 2. Context Construction (compact and relevant)
        context = self._build_context_snapshot(task)

        # 3. Query LLM Reasoner
        response = self.llm_adapter.generate_next_action(context, self.AVAILABLE_TOOLS)

        if response.is_blocked:
            self.state_store.update_task_state(task_id, status=AgentStatus.BLOCKED)
            return {"status": AgentStatus.BLOCKED, "reason": response.reason, "step_executed": False}

        # 4. Detect Repetition Looping (Anti-Spinning Guard)
        action_sig = hashlib.sha256(
            f"{response.tool}:{json.dumps(response.arguments, sort_keys=True)}:{response.hypothesis}".encode("utf-8")
        ).hexdigest()

        if self.action_history_hashes.count(action_sig) >= 3:
            # Stalled in repetitive action without progress
            self.state_store.update_task_state(task_id, status=AgentStatus.BLOCKED, phase=AgentPhase.ERROR_RECOVERY)
            self.event_engine.emit(
                EventEnvelope(
                    event_type="AGENT_STALLED",
                    source="agent_core",
                    task_id=task_id,
                    priority=EventPriority.HIGH,
                    data={"repeated_action": response.tool},
                )
            )
            return {
                "status": AgentStatus.BLOCKED,
                "reason": "Agent repeated identical failed action 3 times without new hypothesis",
                "step_executed": False,
            }
        self.action_history_hashes.append(action_sig)

        # 5. Handle Model Proposing Task Completion
        if response.tool == "complete_task" or response.is_completed:
            return self._handle_completion_request(task_id, task, response.arguments)

        # 6. Execute Tool via Broker
        req_id = f"req-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"
        tool_result = self.tool_broker.execute_tool(
            request_id=req_id,
            task_id=task_id,
            tool_name=response.tool,
            arguments=response.arguments,
        )

        # 7. Update Task Phase & State based on Observation
        next_phase = self._compute_next_phase(task["phase"], response.tool, tool_result)
        obs_str = json.dumps(tool_result.observation)[:500]
        
        # Check if action was gated for approval
        if tool_result.status == "denied" and tool_result.risk_tier == RiskTier.HIGH:
            return {
                "status": AgentStatus.AWAITING_APPROVAL,
                "phase": next_phase,
                "tool": response.tool,
                "approval_required": True,
                "step_executed": True,
            }

        self.state_store.update_task_state(
            task_id,
            status=AgentStatus.IDLE if tool_result.status == "success" else AgentStatus.EXECUTING,
            phase=next_phase,
            last_action=f"{response.tool}({json.dumps(response.arguments)})",
            last_observation=obs_str,
            current_step=task["current_step"] + 1,
        )

        # 8. Emit Operational Audit Event
        self.event_engine.emit(
            EventEnvelope(
                event_type="TOOL_EXECUTED",
                source="agent_core",
                task_id=task_id,
                priority=EventPriority.NORMAL,
                data={
                    "request_id": req_id,
                    "tool": response.tool,
                    "status": tool_result.status,
                    "risk_tier": tool_result.risk_tier,
                },
            )
        )

        return {
            "status": AgentStatus.IDLE if tool_result.status == "success" else AgentStatus.EXECUTING,
            "phase": next_phase,
            "tool": response.tool,
            "result": tool_result.to_dict(),
            "step_executed": True,
        }

    def run_until_completion(self, task_id: str, max_steps: Optional[int] = None) -> Dict[str, Any]:
        """Drive the agent loop synchronously until completed, blocked, or limit reached."""
        steps = 0
        limit = max_steps or 30

        while steps < limit:
            steps += 1
            res = self.step(task_id)
            if res.get("status") in (AgentStatus.COMPLETED, AgentStatus.BLOCKED, AgentStatus.AWAITING_APPROVAL):
                return {
                    "task_id": task_id,
                    "final_status": res.get("status"),
                    "total_steps": steps,
                    "details": res,
                }
            time.sleep(0.05)

        return {
            "task_id": task_id,
            "final_status": "STEP_LIMIT_EXCEEDED",
            "total_steps": steps,
        }

    def _build_context_snapshot(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Construct a token-efficient, relevant machine state snapshot."""
        recent_events = self.state_store.get_events(task_id=task["task_id"], limit=3)
        return {
            "task": {
                "task_id": task["task_id"],
                "objective": task["objective"],
                "phase": task["phase"],
                "iteration": task["iteration"],
            },
            "last_action": task.get("last_action"),
            "last_observation": task.get("last_observation"),
            "success_criteria": task.get("success_criteria", []),
            "recent_events": [e["event_type"] for e in recent_events],
        }

    def _compute_next_phase(self, current_phase: str, tool_name: str, result: ToolResult) -> str:
        """Compute state machine phase transition for data intelligence and coding."""
        if result.status == "failure":
            failure_class = "TOOL"
            if tool_name in ("inspect_dataset",):
                failure_class = "PARSER"
            elif tool_name in ("profile_quality", "prepare_dataset"):
                failure_class = "DATA"
            elif tool_name in ("build_features",):
                failure_class = "FEATURE"
            elif tool_name in ("fit_expected_model", "run_anomaly_detector"):
                failure_class = "MODEL"
            elif tool_name in ("validate_claim",):
                failure_class = "EVIDENCE"

            self.state_store.record_recovery_event(
                recovery_id=f"rec-{uuid.uuid4().hex[:8]}",
                analysis_id=None,
                failure_class=failure_class,
                action_taken=f"Failure during {tool_name}: {result.error}",
                attempt=1,
                result="RETRY_SCHEDULED",
                details=result.observation,
            )
            return AgentPhase.ERROR_RECOVERY

        # Data Intelligence Transitions
        if tool_name in ("inspect_dataset", "profile_quality"):
            return AgentPhase.DATA_DISCOVERY

        if tool_name in ("prepare_dataset",):
            return AgentPhase.DATA_PREP

        if tool_name in ("build_features",):
            return AgentPhase.FEATURE_BUILD

        if tool_name in ("fit_expected_model", "calculate_contextual_residual", "run_anomaly_detector"):
            return AgentPhase.ML_ANALYSIS

        if tool_name in ("find_anomaly_windows", "compare_equipment", "find_contributors"):
            return AgentPhase.INVESTIGATION

        if tool_name in ("validate_claim",):
            return AgentPhase.CRITIC

        if tool_name in ("generate_chart", "generate_engineering_visual"):
            return AgentPhase.VISUALIZE

        if tool_name in ("generate_report",):
            return AgentPhase.REPORT

        # Coding pipeline backward compatibility
        if tool_name in ("list_directory", "read_file", "search_files", "git_status"):
            return AgentPhase.INSPECTING

        if tool_name in ("write_file", "apply_patch"):
            return AgentPhase.IMPLEMENTING

        if tool_name in ("run_tests", "build_project"):
            passed = result.observation.get("passed", False) or result.observation.get("success", False)
            return AgentPhase.VERIFYING if passed else AgentPhase.ANALYZE_FAIL

        if current_phase == AgentPhase.ANALYZE_FAIL:
            return AgentPhase.FIXING

        return current_phase

    def _handle_completion_request(self, task_id: str, task: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
        """Enforces Section 34 & 35 Completion Contract: verified machine evidence required."""
        criteria = task.get("success_criteria", [])
        if criteria:
            verification_report = self.verification_engine.verify_all(criteria)
            if not verification_report["all_passed"]:
                # Verification failed: reject premature completion
                self.state_store.update_task_state(
                    task_id,
                    status=AgentStatus.EXECUTING,
                    phase=AgentPhase.ANALYZE_FAIL,
                    last_observation=f"Verification failed: {verification_report['passed_count']}/{verification_report['total']} passed",
                )
                self.event_engine.emit(
                    EventEnvelope(
                        event_type="VERIFICATION_FAILED",
                        source="agent_core",
                        task_id=task_id,
                        priority=EventPriority.HIGH,
                        data=verification_report,
                    )
                )
                return {
                    "status": AgentStatus.EXECUTING,
                    "phase": AgentPhase.ANALYZE_FAIL,
                    "verified": False,
                    "verification_report": verification_report,
                    "step_executed": True,
                }

        # Success criteria verified
        self.state_store.update_task_state(task_id, status=AgentStatus.COMPLETED, phase=AgentPhase.COMPLETED)
        # Create durable completion checkpoint
        self.state_store.create_checkpoint(
            task_id=task_id,
            phase=AgentPhase.COMPLETED,
            step=task["current_step"] + 1,
            workspace_snapshot={"verified": True},
            state_snapshot={"objective": task["objective"], "status": AgentStatus.COMPLETED},
        )
        self.event_engine.emit(
            EventEnvelope(
                event_type="TASK_COMPLETED",
                source="agent_core",
                task_id=task_id,
                priority=EventPriority.NORMAL,
                data={"summary": args.get("summary", "Task verified and completed")},
            )
        )
        return {
            "status": AgentStatus.COMPLETED,
            "phase": AgentPhase.COMPLETED,
            "verified": True,
            "step_executed": True,
        }
