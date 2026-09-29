"""Unit tests for V.O.I.D.E. Live Chat Streamer and Autonomous Tool Execution."""

import os
import tempfile
from voide.browser.chromium_shell.cdp_controller import CDPController
from voide.browser.chromium_shell.chat_streamer import ChatStreamer


def test_prompt_formatting():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)

        # Test HI prompt formatting
        p1 = streamer.format_prompt("HI")
        assert "V.O.I.D.E. SYSTEM PROTOCOL" in p1
        assert "User: HI" in p1

        # Test calculator prompt formatting
        p2 = streamer.format_prompt("make a py calculator")
        assert "V.O.I.D.E. AUTONOMOUS" in p2
        assert "Request: make a py calculator" in p2
        # CRITICAL RULE: The prompt MUST NEVER contain the absolute workspace directory!
        assert tmpdir not in p2
        assert "Project Root: ." in p2


def test_modular_prompt_engine_proactive_triggers():
    from voide.agent.runtime.prompt_engine import (
        build_initial_prompt,
        build_observation_prompt,
    )

    init_p = build_initial_prompt("fix failing test", manifests=["pyproject.toml"], tech_stack=["Python"])
    assert "### SELF-DIRECTED PROACTIVE TRIGGERS" in init_p
    assert "TRIGGER: EXPLORE & RETRIEVE" in init_p
    assert "TRIGGER: IMPLEMENT" in init_p
    assert "TRIGGER: VERIFY MACHINE TRUTH" in init_p
    assert "TRIGGER: AUTONOMOUS SELF-HEALING" in init_p

    # Test observation with error -> triggers AUTONOMOUS SELF-HEALING
    obs_error = build_observation_prompt([
        {"tool": "bash", "command": "pytest", "exit_code": 1, "status": "ERROR", "stderr": "AssertionError: 1 != 2"}
    ], turn=1, max_turns=5)
    assert "[AUTONOMOUS SELF-HEALING]" in obs_error
    assert "Do NOT ask the engineer" in obs_error

    # Test observation with file modification -> triggers VERIFY MACHINE TRUTH
    obs_mod = build_observation_prompt([
        {"tool": "write_file", "path": "calc.py", "status": "SUCCESS", "message": "created"}
    ], turn=2, max_turns=5)
    assert "[VERIFY MACHINE TRUTH]" in obs_mod

    # Test observation with data retrieval -> triggers IMPLEMENT
    obs_ret = build_observation_prompt([
        {"tool": "read_file", "path": "main.py", "status": "SUCCESS", "content": "print(1)\nprint(2)", "start_line": 1}
    ], turn=1, max_turns=5)
    assert "[IMPLEMENT]" in obs_ret
    assert "1: print(1)" in obs_ret




def test_tool_call_json_execution():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        
        gpt_response = (
            "Here is the calculator implementation:\n\n"
            "```tool_call\n"
            '{\n'
            '  "tool": "write_file",\n'
            '  "args": {\n'
            '    "path": "calculator.py",\n'
            '    "content": "print(\'calculator ready\')"\n'
            '  }\n'
            '}\n'
            "```\n"
            "File created successfully."
        )
        
        tools = streamer.parse_and_execute_tools(gpt_response, "make a py calculator")
        assert len(tools) == 1
        assert tools[0]["tool"] == "write_file"
        assert tools[0]["status"] == "SUCCESS"
        assert tools[0]["path"] == "calculator.py"
        
        written_file = os.path.join(tmpdir, "calculator.py")
        assert os.path.exists(written_file)
        with open(written_file, "r") as f:
            assert f.read() == "print('calculator ready')"


def test_markdown_code_block_execution():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        
        gpt_response = (
            "Python\n"
            "Run\n"
            "# calculator.py\n"
            "import ast\n"
            "def calculate(expr):\n"
            "    return eval(expr)\n"
        )
        
        tools = streamer.parse_and_execute_tools(gpt_response, "make a py calculator")
        assert len(tools) == 1
        assert tools[0]["tool"] == "write_file"
        assert tools[0]["path"] == "calculator.py"
        
        written_file = os.path.join(tmpdir, "calculator.py")
        assert os.path.exists(written_file)
        with open(written_file, "r") as f:
            content = f.read()
            assert "import ast" in content
            assert "calculate(expr)" in content


def test_path_traversal_prevention():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        res = streamer._execute_tool("write_file", {"path": "../../etc/evil.sh", "content": "rm -rf /"})
        assert res["status"] == "ERROR"
        assert "Path traversal detected" in res["error"]


def test_read_file_and_bash_tools():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        # Create a file
        streamer._execute_tool("write_file", {"path": "hello.txt", "content": "Hello VOIDE!"})

        # Read it back
        read_res = streamer._execute_tool("read_file", {"path": "hello.txt"})
        assert read_res["status"] == "SUCCESS"
        assert read_res["content"] == "Hello VOIDE!"

        # Execute bash
        bash_res = streamer._execute_tool("bash", {"command": "echo 'VOIDE_PTY_OK'"})
        assert bash_res["status"] == "SUCCESS"
        assert "VOIDE_PTY_OK" in bash_res["stdout"]


def test_observer_bridge_script_loading():
    cdp = CDPController()
    script = cdp.get_observer_script()
    assert len(script) > 50
    assert "MutationObserver" in script
    assert "__voide_bridge" in script


def test_cdp_target_selector_resolution():
    cdp = CDPController()
    # Mock cached elements
    cdp.cached_elements = [
        {
            "uid": "el-input-1",
            "tag": "textarea",
            "role": "textbox",
            "ariaLabel": "",
            "placeholder": "Type a message...",
            "text": "",
            "id": "prompt-input",
            "classes": "chat-input",
            "visible": True,
            "disabled": False,
        },
        {
            "uid": "el-send-1",
            "tag": "button",
            "role": "button",
            "ariaLabel": "",
            "placeholder": "",
            "text": "Send",
            "id": "send-button",
            "classes": "btn-send",
            "visible": True,
            "disabled": False,
        },
    ]

    input_sel = cdp.get_target_selector("MESSAGE_INPUT")
    assert input_sel == "#prompt-input"

    send_sel = cdp.get_target_selector("SEND_BUTTON")
    assert send_sel == "#send-button"


def test_list_directory_filters_hidden_files():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        # Create normal and hidden files
        os.makedirs(os.path.join(tmpdir, "src"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, ".git"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "__pycache__"), exist_ok=True)
        with open(os.path.join(tmpdir, "main.py"), "w") as f:
            f.write("print('ok')")
        with open(os.path.join(tmpdir, ".secret"), "w") as f:
            f.write("hidden")

        res = streamer._execute_tool("list_directory", {"path": ""})
        assert res["status"] == "SUCCESS"
        names = [e["name"] for e in res["entries"]]
        assert "main.py" in names
        assert "src" in names
        assert ".git" not in names
        assert ".secret" not in names


def test_proactive_attached_files_in_prompt():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        with open(os.path.join(tmpdir, "calculator.py"), "w") as f:
            f.write("def add(a, b): return a + b\n")

        p = streamer.format_prompt("read calculator.py and explain it")
        assert "### ATTACHED WORKSPACE SOURCE CODE" in p
        assert "=== File: calculator.py ===" in p
        assert "def add(a, b): return a + b" in p
        assert tmpdir not in p


def test_disclaimer_detection_and_cleaning():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)

        chatbot_monologue = (
            "I retrieved the available V.O.I.D.E. project material from the accessible workspace/library context. What I have is:\n\n"
            "V.O.I.D.E. architecture/specification\n"
            "Multi-layer telemetry anomaly detection system\n"
            "Flutter desktop shell\n\n"
            "Critical distinction: I have retrieved the V.O.I.D.E. architectural material and project metadata, "
            "but the actual contents of those individual source files are not present in the accessible file attachments/library results. "
            "Therefore I do not have their complete source bodies to truthfully claim that I read every implementation file."
        )

        assert streamer._is_disclaimer(chatbot_monologue) is True

        cleaned = streamer.clean_chat_response(chatbot_monologue)
        assert cleaned == ""

        mixed_response = f"{chatbot_monologue}\n\n### Actual Implementation\n```python\nprint('hello')\n```"
        cleaned_mixed = streamer.clean_chat_response(mixed_response)
        assert "### Actual Implementation" in cleaned_mixed
        assert "print('hello')" in cleaned_mixed
        assert "Critical distinction" not in cleaned_mixed
        assert "I retrieved the available" not in cleaned_mixed


def test_disclaimer_triggers_proactive_tool_execution():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        with open(os.path.join(tmpdir, "sample.py"), "w") as f:
            f.write("x = 42\n")

        chatbot_text = (
            "Critical distinction: I have retrieved the V.O.I.D.E. architectural material, "
            "therefore I do not have their complete source bodies to truthfully claim that I read every implementation file."
        )

        tools = streamer.parse_and_execute_tools(chatbot_text, "read all files")
        assert len(tools) >= 1
        assert tools[0]["tool"] == "read_file"
        assert tools[0]["path"] == "sample.py"
        assert tools[0]["status"] == "SUCCESS"
        assert "x = 42" in tools[0]["content"]


def test_multiturn_followup_prompt_formatting():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        initial_p = streamer.format_prompt("create a calculator", is_followup=False)
        assert "[V.O.I.D.E. AUTONOMOUS ENGINEERING PROTOCOL]" in initial_p

        followup_p = streamer.format_prompt("now add a multiply function", is_followup=True)
        assert "[V.O.I.D.E. CONVERSATION CONTINUATION]" in followup_p
        assert "User Request: now add a multiply function" in followup_p
        # Follow-up should not re-dump full initial protocol identity header
        assert "[V.O.I.D.E. AUTONOMOUS ENGINEERING PROTOCOL]" not in followup_p


def test_tool_execution_guard_informational_block():
    cdp = CDPController()
    with tempfile.TemporaryDirectory() as tmpdir:
        streamer = ChatStreamer(cdp, tmpdir)
        # Informational question without write intent
        resp = "Here is an example of sorting in python:\n```python\nitems = [3, 1, 2]\nitems.sort()\n```"
        tools = streamer.parse_and_execute_tools(resp, "how does sort work in python?")
        # Should NOT write a solution.py file
        assert len(tools) == 0
        assert not os.path.exists(os.path.join(tmpdir, "solution.py"))


def test_stale_singleton_lock_cleanup():
    with tempfile.TemporaryDirectory() as tmpdir:
        cdp = CDPController(profile_dir=tmpdir)
        lock_file = os.path.join(tmpdir, "SingletonLock")
        # Point to an impossible/dead PID like 99999999
        os.symlink("host-99999999", lock_file)
        assert os.path.islink(lock_file)

        cdp.clean_stale_singleton_lock()
        assert not os.path.exists(lock_file)
        assert not os.path.islink(lock_file)

