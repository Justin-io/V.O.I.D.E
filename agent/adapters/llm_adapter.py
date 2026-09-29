"""LLM Adapter Subsystem for V.O.I.D.E.

Isolates reasoning provider from runtime execution.
Provides:
- Abstract LLMAdapter contract
- DeterministicReasoningAdapter for zero-network testing and hermetic reproducibility
- OpenAICompatibleAdapter for API execution and streaming
- APIStreamingAdapter for high-performance SSE streaming
"""

from __future__ import annotations
from abc import ABC, abstractmethod
import json
import os
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, Iterator, List, Optional

try:
    from voide.agent.runtime.prompt_engine import (
        CORE_IDENTITY_PROMPT,
        PROACTIVE_TRIGGERS_PROMPT,
    )
except ImportError:
    from agent.runtime.prompt_engine import (  # type: ignore[no-redef]
        CORE_IDENTITY_PROMPT,
        PROACTIVE_TRIGGERS_PROMPT,
    )


class LLMResponse:
    def __init__(
        self,
        tool: str,
        arguments: Dict[str, Any],
        hypothesis: Optional[str] = None,
        is_completed: bool = False,
        is_blocked: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        self.tool: str = tool
        self.arguments: Dict[str, Any] = arguments
        self.hypothesis: Optional[str] = hypothesis
        self.is_completed: bool = is_completed
        self.is_blocked: bool = is_blocked
        self.reason: Optional[str] = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "hypothesis": self.hypothesis,
            "is_completed": self.is_completed,
            "is_blocked": self.is_blocked,
            "reason": self.reason,
        }


class LLMAdapter(ABC):
    """Abstract reasoning provider interface."""

    @abstractmethod
    def generate_next_action(
        self,
        task_context: Dict[str, Any],
        available_tools: List[str],
    ) -> LLMResponse:
        """Evaluate task context and return next structured tool action."""
        pass


class DeterministicReasoningAdapter(LLMAdapter):
    """Scriptable deterministic adapter for reproducible unit and E2E tests."""

    def __init__(
        self,
        action_plan: Optional[List[LLMResponse]] = None,
        logic_fn: Optional[Callable[[Dict[str, Any], int], LLMResponse]] = None,
    ) -> None:
        self.action_plan: List[LLMResponse] = action_plan or []
        self.logic_fn: Optional[Callable[[Dict[str, Any], int], LLMResponse]] = logic_fn
        self.call_count: int = 0

    def generate_next_action(
        self,
        task_context: Dict[str, Any],
        available_tools: List[str],
    ) -> LLMResponse:
        self.call_count += 1
        if self.logic_fn:
            return self.logic_fn(task_context, self.call_count)

        if self.action_plan:
            idx = min(self.call_count - 1, len(self.action_plan) - 1)
            return self.action_plan[idx]

        return LLMResponse(
            tool="complete_task",
            arguments={"summary": "Default plan completed"},
            is_completed=True,
        )


class OpenAICompatibleAdapter(LLMAdapter):
    """Zero-dependency HTTP client for OpenAI / Gemini / Ollama / vLLM API compatible endpoints."""

    def __init__(
        self,
        endpoint_url: str = "https://api.openai.com/v1/chat/completions",
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        timeout: float = 30.0,
    ) -> None:
        self.endpoint_url: str = endpoint_url
        self.api_key: str = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model: str = model
        self.timeout: float = timeout

    def generate_next_action(
        self,
        task_context: Dict[str, Any],
        available_tools: List[str],
    ) -> LLMResponse:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        system_prompt = (
            f"{CORE_IDENTITY_PROMPT}\n\n"
            f"{PROACTIVE_TRIGGERS_PROMPT}\n\n"
            "Return JSON only matching schema: {\"tool\": string, \"arguments\": object, \"hypothesis\": string, \"is_completed\": boolean}\n"
            f"Available tools: {json.dumps(available_tools)}"
        )

        user_content = json.dumps({
            "task": task_context.get("task"),
            "phase": task_context.get("phase"),
            "iteration": task_context.get("iteration"),
            "last_action": task_context.get("last_action"),
            "last_observation": task_context.get("last_observation"),
            "working_files": task_context.get("working_files", []),
        })

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        req = urllib.request.Request(
            self.endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                choice = body["choices"][0]["message"]["content"]
                parsed = json.loads(choice)
                return LLMResponse(
                    tool=parsed.get("tool", "complete_task"),
                    arguments=parsed.get("arguments", {}),
                    hypothesis=parsed.get("hypothesis"),
                    is_completed=bool(parsed.get("is_completed", False)),
                )
        except Exception as err:
            return LLMResponse(
                tool="blocked",
                arguments={},
                is_blocked=True,
                reason=f"LLM API invocation failed: {err}",
            )

    def stream_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
    ) -> Iterator[str]:
        """Yield streaming text chunks over SSE."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }

        req = urllib.request.Request(
            self.endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta
                except Exception:
                    pass


class APIStreamingAdapter(LLMAdapter):
    """Adapter for pure API-Key streaming execution."""

    def __init__(
        self,
        endpoint_url: str = "https://api.openai.com/v1/chat/completions",
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
    ) -> None:
        self.client = OpenAICompatibleAdapter(
            endpoint_url=endpoint_url,
            api_key=api_key,
            model=model,
        )

    def generate_next_action(
        self,
        task_context: Dict[str, Any],
        available_tools: List[str],
    ) -> LLMResponse:
        return self.client.generate_next_action(task_context, available_tools)


class ChatGPTWebAdapter(APIStreamingAdapter):
    """Deprecated: Alias kept for backwards compatibility; delegates to pure API adapter."""

    def __init__(self, browser_controller: Any = None) -> None:
        super().__init__()
