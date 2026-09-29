"""Live integration test for CDP Controller and DOM discovery."""

import os
import tempfile
from voide.browser.chromium_shell.cdp_controller import CDPController
from voide.browser.chromium_shell.chat_streamer import ChatStreamer


def test_cdp_browser_viewport_and_discovery():
    """Verify CDP controller launches Chrome pointing to local viewport and discovers DOM."""
    cdp = CDPController(port=9222, headless=True)
    started = cdp.start_browser(initial_url="about:blank", force_non_headless=False)
    assert started is True
    assert cdp.is_cdp_available() is True

    try:
        # Verify active page tab
        tab = cdp.get_active_tab()
        assert tab is not None
        assert "webSocketDebuggerUrl" in tab

        # Inject observer bridge
        injected = cdp._run_sync(cdp.inject_observer_bridge_async())
        assert injected is True

        # Run element discovery on the live page
        elements = cdp.discover_elements()
        assert isinstance(elements, list)

        # Verify mutation sync check
        synced = cdp._run_sync(cdp.check_and_sync_mutations_async())
        assert isinstance(synced, bool)
    finally:
        cdp.close()


def test_chat_streamer_tool_execution():
    """Verify ChatStreamer tool call parsing and local workspace execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cdp = CDPController(port=9222, headless=True)
        streamer = ChatStreamer(cdp, tmpdir)

        # Test write_file tool execution
        tool_payload = """
I will create a calculator module for the workspace.
```tool_call
{
  "tool": "write_file",
  "args": {
    "path": "calculator.py",
    "content": "def calculate(a, b):\\n    return a + b\\n\\nif __name__ == '__main__':\\n    print(calculate(10, 20))\\n"
  }
}
```
Module created successfully.
"""
        executed = streamer.parse_and_execute_tools(tool_payload, "make a py calculator")
        assert len(executed) == 1
        assert executed[0]["tool"] == "write_file"
        assert executed[0]["status"] == "SUCCESS"

        calc_file = os.path.join(tmpdir, "calculator.py")
        assert os.path.exists(calc_file)
        with open(calc_file, "r") as f:
            content = f.read()
            assert "def calculate" in content

        # Test bash tool execution
        bash_payload = """
```tool_call
{
  "tool": "bash",
  "args": {
    "command": "python3 calculator.py"
  }
}
```
"""
        bash_executed = streamer.parse_and_execute_tools(bash_payload, "run calculator")
        assert len(bash_executed) == 1
        assert bash_executed[0]["tool"] == "bash"
        assert bash_executed[0]["status"] == "SUCCESS"
        assert "30" in bash_executed[0].get("stdout", "")
