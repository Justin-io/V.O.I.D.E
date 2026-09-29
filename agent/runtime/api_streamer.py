"""V.O.I.D.E. API-Key Streaming Reasoning Engine & Autonomous Multi-Turn ReAct Loop.

Replaces browser-based CDP ChatGPT scraping with a clean, high-performance,
zero-dependency HTTP/SSE streaming client supporting:
- OpenAI API (gpt-4o, gpt-4-turbo, o1, o3-mini)
- Local LLMs via Ollama (http://localhost:11434/v1, zero API key required)
- OpenRouter, vLLM, DeepSeek, LocalAI, and OpenAI-compatible gateways
- Real-time token streaming with Server-Sent Events (SSE)
- Autonomous multi-turn ReAct loop with local tool execution
- Background process tracking subsystem (bash_start, check_process, wait_process)
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

try:
    from voide.agent.runtime.prompt_engine import (
        CORE_IDENTITY_PROMPT,
        build_initial_prompt,
        build_observation_prompt,
        build_followup_prompt,
        load_live_engineering_context,
    )
except ImportError:
    from agent.runtime.prompt_engine import (  # type: ignore[no-redef]
        CORE_IDENTITY_PROMPT,
        build_initial_prompt,
        build_observation_prompt,
        build_followup_prompt,
        load_live_engineering_context,
    )

try:
    from voide.agent.storage.state_store import StateStore
except ImportError:
    from agent.storage.state_store import StateStore  # type: ignore[no-redef]

logger = logging.getLogger("voide.api_streamer")


@dataclass
class LLMConfig:
    """Configuration for LLM reasoning provider."""
    provider: str = "openai"  # openai, ollama, openrouter, custom
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    temperature: float = 0.2
    timeout: float = 60.0
    max_turns: int = 10

    @classmethod
    def from_env(cls, workspace_root: Optional[str] = None) -> LLMConfig:
        """Instantiate LLM configuration from environment and optional .env file."""
        # Try loading .env if available
        if workspace_root:
            env_file = os.path.join(workspace_root, ".env")
            if os.path.isfile(env_file):
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k = k.strip()
                                v = v.strip().strip("'\"")
                                if k not in os.environ:
                                    os.environ[k] = v
                except Exception:
                    pass

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
        model = os.environ.get("OPENAI_MODEL", "").strip()
        provider = os.environ.get("VOIDE_LLM_PROVIDER", "").strip().lower()

        if not base_url:
            base_url = "https://api.openai.com/v1"

        if not model:
            if "ollama" in base_url or "11434" in base_url:
                model = "llama3.1"
                provider = provider or "ollama"
            elif "openrouter" in base_url:
                model = "openai/gpt-4o"
                provider = provider or "openrouter"
            else:
                model = "gpt-4o"
                provider = provider or "openai"

        if not provider:
            if "11434" in base_url or "localhost" in base_url:
                provider = "ollama"
            elif "openrouter" in base_url:
                provider = "openrouter"
            else:
                provider = "openai"

        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        masked_key = ""
        if self.api_key:
            if mask_secrets and len(self.api_key) > 8:
                masked_key = f"{self.api_key[:4]}...{self.api_key[-4:]}"
            elif mask_secrets:
                masked_key = "***"
            else:
                masked_key = self.api_key

        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_configured": bool(self.api_key),
            "api_key_masked": masked_key,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "max_turns": self.max_turns,
        }

    def update(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key.strip()
            os.environ["OPENAI_API_KEY"] = self.api_key
        if base_url is not None:
            self.base_url = base_url.strip()
            os.environ["OPENAI_BASE_URL"] = self.base_url
        if model is not None:
            self.model = model.strip()
            os.environ["OPENAI_MODEL"] = self.model
        if provider is not None:
            self.provider = provider.strip().lower()
            os.environ["VOIDE_LLM_PROVIDER"] = self.provider


DANGEROUS_COMMAND_PATTERNS: List[str] = [
    r"\bsudo\b",
    r"\brm\s+-(?:r|f|rf|fr)\s+[/~]",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bchmod\s+777\b",
    r"\bcurl\b.*\|\s*(?:bash|sh)\b",
    r"\bwget\b.*\|\s*(?:bash|sh)\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # Fork bomb
    r"\bbash\s+-i\s+>&",                           # Interactive bash reverse shell
    r"\bnc\s+.*-e\b",                              # Netcat reverse shell
    r"\bpython.*socket.*connect\b",                # Python reverse shell
    r"(?:cat|grep|head|tail|more|less|strings)\s+.*\.env\b", # Secret credential dump
    r"curl\s+.*(?:-d|--data).*@.*\.env",          # Credential exfiltration
]


def check_command_safety(command: str) -> Optional[str]:
    """Check command against dangerous patterns, returning matched pattern if unsafe."""
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return pattern
    return None


class ProcessManager:
    """Manages background terminal processes, downloads, builds, and progress tracking."""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.realpath(workspace_root)
        self._processes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start_process(self, command: str, process_id: Optional[str] = None) -> Dict[str, Any]:
        pid_key = process_id or f"proc_{int(time.time() * 1000)}"
        unsafe = check_command_safety(command)
        if unsafe:
            return {
                "tool": "bash_start",
                "process_id": pid_key,
                "status": "DENIED",
                "error": f"High-risk command blocked by security policy: {unsafe}",
            }
        with self._lock:
            if pid_key in self._processes and self._processes[pid_key]["proc"].poll() is None:
                return {
                    "tool": "bash_start",
                    "process_id": pid_key,
                    "status": "ALREADY_RUNNING",
                    "message": f"Process '{pid_key}' is already running.",
                }

            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=self.workspace_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            output_buffer: List[str] = []

            def _reader() -> None:
                try:
                    if proc.stdout:
                        for line in iter(proc.stdout.readline, ""):
                            if not line:
                                break
                            output_buffer.append(line)
                            if len(output_buffer) > 2000:
                                del output_buffer[:500]
                except Exception:
                    pass

            t = threading.Thread(target=_reader, daemon=True)
            t.start()

            self._processes[pid_key] = {
                "process_id": pid_key,
                "command": command,
                "proc": proc,
                "thread": t,
                "buffer": output_buffer,
                "start_time": time.time(),
            }

            return {
                "tool": "bash_start",
                "process_id": pid_key,
                "command": command,
                "status": "STARTED",
                "message": f"Started background process '{pid_key}': {command}",
            }

    def check_process(self, process_id: str, tail_lines: int = 25) -> Dict[str, Any]:
        with self._lock:
            info = self._processes.get(process_id)
            if not info:
                return {
                    "tool": "check_process",
                    "process_id": process_id,
                    "status": "NOT_FOUND",
                    "error": f"No background process found with id '{process_id}'",
                }

            proc: subprocess.Popen = info["proc"]
            code = proc.poll()
            is_running = (code is None)
            status = "RUNNING" if is_running else ("COMPLETED" if code == 0 else "FAILED")
            elapsed = round(time.time() - info["start_time"], 2)

            recent_lines = info["buffer"][-tail_lines:] if info["buffer"] else []
            recent_output = "".join(recent_lines).strip()

            return {
                "tool": "check_process",
                "process_id": process_id,
                "command": info["command"],
                "status": status,
                "exit_code": code,
                "elapsed_seconds": elapsed,
                "recent_output": recent_output,
                "is_running": is_running,
            }

    def wait_process(self, process_id: str, timeout_seconds: float = 30.0) -> Dict[str, Any]:
        with self._lock:
            info = self._processes.get(process_id)
            if not info:
                return {
                    "tool": "wait_process",
                    "process_id": process_id,
                    "status": "NOT_FOUND",
                    "error": f"No background process found with id '{process_id}'",
                }
            proc: subprocess.Popen = info["proc"]

        try:
            proc.wait(timeout=timeout_seconds)
            return self.check_process(process_id)
        except subprocess.TimeoutExpired:
            res = self.check_process(process_id)
            res["status"] = "TIMEOUT_STILL_RUNNING"
            return res

    def kill_process(self, process_id: str) -> Dict[str, Any]:
        with self._lock:
            info = self._processes.get(process_id)
            if not info:
                return {"tool": "kill_process", "process_id": process_id, "status": "NOT_FOUND"}
            proc: subprocess.Popen = info["proc"]
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
            return {"tool": "kill_process", "process_id": process_id, "status": "TERMINATED"}


class APIStreamer:
    """Autonomous Vibe Coding Engine driven by API-Key streaming and multi-turn ReAct loop."""

    def __init__(
        self,
        workspace_root: str,
        state_store: Optional[StateStore] = None,
        llm_config: Optional[LLMConfig] = None,
        cdp_controller: Any = None,
    ) -> None:
        self.workspace_root = os.path.realpath(workspace_root)
        self.state_store = state_store or StateStore(
            os.path.join(self.workspace_root, ".voide", "state.db")
        )
        self.llm_config = llm_config or LLMConfig.from_env(self.workspace_root)
        self.process_manager = ProcessManager(self.workspace_root)
        self.cdp = cdp_controller  # Kept for backward compatibility if passed

    def update_config(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> LLMConfig:
        """Update runtime LLM settings."""
        self.llm_config.update(api_key=api_key, base_url=base_url, model=model, provider=provider)
        return self.llm_config

    async def new_chat(self) -> bool:
        """Reset conversation session state."""
        return True

    def _gather_workspace_context(self, user_query: str = "") -> Dict[str, Any]:
        """Inspect directory structure, manifests, tech stack, and relevant source snippets."""
        tree: List[str] = []
        manifests: List[str] = []
        stack: Set[str] = set()
        attached_files: Dict[str, str] = {}

        ignore_dirs = {
            ".git", ".voide", "build", "node_modules", ".dart_tool",
            "__pycache__", ".pytest_cache", ".ruff_cache", "target", "venv", ".venv",
        }

        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            rel_dir = os.path.relpath(root, self.workspace_root)

            for f in sorted(files):
                if f.startswith(".") and f != ".env.example":
                    continue
                rel_file = f if rel_dir == "." else os.path.join(rel_dir, f)
                tree.append(rel_file)

                # Identify manifests & tech stacks
                if f in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile"):
                    manifests.append(rel_file)
                    stack.add("Python")
                elif f == "pubspec.yaml":
                    manifests.append(rel_file)
                    stack.add("Flutter/Dart")
                elif f in ("package.json", "tsconfig.json"):
                    manifests.append(rel_file)
                    stack.add("JavaScript/TypeScript")
                elif f in ("CMakeLists.txt", "Makefile"):
                    manifests.append(rel_file)
                    stack.add("C/C++")
                elif f == "Cargo.toml":
                    manifests.append(rel_file)
                    stack.add("Rust")
                elif f.endswith(".py"):
                    stack.add("Python")
                elif f.endswith(".dart"):
                    stack.add("Flutter/Dart")

        # Proactively load matching files if query targets them
        if user_query:
            target_candidates: List[str] = []
            for m in re.finditer(r'([a-zA-Z0-9_\-./]+\.(?:py|dart|yaml|toml|json|sh|md|txt|html|css|js|ts|c|cpp|h))', user_query):
                cand = m.group(1).lstrip("./")
                full_p = os.path.join(self.workspace_root, cand)
                if os.path.isfile(full_p) and cand not in target_candidates:
                    target_candidates.append(cand)

            for cand in target_candidates[:6]:
                full_p = os.path.join(self.workspace_root, cand)
                try:
                    with open(full_p, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    snippet = "".join(lines[:120])
                    if len(lines) > 120:
                        snippet += f"\n... [{len(lines) - 120} lines truncated for brevity] ..."
                    attached_files[cand] = snippet
                except Exception:
                    pass

        engineering_context = load_live_engineering_context(self.workspace_root)

        return {
            "tree": tree[:40],
            "manifests": manifests,
            "tech_stack": list(stack) if stack else ["Generic/Linux"],
            "attached_files": attached_files,
            "engineering_context": engineering_context,
        }

    def format_prompt(self, user_query: str, is_followup: bool = False) -> str:
        """Wrap user query with V.O.I.D.E. engineering protocol and live context."""
        clean = user_query.strip()
        ctx = self._gather_workspace_context(clean)
        eng_ctx = ctx.get("engineering_context") or {}
        analysis = eng_ctx.get("analysis")
        raw_ds = eng_ctx.get("raw_dataset")

        if clean.upper() in ["HI", "HELLO", "HEY"]:
            greeting_parts = [
                "[V.O.I.D.E. SYSTEM PROTOCOL]",
                "You are V.O.I.D.E., Senior Systems Architect & Engineering Data Intelligence specialist for the YUKTHI 2026 National Hackathon: Intelligent Energy & Equipment Monitoring.",
            ]
            if analysis:
                ds_name = analysis.get("dataset_name", "operational_telemetry.csv")
                rows = analysis.get("row_count", 0)
                cols = analysis.get("column_count", 0)
                entities = analysis.get("entities") or []
                ent_str = ", ".join(f"`{e}`" for e in entities) if entities else "monitored equipment"
                r2 = analysis.get("model_r2")
                r2_str = f" ($R^2 = {r2:.4f}$)" if r2 is not None else ""
                anoms = eng_ctx.get("anomalies") or []
                anom_count = len(anoms) if anoms else analysis.get("anomalies_detected", 0)
                excess_kwh = sum(a.get("residual_score", 0.0) for a in anoms if a.get("residual_score", 0.0) > 0.0)
                greeting_parts.append(f"Active Grounded Dataset: `{ds_name}` ({rows:,} observations, {cols} channels, units: {ent_str}).")
                greeting_parts.append(f"Multivariate Contextual Baseline: Fitted{r2_str}, ASHRAE Guideline 14 compliant.")
                greeting_parts.append(f"Persistent Anomalies: {anom_count} episodes detected, {excess_kwh:.1f} kWh cumulative excess energy lift.")
            elif raw_ds:
                greeting_parts.append(f"Loaded Raw Telemetry: `{raw_ds.get('name')}` ({raw_ds.get('row_count', 0):,} rows, {raw_ds.get('column_count', 0)} channels).")
                greeting_parts.append("Status: Raw telemetry file present. Contextual baseline models and anomaly detection pipeline pending execution.")
            else:
                greeting_parts.append("Status: Standby. Ready for code generation, workspace manipulation, and data analysis.")

            greeting_parts.append("Briefly greet the engineer, summarize current status, and ask what to execute.\n")
            greeting_parts.append(f"User: {clean}")
            return "\n".join(greeting_parts)

        if is_followup:
            return build_followup_prompt(
                user_query=clean,
                attached_files=ctx.get("attached_files"),
                engineering_context=eng_ctx,
            )

        return build_initial_prompt(
            user_query=clean,
            manifests=ctx["manifests"],
            tech_stack=ctx["tech_stack"],
            file_tree=ctx["tree"],
            attached_files=ctx.get("attached_files"),
            engineering_context=eng_ctx,
        )

    @staticmethod
    def clean_chat_response(text: str) -> str:
        """Strip raw JSON tool call blocks and protocol markers for clean presentation."""
        cleaned = text
        cleaned = re.sub(r'```(?:tool_call|json)?\s*\{[\s\S]*?"tool"[\s\S]*?\}\s*```', '', cleaned)
        cleaned = re.sub(r'\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"args"\s*:\s*\{[\s\S]*?\}\s*\}', '', cleaned)
        cleaned = re.sub(r'\[V\.O\.I\.D\.E\.[^\]]*\]', '', cleaned)
        cleaned = re.sub(r'\[TRIGGER:[^\]]*\]', '', cleaned)
        cleaned = re.sub(r'\[TOOL OBSERVATIONS[^\]]*\][\s\S]*?(?=\n\n|$)', '', cleaned)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return cleaned

    def _safe_resolve(self, relative_path: str) -> str:
        """Ensure file path stays strictly within the workspace root and blocks protected secrets."""
        joined = os.path.join(self.workspace_root, relative_path)
        resolved = os.path.realpath(joined)
        common = os.path.commonpath([self.workspace_root, resolved])
        if common != self.workspace_root:
            raise ValueError(f"Path traversal detected: '{relative_path}' escapes workspace '{self.workspace_root}'")

        base_name = os.path.basename(resolved)
        rel_from_ws = os.path.relpath(resolved, self.workspace_root)
        parts = rel_from_ws.split(os.sep)
        if (
            any(p.startswith(".git") or p.startswith(".ssh") for p in parts)
            or (base_name.startswith(".env") and not base_name.endswith(".example"))
            or base_name.endswith((".key", ".pem", ".pfx", ".pkcs12", ".id_rsa", ".id_ed25519"))
            or base_name in ("credentials.json", "token.json", "id_rsa", "id_ed25519")
        ):
            raise PermissionError(f"Access to protected credential or sensitive path is denied: '{relative_path}'")
        return resolved

    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute local filesystem, terminal, or data intelligence tools."""
        try:
            if tool_name == "write_file":
                rel_path = args.get("path", "output.py")
                content = args.get("content", "")
                full_path = self._safe_resolve(rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return {
                    "tool": "write_file",
                    "path": rel_path,
                    "status": "SUCCESS",
                    "bytes_written": len(content),
                    "message": f"Created workspace file: {rel_path} ({len(content)} bytes)",
                }

            elif tool_name == "patch_file":
                rel_path = args.get("path", "")
                target = args.get("target", "")
                replacement = args.get("replacement", "")
                full_path = self._safe_resolve(rel_path)
                if not os.path.isfile(full_path):
                    return {"tool": "patch_file", "path": rel_path, "status": "ERROR", "error": "File not found"}
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if target not in content:
                    return {
                        "tool": "patch_file",
                        "path": rel_path,
                        "status": "ERROR",
                        "error": "Target string not found in file content",
                    }
                new_content = content.replace(target, replacement, 1)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                return {
                    "tool": "patch_file",
                    "path": rel_path,
                    "status": "SUCCESS",
                    "message": f"Successfully patched {rel_path}",
                }

            elif tool_name == "read_file":
                rel_path = args.get("path", "")
                full_path = self._safe_resolve(rel_path)
                if not os.path.isfile(full_path):
                    return {"tool": "read_file", "path": rel_path, "status": "ERROR", "error": "File not found"}
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                start_line = max(1, int(args.get("start_line", 1)))
                end_line = min(len(lines), int(args.get("end_line", start_line + 200)))
                sliced = lines[start_line - 1 : end_line]
                content = "".join(sliced)

                return {
                    "tool": "read_file",
                    "path": rel_path,
                    "status": "SUCCESS",
                    "start_line": start_line,
                    "end_line": end_line,
                    "total_lines": len(lines),
                    "content": content,
                }

            elif tool_name == "list_directory":
                rel_path = args.get("path", "")
                full_path = self._safe_resolve(rel_path)
                if not os.path.isdir(full_path):
                    return {"tool": "list_directory", "path": rel_path, "status": "ERROR", "error": "Directory not found"}
                entries = []
                for item in os.scandir(full_path):
                    if item.name.startswith(".") or item.name in ("__pycache__", "build", "node_modules", "target", ".dart_tool"):
                        continue
                    entries.append({"name": item.name, "is_dir": item.is_dir()})
                return {
                    "tool": "list_directory",
                    "path": rel_path,
                    "status": "SUCCESS",
                    "entries": entries,
                }

            elif tool_name == "search_files":
                query = args.get("query", "")
                sub_path = args.get("path", "")
                search_dir = self._safe_resolve(sub_path) if sub_path else self.workspace_root
                matches = []
                regex = re.compile(query, re.IGNORECASE)
                for root, dirs, files in os.walk(search_dir):
                    dirs[:] = [
                        d for d in dirs
                        if not d.startswith(".") and d not in ("__pycache__", "build", "node_modules", "target")
                    ]
                    for f in files:
                        if f.startswith("."):
                            continue
                        f_path = os.path.join(root, f)
                        try:
                            with open(f_path, "r", encoding="utf-8", errors="ignore") as fl:
                                for line_num, line in enumerate(fl, 1):
                                    if regex.search(line):
                                        rel_f = os.path.relpath(f_path, self.workspace_root)
                                        matches.append({"file": rel_f, "line": line_num, "content": line.strip()[:150]})
                                        if len(matches) >= 30:
                                            break
                        except Exception:
                            continue
                        if len(matches) >= 30:
                            break
                    if len(matches) >= 30:
                        break
                return {
                    "tool": "search_files",
                    "query": query,
                    "status": "SUCCESS",
                    "matches": matches,
                    "count": len(matches),
                }

            elif tool_name == "bash":
                cmd = args.get("command", "")
                unsafe = check_command_safety(cmd)
                if unsafe:
                    return {
                        "tool": "bash",
                        "command": cmd,
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": f"Command rejected: matches dangerous pattern '{unsafe}'",
                        "status": "DENIED",
                    }
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return {
                    "tool": "bash",
                    "command": cmd,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout[:2000],
                    "stderr": proc.stderr[:2000],
                    "status": "SUCCESS" if proc.returncode == 0 else "ERROR",
                }

            elif tool_name == "bash_start":
                cmd = args.get("command", "")
                unsafe = check_command_safety(cmd)
                if unsafe:
                    return {
                        "tool": "bash_start",
                        "command": cmd,
                        "status": "DENIED",
                        "error": f"Command rejected: matches dangerous pattern '{unsafe}'",
                    }
                proc_id = args.get("process_id")
                return self.process_manager.start_process(cmd, proc_id)

            elif tool_name == "check_process":
                proc_id = args.get("process_id", "")
                tail = int(args.get("tail_lines", 25))
                return self.process_manager.check_process(proc_id, tail_lines=tail)

            elif tool_name == "wait_process":
                proc_id = args.get("process_id", "")
                timeout = float(args.get("timeout_seconds", 30.0))
                return self.process_manager.wait_process(proc_id, timeout_seconds=timeout)

            elif tool_name == "kill_process":
                proc_id = args.get("process_id", "")
                return self.process_manager.kill_process(proc_id)

            # Domain engineering tools delegation
            elif tool_name in ("dataset_ingest", "inspect_dataset"):
                p = args.get("path", "datasets/development_dataset.csv")
                full_p = self._safe_resolve(p)
                try:
                    from voide.agent.data_engine.ingest import DatasetIngestEngine
                except ImportError:
                    from agent.data_engine.ingest import DatasetIngestEngine  # type: ignore[no-redef]
                info = DatasetIngestEngine().ingest(full_p)
                return {"tool": tool_name, "status": "SUCCESS", "dataset_id": info.get("dataset_id"), "row_count": info.get("row_count")}

            return {"tool": tool_name, "status": "SKIPPED", "message": f"Unsupported tool: {tool_name}"}
        except Exception as e:
            return {"tool": tool_name, "status": "ERROR", "error": str(e)}

    def parse_and_execute_tools(self, response_text: str, user_query: str) -> List[Dict[str, Any]]:
        """Parse structured tool calls or embedded code files and execute them locally."""
        executed: List[Dict[str, Any]] = []

        # 1. Explicit tool_call / json code blocks
        seen_calls = set()
        for block in re.findall(r'```(?:tool_call|json)?\s*\n?([\s\S]*?)```', response_text):
            block = block.strip()
            if block.startswith("{") and "tool" in block:
                try:
                    call_data = json.loads(block, strict=False)
                    tool_name = call_data.get("tool")
                    args = call_data.get("args", {})
                    call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                    if tool_name and call_key not in seen_calls:
                        seen_calls.add(call_key)
                        result = self._execute_tool(tool_name, args)
                        executed.append(result)
                except Exception:
                    pass

        # Also search for standalone JSON objects outside fences if none found
        if not executed:
            for match in re.finditer(r'\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"args"\s*:\s*\{', response_text):
                start = match.start()
                brace_count = 0
                end = -1
                for i in range(start, len(response_text)):
                    if response_text[i] == '{':
                        brace_count += 1
                    elif response_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break
                if end != -1:
                    raw_json = response_text[start:end]
                    try:
                        call_data = json.loads(raw_json, strict=False)
                        tool_name = call_data.get("tool")
                        args = call_data.get("args", {})
                        call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                        if tool_name and call_key not in seen_calls:
                            seen_calls.add(call_key)
                            result = self._execute_tool(tool_name, args)
                            executed.append(result)
                    except Exception:
                        pass

        # 2. Markdown python code block fallback for code generation
        if not executed:
            write_intent = bool(re.search(
                r'\b(create|write|implement|build|generate|save|overwrite|make|update|fix|code|calculator|matrix|patch)\b',
                user_query,
                re.IGNORECASE,
            ))
            filename = self._infer_filename(user_query)
            code_body = ""

            py_match = re.search(r'```(?:python|py)?\s*\n(.*?)```', response_text, re.DOTALL)
            if py_match:
                code_body = py_match.group(1).strip()
            else:
                code_header_match = re.search(r'#\s*([a-zA-Z0-9_\-]+\.py)\s*\n(.*)', response_text, re.DOTALL)
                if code_header_match:
                    filename = code_header_match.group(1)
                    code_body = code_header_match.group(2).strip()

            if write_intent and code_body and len(code_body) > 20:
                code_body = re.sub(r'```\s*$', '', code_body).strip()
                res = self._execute_tool("write_file", {"path": filename, "content": code_body})
                executed.append(res)

        return executed

    def _infer_filename(self, query: str) -> str:
        """Infer target filename from user prompt."""
        m = re.search(r'\b([a-zA-Z0-9_\-]+\.(?:py|dart|sh|json|yaml|sql|md))\b', query)
        if m:
            return m.group(1)
        if "calculator" in query.lower():
            return "calculator.py"
        return "output.py"

    async def _stream_turn_sse(
        self,
        messages: List[Dict[str, str]],
        on_token: Optional[Callable[[str, str, bool], Awaitable[None]]] = None,
    ) -> str:
        """Stream a single LLM response turn over standard HTTP/SSE chat completions."""
        base_url = self.llm_config.base_url.rstrip("/")
        endpoint = f"{base_url}/chat/completions"
        api_key = self.llm_config.api_key

        is_local = any(h in base_url for h in ("localhost", "127.0.0.1", "0.0.0.0", "11434"))

        # Guide user if no API key is set and endpoint is not local
        if not api_key and not is_local:
            help_msg = (
                "### V.O.I.D.E. AI Engine Standby: API Key Required\n\n"
                "To enable real-time streaming and autonomous reasoning, configure an API key or local model:\n\n"
                "1. **OpenAI / OpenRouter / Anthropic Proxy**:\n"
                "   - Set your key: `export OPENAI_API_KEY=\"sk-...\"` in `.env` or your terminal.\n"
                "   - Or switch to the **GATEWAY** tab in the left rail to enter your key live.\n\n"
                "2. **Zero-Cost Local AI with Ollama**:\n"
                "   - Run locally: `ollama run llama3.1`\n"
                "   - Set base URL: `export OPENAI_BASE_URL=\"http://localhost:11434/v1\"` (no key required!).\n"
            )
            if on_token:
                await on_token(help_msg, help_msg, False)
            return help_msg

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": self.llm_config.model,
            "messages": messages,
            "stream": True,
            "temperature": self.llm_config.temperature,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")

        accumulated = ""
        loop = asyncio.get_running_loop()
        token_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        error_holder: List[Exception] = []

        def _sync_worker() -> None:
            try:
                with urllib.request.urlopen(req, timeout=self.llm_config.timeout) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    loop.call_soon_threadsafe(token_queue.put_nowait, delta)
                            except Exception:
                                pass
            except Exception as ex:
                error_holder.append(ex)
            finally:
                loop.call_soon_threadsafe(token_queue.put_nowait, None)

        worker_thread = threading.Thread(target=_sync_worker, daemon=True)
        worker_thread.start()

        while True:
            delta = await token_queue.get()
            if delta is None:
                break
            accumulated += delta
            if on_token:
                await on_token(delta, accumulated, False)

        if error_holder and not accumulated:
            err = error_holder[0]
            logger.error("LLM API streaming failure: %s", err)
            fallback = f"LLM Connection Error ({self.llm_config.provider}): {err}. Verify your API key or endpoint URL ({self.llm_config.base_url})."
            if on_token:
                await on_token(f"\n\n[{fallback}]", fallback, False)
            return fallback

        return accumulated

    async def stream_chat(
        self,
        user_query: str,
        on_token: Optional[Callable[[str, str, bool], Awaitable[None]]] = None,
        on_tool_executed: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        is_followup: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute multi-turn autonomous ReAct loop with live token streaming and tool dispatch."""
        active_prompt = self.format_prompt(user_query, is_followup=is_followup)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": CORE_IDENTITY_PROMPT},
        ]

        # Load session history if available
        if session_id and self.state_store:
            history = self.state_store.get_chat_messages(session_id)
            for m in history[-6:]:
                role = m.get("role", "user")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": m.get("content", "")})

        messages.append({"role": "user", "content": active_prompt})

        all_executed_tools: List[Dict[str, Any]] = []
        accumulated_responses: List[str] = []
        max_turns = self.llm_config.max_turns
        current_turn = 0

        for current_turn in range(1, max_turns + 1):
            turn_text = await self._stream_turn_sse(messages, on_token=on_token)
            if not turn_text:
                break

            executed_tools = self.parse_and_execute_tools(turn_text, user_query)
            all_executed_tools.extend(executed_tools)

            if on_tool_executed:
                for t in executed_tools:
                    try:
                        await on_tool_executed(t)
                    except Exception:
                        pass

            accumulated_responses.append(turn_text)

            # If no tools called, we have completed the response
            if not executed_tools:
                break

            # Build observation prompt and feed back into the ReAct conversation
            obs_prompt = build_observation_prompt(executed_tools, current_turn, max_turns)
            messages.append({"role": "assistant", "content": turn_text})
            messages.append({"role": "user", "content": obs_prompt})

            if on_token:
                status_msg = f"\n\n*Agent executed {len(executed_tools)} tool action(s). Formulating next step...*\n\n"
                interim = ("\n\n".join(accumulated_responses) + status_msg).strip()
                await on_token(status_msg, interim, False)

        raw_full_text = "\n\n".join(accumulated_responses)
        clean_text = self.clean_chat_response(raw_full_text)
        if on_token:
            await on_token("", clean_text, True)

        return {
            "query": user_query,
            "response": clean_text,
            "raw_response": raw_full_text,
            "tools_executed": all_executed_tools,
            "turns_completed": current_turn,
        }
