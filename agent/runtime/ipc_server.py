"""Local IPC & Event Bridge Server for V.O.I.D.E.

Implements Sections 40, 41, and 42.
Bridges Flutter Desktop Shell to Python Agent Runtime, PTY Manager,
and DOM Intelligence via bidirectional WebSocket JSON protocol.
"""

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any, Dict, Optional, Set

import numpy as np
import uuid
import websockets

from voide.agent.adapters.llm_adapter import DeterministicReasoningAdapter, OpenAICompatibleAdapter
from voide.agent.runtime.agent_core import AgentCore
from voide.agent.runtime.event_engine import EventEngine, EventEnvelope
try:
    from voide.agent.storage.state_store import StateStore
except ImportError:
    from agent.storage.state_store import StateStore  # type: ignore[no-redef]
try:
    from voide.agent.runtime.api_streamer import APIStreamer, ProcessManager, LLMConfig
except ImportError:
    from agent.runtime.api_streamer import APIStreamer, ProcessManager, LLMConfig  # type: ignore[no-redef]
from voide.native.linux_host.fs_service import FilesystemService

logger = logging.getLogger("voide.ipc")
logging.getLogger("websockets.server").setLevel(logging.CRITICAL)
logging.getLogger("websockets").setLevel(logging.ERROR)



class IPCServer:
    """Async WebSocket IPC bridge for V.O.I.D.E."""

    def __init__(
        self,
        workspace_root: str,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self.workspace_root: str = os.path.realpath(workspace_root)
        self.host: str = host
        self.port: int = port if port is not None else int(os.environ.get("VOIDE_IPC_PORT", "8766"))
        self.db_path: str = db_path or os.path.join(self.workspace_root, ".voide", "state.db")
        
        # Configure logging to .voide/agent.log
        log_dir = os.path.join(self.workspace_root, ".voide")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "agent.log")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(formatter)
            logger.addHandler(sh)
        
        self.state_store: StateStore = StateStore(self.db_path)
        self.event_engine: EventEngine = EventEngine()
        self.llm_adapter = OpenAICompatibleAdapter() if os.environ.get("OPENAI_API_KEY") else DeterministicReasoningAdapter()
        self.agent_core: AgentCore = AgentCore(
            workspace_root=self.workspace_root,
            state_store=self.state_store,
            llm_adapter=self.llm_adapter,
            event_engine=self.event_engine,
        )
        self.chat_streamer = APIStreamer(
            workspace_root=self.workspace_root,
            state_store=self.state_store,
        )
        self.connected_clients: Set[Any] = set()

        
        # Subscribe event broadcast
        self.event_engine.subscribe("*", self._broadcast_event_sync)

    def _broadcast_event_sync(self, event: EventEnvelope) -> None:
        """Forward internal runtime events to all connected UI sockets."""
        if not self.connected_clients:
            return
        payload = json.dumps({"type": "EVENT", "event": event.to_dict()})
        websockets.broadcast(self.connected_clients, payload)

    def _resolve_dataset_path(self, path: str) -> str:
        """Resolve telemetry dataset path supporting relative, workspace-relative, and datasets/ subfolder."""
        if not path:
            datasets_dir = os.path.join(self.workspace_root, "datasets")
            csvs = sorted([f for f in os.listdir(datasets_dir) if f.endswith(".csv")]) if os.path.exists(datasets_dir) else []
            path = csvs[0] if csvs else ""
        if os.path.isabs(path) and os.path.exists(path):
            return path
        cand1 = os.path.join(self.workspace_root, path)
        if os.path.exists(cand1):
            return cand1
        cand2 = os.path.join(self.workspace_root, "datasets", path)
        if os.path.exists(cand2):
            return cand2
        cand3 = os.path.join(self.workspace_root, "datasets", os.path.basename(path))
        if os.path.exists(cand3):
            return cand3
        return cand1

    def _attach_pty_reader(self, session_id: str, session: Any) -> None:
        """Attach an async reader to PTY master fd with safe EOF and error deregistration."""
        if session.master_fd is None:
            return
        fd = session.master_fd
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        def _on_pty_read() -> None:
            if session.master_fd is None or session.master_fd != fd:
                try:
                    loop.remove_reader(fd)
                except Exception:
                    pass
                return

            try:
                raw = os.read(fd, 4096)
                if raw:
                    if self.connected_clients:
                        text = raw.decode("utf-8", errors="replace")
                        websockets.broadcast(
                            self.connected_clients,
                            json.dumps({"type": "TERMINAL_OUTPUT", "session_id": session_id, "data": text}),
                        )
                else:
                    # EOF encountered: child process exited or slave closed
                    try:
                        loop.remove_reader(fd)
                    except Exception:
                        pass
            except (BlockingIOError, InterruptedError):
                pass
            except OSError:
                # EIO / bad descriptor on Linux when terminal closes
                try:
                    loop.remove_reader(fd)
                except Exception:
                    pass

        try:
            loop.add_reader(fd, _on_pty_read)
        except Exception:
            pass

    async def handle_client(self, websocket: Any) -> None:
        """Handle incoming client connection messages concurrently without blocking."""
        self.connected_clients.add(websocket)
        send_lock = asyncio.Lock()

        async def _safe_send(payload_str: str) -> None:
            async with send_lock:
                await websocket.send(payload_str)

        async def _process_message(raw_msg: str) -> None:
            msg_id = "0"
            action = "unknown"
            try:
                req = json.loads(raw_msg)
                action = req.get("action", "unknown")
                msg_id = str(req.get("id", "0"))
                payload = req.get("payload")
                if not isinstance(payload, dict) or not payload:
                    payload = {k: v for k, v in req.items() if k not in ("action", "id", "type")}
                logger.info("IPC Request received: action=%s, id=%s", action, msg_id)

                result = await self.dispatch(action, payload)
                await _safe_send(json.dumps({
                    "type": "RESPONSE",
                    "id": msg_id,
                    "success": True,
                    "result": result,
                }))
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as err:
                logger.error("IPC dispatch error on action '%s' [id=%s]: %s", action, msg_id, err, exc_info=True)
                try:
                    await _safe_send(json.dumps({
                        "type": "RESPONSE",
                        "id": msg_id,
                        "success": False,
                        "error": str(err),
                    }))
                except Exception:
                    pass


        try:
            # Send initial hello & system status
            await _safe_send(json.dumps({
                "type": "HELLO",
                "workspace": self.workspace_root,
                "version": "1.0.0-linux",
                "port": self.port,
            }))

            async for raw_message in websocket:
                asyncio.create_task(_process_message(raw_message))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connected_clients.discard(websocket)

    async def dispatch(self, action: str, payload: Dict[str, Any]) -> Any:
        """Dispatch IPC command to appropriate runtime subsystem."""
        if action == "get_workspace":
            return {
                "workspace": self.workspace_root,
                "port": self.port,
                "version": "1.0.0-linux",
            }

        elif action == "register_project":
            return self.state_store.register_project(
                root_path=payload.get("root_path", self.workspace_root),
                name=payload.get("name", "Default Project"),
            )

        elif action == "create_task":
            return self.agent_core.start_task(
                project_id=payload.get("project_id", "default"),
                objective=payload.get("objective", ""),
                success_criteria=payload.get("success_criteria", []),
                max_iterations=payload.get("max_iterations", 25),
            )

        elif action == "step_task":
            task_id = payload.get("task_id", "")
            return self.agent_core.step(task_id)

        elif action == "run_task":
            task_id = payload.get("task_id", "")
            return self.agent_core.run_until_completion(task_id, payload.get("max_steps", 25))

        elif action == "decide_approval":
            approval_id = payload.get("approval_id", "")
            approved = bool(payload.get("approved", False))
            return self.state_store.decide_approval(approval_id, approved)

        elif action == "get_task":
            task_id = payload.get("task_id", "")
            return self.state_store.get_task(task_id)

        elif action == "get_events":
            task_id = payload.get("task_id")
            limit = payload.get("limit", 50)
            return self.state_store.get_events(task_id, limit)

        elif action == "list_files":
            rel_path = payload.get("path", "")
            return self.agent_core.tool_broker.fs_service.list_directory(rel_path)

        elif action == "read_file":
            rel_path = payload.get("path", "")
            return self.agent_core.tool_broker.fs_service.read_file(rel_path)

        elif action == "write_file":
            rel_path = payload.get("path", "")
            content = payload.get("content", "")
            return self.agent_core.tool_broker.fs_service.write_file(rel_path, content)

        elif action == "workspace_open":
            new_path = payload.get("path", "").strip()
            if not new_path:
                raise ValueError("Workspace path cannot be empty")
            real_path = os.path.realpath(os.path.expanduser(new_path))
            if not os.path.exists(real_path):
                os.makedirs(real_path, exist_ok=True)
            self.workspace_root = real_path
            self.chat_streamer.workspace_root = real_path
            self.chat_streamer.process_manager = ProcessManager(real_path)
            self.agent_core.workspace_root = real_path
            self.agent_core.tool_broker.fs_service = FilesystemService(real_path)
            self.agent_core.tool_broker.pty_manager.close_all()
            self.state_store.register_project(real_path, os.path.basename(real_path) or "Workspace")

            if self.connected_clients:
                websockets.broadcast(
                    self.connected_clients,
                    json.dumps({"type": "WORKSPACE_CHANGED", "workspace": self.workspace_root}),
                )
            return {"workspace": self.workspace_root, "status": "OPENED"}

        elif action == "create_directory":
            rel_path = payload.get("path", "")
            return self.agent_core.tool_broker.fs_service.create_directory(rel_path)

        elif action == "delete_file":
            rel_path = payload.get("path", "")
            return self.agent_core.tool_broker.fs_service.delete_file(rel_path)

        elif action == "rename_file":
            old_path = payload.get("old_path", "")
            new_path = payload.get("new_path", "")
            return self.agent_core.tool_broker.fs_service.rename_file(old_path, new_path)

        elif action in ("chat_sessions_list", "list_chat_sessions"):
            ws = payload.get("workspace", self.workspace_root)
            return self.state_store.list_chat_sessions(ws)

        elif action in ("chat_session_create", "chat_new"):
            ws = payload.get("workspace", self.workspace_root)
            title = payload.get("title", "New Chat")
            session = self.state_store.create_chat_session(ws, title)
            try:
                await self.chat_streamer.new_chat()
                logger.info("Opened new chat in ChatGPT for session %s", session.get("session_id"))
            except Exception as e:
                logger.warning("Could not open new chat in ChatGPT: %s", e)
            return session

        elif action in ("chat_session_messages", "get_chat_session"):
            sid = payload.get("session_id", "")
            messages = self.state_store.get_chat_messages(sid)
            session_info = self.state_store.get_chat_session(sid)
            conv_url = session_info.get("conversation_url") if session_info else None
            if conv_url and self.chat_streamer.cdp.is_cdp_available():
                page_tab = self.chat_streamer.cdp.get_chatgpt_tab()
                if page_tab and conv_url not in page_tab.get("url", ""):
                    asyncio.create_task(self.chat_streamer.cdp.navigate_async(conv_url))
            return {"session_id": sid, "messages": messages, "conversation_url": conv_url}

        elif action in ("chat_session_delete", "delete_chat_session"):
            sid = payload.get("session_id", "")
            return {"deleted": self.state_store.delete_chat_session(sid)}

        elif action == "terminal_start":
            session_id = payload.get("session_id", "term-user-1")
            existing = self.agent_core.tool_broker.pty_manager.get_session(session_id)
            if existing and existing.is_alive:
                return {"session_id": session_id, "pid": existing.pid}

            session = self.agent_core.tool_broker.pty_manager.create_session(
                session_id=session_id,
                cwd=self.workspace_root,
            )
            self._attach_pty_reader(session_id, session)
            return {"session_id": session_id, "pid": session.pid}

        elif action == "terminal_interrupt":
            session_id = payload.get("session_id", "term-user-1")
            session = self.agent_core.tool_broker.pty_manager.get_session(session_id)
            if session:
                session.send_signal(signal.SIGINT)
                return {"interrupted": True}
            return {"interrupted": False}

        elif action == "terminal_write":
            session_id = payload.get("session_id", "term-user-1")
            data = payload.get("data", "")
            session = self.agent_core.tool_broker.pty_manager.get_session(session_id)
            if not session:
                # Auto-create the session
                session = self.agent_core.tool_broker.pty_manager.create_session(
                    session_id=session_id,
                    cwd=self.workspace_root,
                )
                self._attach_pty_reader(session_id, session)
            written = session.write(data.encode("utf-8"))
            return {"bytes_written": written}

        elif action == "terminal_read":
            session_id = payload.get("session_id", "")
            session = self.agent_core.tool_broker.pty_manager.get_session(session_id)
            output = ""
            if session and session.master_fd is not None:
                try:
                    raw = os.read(session.master_fd, 4096)
                    output = raw.decode("utf-8", errors="replace")
                except (BlockingIOError, OSError):
                    output = ""
            return {"session_id": session_id, "output": output}

        elif action == "browser_launch":
            url = payload.get("url", "https://chatgpt.com")
            show_window = payload.get("show_window", payload.get("headless") is False if "headless" in payload else False)
            started = self.agent_core.tool_broker.browser.start_browser(initial_url=url, force_non_headless=show_window)
            return {
                "started": started,
                "status": self.agent_core.tool_broker.browser.get_status(),
            }

        elif action == "browser_status":
            return self.agent_core.tool_broker.browser.get_status()

        elif action == "browser_navigate":
            url = payload.get("url", "https://chatgpt.com")
            return await self.agent_core.tool_broker.browser.navigate_async(url)

        elif action == "browser_inspect":
            return self.agent_core.tool_broker.browser.inspect_targets()

        elif action == "browser_discover":
            elements = await self.agent_core.tool_broker.browser.discover_elements_async()
            return {"count": len(elements), "elements": elements}

        elif action == "browser_reveal":
            selector = payload.get("selector", "")
            title = payload.get("title", "Target Element")
            return await self.agent_core.tool_broker.browser.highlight_target_async(selector, title)

        elif action == "browser_screenshot":
            data = await self.agent_core.tool_broker.browser.capture_screenshot_async()
            return {"screenshot_base64": data}

        elif action == "browser_action":
            selector = payload.get("selector", "")
            act = payload.get("action_type", "click")
            param = payload.get("param")
            return await self.agent_core.tool_broker.browser.dispatch_action_async(selector, act, param)

        elif action == "chat_send":
            query = payload.get("query", "")
            session_id = payload.get("session_id")
            if not session_id:
                new_session = self.state_store.create_chat_session(self.workspace_root, "New Chat")
                session_id = new_session["session_id"]
                try:
                    await self.chat_streamer.new_chat()
                except Exception:
                    pass
            else:
                self.state_store.ensure_chat_session(session_id, self.workspace_root)

            existing_messages = self.state_store.get_chat_messages(session_id)
            is_followup = len(existing_messages) > 1

            logger.info("Processing chat_send for session %s (is_followup=%s, query length %d)", session_id, is_followup, len(query))
            self.state_store.add_chat_message(session_id, "user", query)

            async def on_token(delta: str, full_text: str, is_done: bool) -> None:
                if self.connected_clients:
                    payload_json = json.dumps({
                        "type": "CHAT_STREAM",
                        "session_id": session_id,
                        "delta": delta,
                        "full_text": full_text,
                        "done": is_done,
                    })
                    websockets.broadcast(self.connected_clients, payload_json)

            async def on_tool_executed(tool_res: Dict[str, Any]) -> None:
                self.state_store.add_chat_message(session_id, "tool", "", tool_data=tool_res)
                if self.connected_clients:
                    tool_json = json.dumps({
                        "type": "TOOL_EXECUTED",
                        "session_id": session_id,
                        "tool": tool_res,
                    })
                    websockets.broadcast(self.connected_clients, tool_json)

            try:
                res = await self.chat_streamer.stream_chat(
                    query,
                    on_token=on_token,
                    on_tool_executed=on_tool_executed,
                    is_followup=is_followup,
                    session_id=session_id,
                )
            except Exception as e:
                logger.error("Chat streaming error: %s", e)
                err_msg = f"Agent generation error: {e}. Click 'NEW CHAT' to refresh session."
                if self.connected_clients:
                    websockets.broadcast(self.connected_clients, json.dumps({
                        "type": "CHAT_STREAM",
                        "session_id": session_id,
                        "delta": f"\n\n[{err_msg}]",
                        "full_text": f"[{err_msg}]",
                        "done": True,
                    }))
                self.state_store.add_chat_message(session_id, "assistant", f"[{err_msg}]")
                return {
                    "query": query,
                    "response": f"[{err_msg}]",
                    "session_id": session_id,
                    "error": str(e),
                }

            res["session_id"] = session_id
            clean_resp = res.get("response", "")
            self.state_store.add_chat_message(session_id, "assistant", clean_resp)
            return res

        elif action == "chat_new":
            title = payload.get("title", "New Chat")
            session = self.state_store.create_chat_session(self.workspace_root, title)
            await self.chat_streamer.new_chat()
            return session

        elif action == "llm_get_config":
            return self.chat_streamer.llm_config.to_dict(mask_secrets=True)

        elif action == "llm_set_config":
            api_key = payload.get("api_key")
            base_url = payload.get("base_url")
            model = payload.get("model")
            provider = payload.get("provider")
            cfg = self.chat_streamer.update_config(
                api_key=api_key,
                base_url=base_url,
                model=model,
                provider=provider,
            )
            # Synchronize with AgentCore adapter if applicable
            if isinstance(self.agent_core.llm_adapter, OpenAICompatibleAdapter):
                if api_key is not None:
                    self.agent_core.llm_adapter.api_key = api_key
                if model is not None:
                    self.agent_core.llm_adapter.model = model
                if base_url is not None:
                    self.agent_core.llm_adapter.endpoint_url = f"{base_url.rstrip('/')}/chat/completions"
            return cfg.to_dict(mask_secrets=True)

        # ----------------- Engineering Data Intelligence Actions -----------------

        elif action == "dataset_ingest":
            path = payload.get("path", "datasets/development_dataset.csv")
            full_path = self._resolve_dataset_path(path)
            info = self.agent_core.tool_broker.ingest_engine.ingest(full_path)
            self.state_store.register_dataset(
                dataset_id=info["dataset_id"],
                name=info["name"],
                file_path=info["file_path"],
                file_hash=info["file_hash"],
                row_count=info["row_count"],
                column_count=info["column_count"],
                format_type=info["format"],
                schema_dict={"columns": info["columns"]},
                provenance=info["provenance"],
            )
            return info

        elif action == "dataset_profile":
            path = payload.get("path", "datasets/development_dataset.csv")
            full_path = self._resolve_dataset_path(path)
            profile = self.agent_core.tool_broker.profiler.profile(full_path)
            try:
                ingest_info = self.agent_core.tool_broker.ingest_engine.ingest(full_path, copy_to_workspace=False)
                ds_id = ingest_info["dataset_id"]
                self.state_store.register_dataset(
                    dataset_id=ds_id,
                    name=ingest_info["name"],
                    file_path=ingest_info["file_path"],
                    file_hash=ingest_info["file_hash"],
                    row_count=ingest_info["row_count"],
                    column_count=ingest_info["column_count"],
                    format_type=ingest_info["format"],
                    schema_dict={"columns": ingest_info["columns"]},
                )
                self.state_store.save_data_profile(
                    profile_id=f"prof-{ds_id}",
                    dataset_id=ds_id,
                    profile=profile,
                )
            except Exception as e:
                logger.warning("Could not persist data profile: %s", e)
            return profile

        elif action in ("dataset_list", "list_datasets"):
            # Discover CSV datasets in datasets/ folder and workspace root
            available = []
            datasets_dir = os.path.join(self.workspace_root, "datasets")
            search_dirs = [datasets_dir, self.workspace_root]
            seen_paths = set()

            for sdir in search_dirs:
                if os.path.exists(sdir):
                    for fname in os.listdir(sdir):
                        if fname.endswith(".csv"):
                            fpath = os.path.join(sdir, fname)
                            if fpath in seen_paths:
                                continue
                            seen_paths.add(fpath)
                            size_b = os.path.getsize(fpath)
                            # Quick line count estimate
                            with open(fpath, "rb") as f:
                                line_count = sum(1 for _ in f) - 1
                            rel_path = os.path.relpath(fpath, self.workspace_root)
                            available.append({
                                "name": fname,
                                "path": rel_path,
                                "absolute_path": fpath,
                                "size_bytes": size_b,
                                "estimated_rows": max(0, line_count),
                            })
            return available

        elif action == "upload_dataset":
            # Handle uploaded CSV file content or local file import
            content = payload.get("content")
            src_path = payload.get("file_path") or payload.get("path")
            filename = payload.get("filename")

            datasets_dir = os.path.join(self.workspace_root, "datasets")
            os.makedirs(datasets_dir, exist_ok=True)

            if content is not None:
                safe_name = os.path.basename(filename) if filename else f"dataset_{int(time.time())}.csv"
                target_path = os.path.realpath(os.path.join(datasets_dir, safe_name))
                if os.path.commonpath([datasets_dir, target_path]) != datasets_dir:
                    raise ValueError(f"Path traversal rejected in dataset upload: '{filename}'")
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
            elif src_path:
                src_full = os.path.realpath(src_path)
                if not os.path.exists(src_full):
                    raise FileNotFoundError(f"Source dataset not found: {src_path}")
                safe_name = os.path.basename(filename) if filename else os.path.basename(src_full)
                target_path = os.path.realpath(os.path.join(datasets_dir, safe_name))
                if os.path.commonpath([datasets_dir, target_path]) != datasets_dir:
                    raise ValueError(f"Path traversal rejected in dataset upload: '{filename}'")
                import shutil
                if src_full != target_path:
                    shutil.copyfile(src_full, target_path)
            else:
                raise ValueError("upload_dataset requires either 'content' or 'file_path'")

            # Ingest and profile immediately
            info = self.agent_core.tool_broker.ingest_engine.ingest(target_path)
            profile = self.agent_core.tool_broker.profiler.profile(target_path)
            self.state_store.register_dataset(
                dataset_id=info["dataset_id"],
                name=info["name"],
                file_path=info["file_path"],
                file_hash=info["file_hash"],
                row_count=info["row_count"],
                column_count=info["column_count"],
                format_type=info["format"],
                schema_dict={"columns": info["columns"]},
                provenance=info["provenance"],
            )
            self.state_store.save_data_profile(f"prof-{info['dataset_id']}", info["dataset_id"], profile)

            return {
                "status": "UPLOADED",
                "dataset_id": info["dataset_id"],
                "name": info["name"],
                "path": os.path.relpath(target_path, self.workspace_root),
                "row_count": info["row_count"],
                "column_count": info["column_count"],
                "profile": profile,
            }

        elif action == "get_latest_analysis":
            latest = self.state_store.get_latest_analysis()
            if not latest:
                return {}
            an_id = latest["analysis_id"]
            anomalies = self.state_store.list_anomalies(an_id)
            visuals = self.state_store.list_visual_artifacts(an_id)
            report = self.state_store.get_report(an_id)

            latest.setdefault("anomalies_detected", len(anomalies))
            latest.setdefault("total_anomalies", len(anomalies))
            if "model_metrics" not in latest or not latest.get("model_metrics", {}).get("entities"):
                models = self.state_store.list_models_for_dataset(latest.get("dataset_id", ""))
                if models:
                    ent_dict = {m["model_id"].split("-")[-1].upper(): m.get("metrics", {}) for m in models}
                    latest["model_metrics"] = {"overall_r2": latest.get("model_r2", 0.0), "entities": ent_dict}
                    if not latest.get("entities"):
                        latest["entities"] = list(ent_dict.keys())

            if "row_count" not in latest and latest.get("dataset_id"):
                ds_info = self.state_store.get_dataset(latest["dataset_id"])
                if ds_info:
                    latest["row_count"] = ds_info.get("row_count")
                    latest["column_count"] = ds_info.get("column_count")
            if "data_health_score" not in latest and latest.get("dataset_id"):
                prof_info = self.state_store.get_data_profile(latest["dataset_id"])
                if prof_info:
                    latest["data_health_score"] = prof_info.get("data_health_score")

            return {
                "analysis": latest,
                "anomalies": anomalies,
                "visuals": visuals,
                "report": report,
            }

        elif action == "get_anomalies":
            analysis_id = payload.get("analysis_id")
            if not analysis_id:
                latest = self.state_store.get_latest_analysis()
                analysis_id = latest["analysis_id"] if latest else None
            if not analysis_id:
                return []
            equipment_id = payload.get("equipment_id")
            return self.state_store.list_anomalies(analysis_id, equipment_id)

        elif action == "get_anomaly_evidence":
            evidence_id = payload.get("evidence_id", "")
            return self.state_store.get_evidence(evidence_id) or {}

        elif action == "get_visual_artifacts":
            analysis_id = payload.get("analysis_id")
            if not analysis_id:
                latest = self.state_store.get_latest_analysis()
                analysis_id = latest["analysis_id"] if latest else None
            if not analysis_id:
                return []
            return self.state_store.list_visual_artifacts(analysis_id)

        elif action == "get_report":
            analysis_id = payload.get("analysis_id")
            if not analysis_id:
                latest = self.state_store.get_latest_analysis()
                analysis_id = latest["analysis_id"] if latest else None
            if not analysis_id:
                return {}
            return self.state_store.get_report(analysis_id) or {}

        elif action in ("record_decision", "update_anomaly_status"):
            anomaly_id = payload.get("anomaly_id", "")
            decision = payload.get("decision") or payload.get("status", "CONFIRMED")
            success = self.state_store.update_anomaly_status(anomaly_id, decision)
            return {"success": success, "anomaly_id": anomaly_id, "status": decision}

        elif action in ("run_analysis_pipeline", "run_demo_pipeline"):
            # Universal end-to-end engineering pipeline execution with real calculations
            raw_path = payload.get("path") or payload.get("file_path") or payload.get("dataset_name", "datasets/development_dataset.csv")
            full_path = self._resolve_dataset_path(raw_path)
            analysis_id = payload.get("analysis_id") or f"an-{uuid.uuid4().hex[:8]}"

            def _broadcast_stage(stage_name: str, message: str, progress: float) -> None:
                if self.connected_clients:
                    websockets.broadcast(
                        self.connected_clients,
                        json.dumps({
                            "type": "DATA_PIPELINE_STAGE",
                            "stage": stage_name,
                            "message": message,
                            "progress": progress,
                            "analysis_id": analysis_id,
                        }),
                    )

            # Stage 1: Ingestion & Fingerprinting
            _broadcast_stage("INGESTION", "Ingesting and hashing dataset...", 0.1)
            ingest_info = self.agent_core.tool_broker.ingest_engine.ingest(full_path, copy_to_workspace=False)
            ds_id = ingest_info["dataset_id"]
            self.state_store.register_dataset(
                dataset_id=ds_id,
                name=ingest_info["name"],
                file_path=ingest_info["file_path"],
                file_hash=ingest_info["file_hash"],
                row_count=ingest_info["row_count"],
                column_count=ingest_info["column_count"],
                format_type=ingest_info["format"],
                schema_dict={"columns": ingest_info["columns"]},
            )

            # Stage 2: Profiling & Dynamic Role Inference
            _broadcast_stage("PROFILING", "Profiling schema, sampling regularity, and variable roles...", 0.2)
            profile = self.agent_core.tool_broker.profiler.profile(full_path)
            self.state_store.save_data_profile(f"prof-{ds_id}", ds_id, profile)

            time_col = payload.get("time_column") or profile.get("primary_time_column") or "timestamp"
            entity_col = payload.get("entity_column") or profile.get("primary_entity_column")
            target_col = payload.get("target_column") or profile.get("primary_target_column") or "Chiller Energy Consumption (kWh)"
            load_col = payload.get("load_column") or profile.get("primary_load_column")

            # Stage 3: Preparation & Outage Segmentation
            _broadcast_stage("PREPARATION", "Chronological sorting and gap segmentation (preventing leakage)...", 0.35)
            import pandas as pd
            raw_df = pd.read_csv(full_path)
            clean_df, prep_report = self.agent_core.tool_broker.preparator.prepare(
                raw_df, time_column=time_col, entity_column=entity_col
            )

            # Stage 4: Feature Engineering
            _broadcast_stage("FEATURE_ENGINEERING", "Generating sinusoidal cyclics, kW/RT ratios, and rolling stats...", 0.5)
            feat_df, feat_manifest = self.agent_core.tool_broker.feature_engine.build_features(
                clean_df, target_col=target_col, load_col=load_col, entity_col=entity_col
            )

            # Stage 5: Expected-Behaviour Model Fitting (ASHRAE Guideline 14)
            _broadcast_stage("ML_BASELINE", "Fitting contextual Ridge expected-energy regression models...", 0.65)
            # Gather numerical feature columns excluding target
            numeric_cols = feat_df.select_dtypes(include=[np.number]).columns.tolist()
            exclude_set = {target_col, "_segment_id", "feat_hour", "feat_dayofweek", "feat_month"}
            feature_cols = [c for c in numeric_cols if c not in exclude_set and not c.startswith("_res")]

            model_rec = self.agent_core.tool_broker.ml_engine.fit_expected_behaviour_model(
                feat_df, target_col=target_col, feature_cols=feature_cols, entity_col=entity_col
            )
            self.state_store.record_model(
                model_id=model_rec["model_id"],
                dataset_id=ds_id,
                model_type="RidgeContextualRegression",
                target_column=target_col,
                metrics={
                    "overall_r2": model_rec["overall_r2"],
                    "entities": {k: {"r2": v["r2"], "rmse": v["rmse"], "cv_rmse": v.get("cv_rmse"), "nmbe": v.get("nmbe"), "ashrae_compliant": v.get("ashrae_compliant", True)} for k, v in model_rec["entities"].items()},
                },
                parameters={"alpha": model_rec["alpha"], "feature_cols": feature_cols},
            )

            # Stage 6: Anomaly Detection & Persistence Clustering
            _broadcast_stage("ANOMALY_DETECTION", "Computing contextual residuals, z-scores, and persistence clustering...", 0.8)
            preds = self.agent_core.tool_broker.ml_engine.predict_expected(feat_df, model_rec)
            res, z, stats = self.agent_core.tool_broker.ml_engine.compute_contextual_residuals(
                feat_df, target_col, preds, entity_col
            )
            multi = self.agent_core.tool_broker.ml_engine.compute_multivariate_scores(
                feat_df, [c for c in feature_cols if not c.startswith("feat_")][:6]
            )
            feat_df["_expected"] = preds
            feat_df["_res"] = res
            feat_df["_z"] = z
            feat_df["_multi"] = multi

            anomalies = self.agent_core.tool_broker.ml_engine.find_persistent_anomaly_windows(
                feat_df, res, z, multi, preds, target_col, entity_col or "_entity", time_col, min_persistence=3
            )

            # Record entity models in state store
            for ent_name, ent_m in model_rec["entities"].items():
                self.state_store.record_model(
                    model_id=f"mod-{analysis_id}-{ent_name.lower()}",
                    dataset_id=ds_id,
                    model_type="OLS_REGRESSION",
                    target_column=target_col,
                    metrics=ent_m,
                    parameters={"weights": ent_m.get("weights", [])},
                )

            analysis_meta = {
                "dataset_name": ingest_info["name"],
                "row_count": ingest_info["row_count"],
                "column_count": ingest_info["column_count"],
                "data_health_score": profile.get("data_health_score", 100.0),
                "model_r2": model_rec["overall_r2"],
                "entities": list(model_rec["entities"].keys()),
                "model_metrics": {
                    "overall_r2": model_rec["overall_r2"],
                    "entities": model_rec["entities"],
                },
                "anomalies_detected": len(anomalies),
                "total_anomalies": len(anomalies),
            }

            # Record analysis in state store
            self.state_store.record_analysis(
                analysis_id=analysis_id,
                project_id="proj-default",
                dataset_id=ds_id,
                objective="YUKTHI 2026 Contextual Energy & Equipment Monitoring",
                status="COMPLETED",
                phase="REPORT",
                plan={"pipeline_meta": analysis_meta, "steps": [{"phase": "ML_ANALYSIS", "status": "DONE"}]},
                summary=f"Discovered {len(anomalies)} persistent anomaly episodes across {len(model_rec['entities'])} equipment units.",
            )

            # Stage 7: Evidence Critic & Storage
            _broadcast_stage("CRITIC_VERIFICATION", "Validating telemetry boundaries and storing evidence objects...", 0.9)
            for anom in anomalies:
                ev = anom["evidence"]
                crit_res = self.agent_core.tool_broker.critic.validate_claim(anom["interpretation"], ev)
                anom["interpretation"] = crit_res["validated_claim"]

                self.state_store.record_evidence(
                    evidence_id=ev["evidence_id"],
                    anomaly_id=anom["anomaly_id"],
                    observations=ev["observations"],
                    source_refs=ev["source_refs"],
                    metrics=ev["metrics"],
                )
                self.state_store.record_anomaly(
                    anomaly_id=anom["anomaly_id"],
                    analysis_id=analysis_id,
                    equipment_id=anom["equipment_id"],
                    start_time=anom["start_time"],
                    end_time=anom["end_time"],
                    severity=anom["severity"],
                    persistence_count=anom["persistence_count"],
                    residual_score=anom["residual_score"],
                    multivariate_score=anom["multivariate_score"],
                    confidence=anom["confidence"],
                    status=anom["status"],
                    interpretation=anom["interpretation"],
                    evidence_id=anom["evidence_id"],
                    peak_z_score=anom.get("peak_z_score", 0.0),
                )

            # Stage 8: Visual Intelligence & Reporting (White Theme)
            _broadcast_stage("VISUALS_AND_REPORT", "Rendering publication-grade charts and engineering report...", 0.95)

            # Render charts for each entity discovered in dataset
            entities_to_plot = list(model_rec["entities"].keys())
            for ent_name in entities_to_plot:
                safe_ent = ent_name if ent_name != "GLOBAL" else "FLEET"
                c1 = self.agent_core.tool_broker.visual_engine.plot_observed_vs_expected(
                    feat_df, safe_ent, target_col, "_expected", entity_col=entity_col
                )
                self.state_store.record_visual_artifact(
                    f"vis-{analysis_id}-obs-{safe_ent.lower()}", analysis_id, "observed_vs_expected",
                    f"{safe_ent} — Observed vs Contextual Baseline", c1
                )

                c2 = self.agent_core.tool_broker.visual_engine.plot_residuals(
                    feat_df, safe_ent, "_res", "_z", entity_col=entity_col
                )
                self.state_store.record_visual_artifact(
                    f"vis-{analysis_id}-res-{safe_ent.lower()}", analysis_id, "residuals",
                    f"{safe_ent} — Contextual Residual Envelope", c2
                )

            # Render schematic
            schematic = self.agent_core.tool_broker.visual_engine.plot_chiller_schematic()
            self.state_store.record_visual_artifact(
                f"vis-{analysis_id}-schematic", analysis_id, "schematic",
                "Physical HVAC Chiller Flow & Instrumentation Schematic", schematic
            )

            # Render anomaly zoom into top critical anomaly
            if anomalies:
                top_anom = anomalies[0]
                c_zoom = self.agent_core.tool_broker.visual_engine.plot_anomaly_zoom(
                    feat_df, top_anom, target_col, "_expected", load_col, entity_col=entity_col
                )
                self.state_store.record_visual_artifact(
                    f"vis-{analysis_id}-zoom-top", analysis_id, "anomaly_zoom",
                    f"Episode Zoom: {top_anom['equipment_id']} ({top_anom['severity']})", c_zoom
                )

            visuals = self.state_store.list_visual_artifacts(analysis_id)

            report_info = self.agent_core.tool_broker.report_engine.generate_report(
                analysis_id=analysis_id,
                dataset_name=ingest_info["name"],
                dataset_profile=profile,
                model_metrics={
                    "overall_r2": model_rec["overall_r2"],
                    "entities": model_rec["entities"],
                },
                anomalies=anomalies,
                visual_artifacts=visuals,
            )
            self.state_store.save_report(
                report_id=report_info["report_id"],
                analysis_id=analysis_id,
                title=report_info["title"],
                content_markdown=report_info["content_markdown"],
                file_path=report_info["file_path"],
            )

            _broadcast_stage("COMPLETED", "Analysis pipeline completed successfully!", 1.0)

            return {
                "status": "COMPLETED",
                "analysis_id": analysis_id,
                "dataset_id": ds_id,
                "dataset_name": ingest_info["name"],
                "row_count": ingest_info["row_count"],
                "column_count": ingest_info["column_count"],
                "data_health_score": profile.get("data_health_score"),
                "model_r2": model_rec["overall_r2"],
                "entities": list(model_rec["entities"].keys()),
                "model_metrics": model_rec["entities"],
                "anomalies_detected": len(anomalies),
                "total_anomalies": len(anomalies),
                "visual_artifacts_count": len(visuals),
                "report_id": report_info["report_id"],
                "report_path": report_info["file_path"],
            }

        elif action == "get_anomaly_audit":
            # Multi-layer raw-data anomaly audit (plateaus, spikes, cross-entity, physical, energy)
            raw_path = payload.get("path") or payload.get("dataset_name") or ""
            full_path = self._resolve_dataset_path(raw_path)
            auditor = getattr(self.agent_core.tool_broker, "anomaly_auditor", None)
            if auditor is None:
                try:
                    from agent.data_engine.anomaly_auditor import AnomalyAuditor
                except ImportError:
                    from voide.agent.data_engine.anomaly_auditor import AnomalyAuditor
                auditor = AnomalyAuditor()
            return auditor.audit(full_path)

        else:
            raise ValueError(f"Unknown IPC action: {action}")



    async def start(self) -> None:
        """Start IPC server listening on WebSocket interface."""
        logger.info("Starting V.O.I.D.E. IPC Server on ws://%s:%d (workspace: %s)", self.host, self.port, self.workspace_root)
        await self.event_engine.start()

        async with websockets.serve(self.handle_client, self.host, self.port, ping_interval=None):
            logger.info("IPC Server listening on ws://%s:%d", self.host, self.port)
            await asyncio.Future()  # Run forever


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("V.O.I.D.E. IPC Daemon")
        print("Usage: python3 -m agent.runtime.ipc_server [workspace_root]")
        print("Environment variables:")
        print("  VOIDE_IPC_PORT   WebSocket port (default: 8766)")
        print("  OPENAI_API_KEY   API Key for OpenAI/OpenRouter/custom LLM")
        print("  OPENAI_BASE_URL  Base endpoint (default: https://api.openai.com/v1)")
        print("  OPENAI_MODEL     Model name (default: gpt-4o)")
        sys.exit(0)

    workspace = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    server = IPCServer(workspace_root=workspace)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
