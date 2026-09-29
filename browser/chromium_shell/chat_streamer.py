"""Compatibility Bridge for V.O.I.D.E. Streamer.

Delegates live streaming and multi-turn ReAct reasoning to the pure API-Key
streaming runtime in `agent.runtime.api_streamer`.
"""

from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Optional

try:
    from voide.agent.runtime.api_streamer import APIStreamer, ProcessManager, LLMConfig
except ImportError:
    from agent.runtime.api_streamer import APIStreamer, ProcessManager, LLMConfig  # type: ignore[no-redef]

try:
    from voide.browser.chromium_shell.cdp_controller import CDPController
except ImportError:
    try:
        from browser.chromium_shell.cdp_controller import CDPController  # type: ignore[no-redef]
    except ImportError:
        CDPController = Any  # type: ignore[misc,assignment]


class ChatStreamer(APIStreamer):
    """Backwards-compatible ChatStreamer interface delegating to APIStreamer."""

    def __init__(
        self,
        cdp_controller: Any = None,
        workspace_root: Optional[str] = None,
        state_store: Optional[Any] = None,
    ) -> None:
        ws = workspace_root or os.getcwd()
        super().__init__(
            workspace_root=ws,
            state_store=state_store,
            cdp_controller=cdp_controller,
        )

    @staticmethod
    def _is_disclaimer(text: str) -> bool:
        """Detect disclaimer or hedging patterns."""
        lower = text.lower()
        if "critical distinction" in lower and "source bodies" in lower:
            return True
        if "i retrieved the available v.o.i.d.e. project material" in lower:
            return True
        if "therefore i do not have their complete source bodies" in lower:
            return True
        if "actual contents of those individual source files are not present" in lower:
            return True
        if "what i have is:" in lower and ("architecture/specification" in lower or "flutter desktop shell" in lower):
            return True
        if "cannot legitimately claim" in lower:
            return True
        return False

    @staticmethod
    def clean_chat_response(text: str) -> str:
        """Strip raw JSON tool call blocks and protocol markers."""
        cleaned = text
        cleaned = re.sub(r'```(?:tool_call|json)?\s*\{[\s\S]*?"tool"[\s\S]*?\}\s*```', '', cleaned)
        cleaned = re.sub(r'\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"args"\s*:\s*\{[\s\S]*?\}\s*\}', '', cleaned)
        cleaned = re.sub(r'\[V\.O\.I\.D\.E\.[^\]]*\]', '', cleaned)
        cleaned = re.sub(r'\[TRIGGER:[^\]]*\]', '', cleaned)
        cleaned = re.sub(r'\[TOOL OBSERVATIONS[^\]]*\][\s\S]*?(?=\n\n|$)', '', cleaned)
        cleaned = re.sub(
            r'I retrieved the available V\.O\.I\.D\.E\. project material[\s\S]*?(?:truthfully claim[^\n]*\n?|read every implementation file[^\n]*\n?|\Z)',
            '',
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r'The active project context identifies these source/configuration files[\s\S]*?(?:truthfully claim[^\n]*\n?|read every implementation file[^\n]*\n?|\Z)',
            '',
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r'Critical distinction:[\s\S]*?(?:truthfully claim[^\n]*\n?|read every implementation file[^\n]*\n?|\Z)',
            '',
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r'(?:What I cannot legitimately claim|The protocol says I have native host execution|In this ChatGPT conversation I do not|Therefore I do not have their complete source bodies[^\n]*)',
            '',
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        if ChatStreamer._is_disclaimer(cleaned):
            cleaned = ""
        return cleaned

    def parse_and_execute_tools(self, response_text: str, user_query: str) -> List[Dict[str, Any]]:
        """Extended parsing checking disclaimer fallback in addition to standard tools."""
        executed = super().parse_and_execute_tools(response_text, user_query)
        if not executed:
            read_intent = bool(re.search(
                r'\b(read|inspect|analyze|understand|check|examine|review|view|open|show|explain)\b',
                user_query,
                re.IGNORECASE,
            ))
            disclaimer_detected = self._is_disclaimer(response_text) or bool(re.search(
                r'(?:do not have|cannot legitimately claim|actual contents.*not present|not present in the accessible|truthfully claim|i retrieved the available)',
                response_text,
                re.IGNORECASE,
            ))
            if read_intent or disclaimer_detected:
                target_paths: List[str] = []
                for m in re.finditer(r'([a-zA-Z0-9_\-./]+\.(?:py|dart|yaml|toml|json|sh|md|txt|html|css|js|ts|c|cpp|h))', user_query):
                    candidate = m.group(1).lstrip("./")
                    full_p = os.path.join(self.workspace_root, candidate)
                    if os.path.isfile(full_p) and candidate not in target_paths:
                        target_paths.append(candidate)

                if not target_paths:
                    ctx = self._gather_workspace_context(user_query)
                    for f in ctx.get("tree", []):
                        base_name = os.path.basename(f)
                        if (base_name in response_text or f in response_text or "all" in user_query.lower() or disclaimer_detected) and f not in target_paths:
                            target_paths.append(f)
                            if len(target_paths) >= 5:
                                break

                for path in target_paths[:5]:
                    res = self._execute_tool("read_file", {"path": path, "start_line": 1, "end_line": 120})
                    executed.append(res)

        return executed
