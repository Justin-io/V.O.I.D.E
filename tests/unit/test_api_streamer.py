"""Unit tests for V.O.I.D.E. API-Key Streaming Reasoning Engine and Multi-Turn ReAct Loop."""

import asyncio
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
try:
    from voide.agent.runtime.api_streamer import APIStreamer, LLMConfig, ProcessManager
except ImportError:
    from agent.runtime.api_streamer import APIStreamer, LLMConfig, ProcessManager


def test_llm_config_initialization_and_masking():
    cfg = LLMConfig(
        provider="openai",
        api_key="sk-proj-1234567890abcdef1234567890",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    )
    d = cfg.to_dict(mask_secrets=True)
    assert d["provider"] == "openai"
    assert d["model"] == "gpt-4o"
    assert d["api_key_configured"] is True
    assert d["api_key_masked"].startswith("sk-p")
    assert d["api_key_masked"].endswith("7890")
    assert "abcdef" not in d["api_key_masked"]

    # Test update
    cfg.update(model="llama3.1", provider="ollama", base_url="http://localhost:11434/v1")
    assert cfg.model == "llama3.1"
    assert cfg.provider == "ollama"
    assert cfg.base_url == "http://localhost:11434/v1"


def test_api_streamer_tool_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = APIStreamer(workspace_root=tmpdir)

        # 1. Write file
        res_write = streamer._execute_tool("write_file", {
            "path": "math_ops.py",
            "content": "def multiply(x, y):\n    return x * y\n",
        })
        assert res_write["status"] == "SUCCESS"
        assert os.path.exists(os.path.join(tmpdir, "math_ops.py"))

        # 2. Read file
        res_read = streamer._execute_tool("read_file", {
            "path": "math_ops.py",
            "start_line": 1,
            "end_line": 10,
        })
        assert res_read["status"] == "SUCCESS"
        assert "def multiply" in res_read["content"]

        # 3. Patch file
        res_patch = streamer._execute_tool("patch_file", {
            "path": "math_ops.py",
            "target": "return x * y",
            "replacement": "return float(x * y)",
        })
        assert res_patch["status"] == "SUCCESS"
        with open(os.path.join(tmpdir, "math_ops.py"), "r") as f:
            assert "float(x * y)" in f.read()

        # 4. List directory
        res_list = streamer._execute_tool("list_directory", {"path": ""})
        assert res_list["status"] == "SUCCESS"
        entries = [e["name"] for e in res_list["entries"]]
        assert "math_ops.py" in entries

        # 5. Search files
        res_search = streamer._execute_tool("search_files", {"query": "multiply"})
        assert res_search["status"] == "SUCCESS"
        assert res_search["count"] >= 1
        assert res_search["matches"][0]["file"] == "math_ops.py"

        # 6. Bash execution
        res_bash = streamer._execute_tool("bash", {"command": "python3 math_ops.py"})
        assert res_bash["status"] == "SUCCESS"
        assert res_bash["exit_code"] == 0


def test_process_manager_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = ProcessManager(workspace_root=tmpdir)
        start_res = pm.start_process("sleep 0.1 && echo done", process_id="test_proc")
        assert start_res["status"] == "STARTED"

        wait_res = pm.wait_process("test_proc", timeout_seconds=2.0)
        assert wait_res["status"] == "COMPLETED"
        assert wait_res["exit_code"] == 0


def test_api_streamer_parse_and_execute_tool_blocks():
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = APIStreamer(workspace_root=tmpdir)
        response_with_tool = """
I will now generate the test runner.
```tool_call
{
  "tool": "write_file",
  "args": {
    "path": "runner.py",
    "content": "print('runner active')\n"
  }
}
```
Tool dispatched.
"""
        executed = streamer.parse_and_execute_tools(response_with_tool, "create runner.py")
        assert len(executed) == 1
        assert executed[0]["tool"] == "write_file"
        assert executed[0]["status"] == "SUCCESS"
        assert os.path.exists(os.path.join(tmpdir, "runner.py"))


def test_api_streamer_missing_key_guidance():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = LLMConfig(provider="openai", api_key="", base_url="https://api.openai.com/v1")
        streamer = APIStreamer(workspace_root=tmpdir, llm_config=cfg)

        async def _run():
            tokens = []
            async def on_token(delta, full, done):
                tokens.append(delta)

            res = await streamer.stream_chat("what is this project?", on_token=on_token)
            assert "API Key Required" in res["response"]
            assert "export OPENAI_API_KEY" in res["response"]

        asyncio.run(_run())
