"""Integration Tests for IPCServer WebSocket Bridge."""

import asyncio
import json
import os
import tempfile
import websockets

from voide.agent.runtime.ipc_server import IPCServer


async def _async_test_ipc():
    with tempfile.TemporaryDirectory() as tmpdir:
        port = 8799
        server = IPCServer(workspace_root=tmpdir, host="127.0.0.1", port=port)
        server_task = asyncio.create_task(server.start())
        await asyncio.sleep(0.2)

        try:
            uri = f"ws://127.0.0.1:{port}"
            async with websockets.connect(uri) as ws:
                # 1. Receive HELLO
                hello_raw = await ws.recv()
                hello = json.loads(hello_raw)
                assert hello["type"] == "HELLO"
                assert hello["version"] == "1.0.0-linux"
                assert hello["port"] == port

                # 2. Get workspace action
                await ws.send(json.dumps({
                    "action": "get_workspace",
                    "id": "0",
                    "payload": {},
                }))
                resp_ws = json.loads(await ws.recv())
                assert resp_ws["success"] is True
                assert resp_ws["result"]["port"] == port
                assert resp_ws["result"]["workspace"] == os.path.realpath(tmpdir)

                # 3. Register project
                await ws.send(json.dumps({
                    "action": "register_project",
                    "id": "1",
                    "payload": {"name": "Test IPC Project"},
                }))
                resp1 = json.loads(await ws.recv())
                assert resp1["success"] is True
                pid = resp1["result"]
                assert pid.startswith("proj-")

                # 3. Create task
                await ws.send(json.dumps({
                    "action": "create_task",
                    "id": "2",
                    "payload": {
                        "project_id": pid,
                        "objective": "Verify IPC communication",
                    },
                }))

                # Should receive TASK_CREATED event and RESPONSE
                msg_a = json.loads(await ws.recv())
                msg_b = json.loads(await ws.recv())

                messages = [msg_a, msg_b]
                event_msg = next((m for m in messages if m.get("type") == "EVENT"), None)
                resp_msg = next((m for m in messages if m.get("type") == "RESPONSE"), None)

                assert event_msg is not None
                assert event_msg["event"]["event_type"] == "TASK_CREATED"
                assert resp_msg is not None
                assert resp_msg["success"] is True
                assert resp_msg["result"].startswith("task-")

                # 4. Test Browser IPC endpoints without event loop collision
                await ws.send(json.dumps({
                    "action": "browser_status",
                    "id": "3",
                    "payload": {},
                }))
                resp_status = json.loads(await ws.recv())
                assert resp_status["success"] is True
                assert "connected" in resp_status["result"]

                await ws.send(json.dumps({
                    "action": "browser_inspect",
                    "id": "4",
                    "payload": {},
                }))
                resp_inspect = json.loads(await ws.recv())
                assert resp_inspect["success"] is True

                await ws.send(json.dumps({
                    "action": "browser_discover",
                    "id": "5",
                    "payload": {},
                }))
                resp_discover = json.loads(await ws.recv())
                assert resp_discover["success"] is True

                await ws.send(json.dumps({
                    "action": "browser_screenshot",
                    "id": "6",
                    "payload": {},
                }))
                resp_shot = json.loads(await ws.recv())
                assert resp_shot["success"] is True

                # 5. Test Terminal actions & PTY reader broadcast
                await ws.send(json.dumps({
                    "action": "terminal_start",
                    "id": "7",
                    "payload": {"session_id": "test-term-1"},
                }))
                resp_term = json.loads(await ws.recv())
                assert resp_term["success"] is True
                assert resp_term["result"]["session_id"] == "test-term-1"

                await ws.send(json.dumps({
                    "action": "terminal_write",
                    "id": "8",
                    "payload": {"session_id": "test-term-1", "data": "echo VOIDE_OK\n"},
                }))
                resp_write = json.loads(await ws.recv())
                assert resp_write["success"] is True
                assert resp_write["result"]["bytes_written"] > 0

                # Expect TERMINAL_OUTPUT broadcast containing echo or output
                term_msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                assert term_msg["type"] == "TERMINAL_OUTPUT"
                assert term_msg["session_id"] == "test-term-1"

                # 5. Test LLM Configuration IPC endpoints
                await ws.send(json.dumps({
                    "action": "llm_get_config",
                    "id": "9",
                    "payload": {},
                }))
                resp_cfg = json.loads(await ws.recv())
                assert resp_cfg["success"] is True
                assert "base_url" in resp_cfg["result"]
                assert "model" in resp_cfg["result"]

                await ws.send(json.dumps({
                    "action": "llm_set_config",
                    "id": "10",
                    "payload": {
                        "api_key": "sk-test-live-key",
                        "model": "gpt-4o-mini",
                        "base_url": "https://api.openai.com/v1",
                    },
                }))
                resp_set = json.loads(await ws.recv())
                assert resp_set["success"] is True
                assert resp_set["result"]["model"] == "gpt-4o-mini"
                assert resp_set["result"]["api_key_configured"] is True
                assert "live" not in resp_set["result"]["api_key_masked"]

        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass


def test_ipc_server_lifecycle():
    asyncio.run(_async_test_ipc())

