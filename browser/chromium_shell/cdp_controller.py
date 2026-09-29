"""Chromium Shell & Chrome DevTools Protocol (CDP) Controller for V.O.I.D.E.

Implements on-device DOM intelligence, live element discovery, visual reveal overlays,
prototype value setter dispatch, and screenshot telemetry ported from Alex Browser v2.
"""

from __future__ import annotations
import json
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
import logging
from typing import Any, Dict, List, Optional
import websockets
import asyncio

logger = logging.getLogger("voide.cdp")

try:
    from voide.browser.dom_intelligence.semantic_resolver import (
        SemanticResolver,
        ScoredCandidate,
        ConfidenceBand,
        MappingHealthStatus,
    )
    from voide.browser.dom_intelligence.dom_scripts import (
        DOM_DISCOVERY_SCRIPT,
        build_action_script,
        build_highlight_script,
    )
except ImportError:
    # Direct script invocation — inject the repo root so relative imports resolve
    import sys as _sys
    import os as _os
    _repo = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", ".."))
    if _repo not in _sys.path:
        _sys.path.insert(0, _repo)
    from voide.browser.dom_intelligence.semantic_resolver import (  # type: ignore[no-redef]
        SemanticResolver,
        ScoredCandidate,
        ConfidenceBand,
        MappingHealthStatus,
    )
    from voide.browser.dom_intelligence.dom_scripts import (  # type: ignore[no-redef]
        DOM_DISCOVERY_SCRIPT,
        build_action_script,
        build_highlight_script,
    )


class CDPController:
    """Controls Chromium via standard Chrome DevTools Protocol with persistent session profile."""

    def __init__(
        self,
        port: int = 9222,
        headless: bool = True,
        profile_dir: Optional[str] = None,
    ) -> None:
        self.port: int = port
        self.headless: bool = headless
        self.profile_dir: str = profile_dir or os.path.expanduser("~/.config/voide/chromium_profile")
        os.makedirs(self.profile_dir, exist_ok=True)
        self.process: Optional[subprocess.Popen] = None
        self.ws_url: Optional[str] = None
        self.resolver: SemanticResolver = SemanticResolver()
        self.mapping_version: int = 1
        self.last_synced_mutation_version: int = 1
        self.cached_elements: List[Dict[str, Any]] = []
        self.active_url: str = "about:blank"
        self.active_title: str = "Browser Viewport"
        self.is_currently_headless: bool = self.headless

    def clean_stale_singleton_lock(self) -> None:
        """Unlink dead SingletonLock to prevent Chrome startup hangs if previous process died."""
        lock_path = os.path.join(self.profile_dir, "SingletonLock")
        if os.path.islink(lock_path) or os.path.exists(lock_path):
            try:
                target = os.readlink(lock_path) if os.path.islink(lock_path) else ""
                parts = target.split("-")
                pid = int(parts[-1]) if parts and parts[-1].isdigit() else None
                pid_running = False
                if pid:
                    try:
                        os.kill(pid, 0)
                        pid_running = True
                    except OSError:
                        pid_running = False
                if not pid_running:
                    try:
                        os.unlink(lock_path)
                    except Exception:
                        pass
                    sock_path = os.path.join(self.profile_dir, "SingletonSocket")
                    if os.path.islink(sock_path) or os.path.exists(sock_path):
                        try:
                            os.unlink(sock_path)
                        except Exception:
                            pass
            except Exception:
                pass

    def find_browser_binary(self) -> Optional[str]:
        """Locate Google Chrome or Chromium executable on Linux."""
        candidates = [
            "/opt/google/chrome/chrome",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
        ]
        for c in candidates:
            if c and os.path.exists(c) and os.access(c, os.X_OK):
                return c
        return None

    def get_chrome_x11_window_ids(self) -> List[str]:
        """Find all X11 window IDs belonging to our Chrome process."""
        win_ids = set()
        try:
            pid = self.process.pid if self.process else None
            out = subprocess.check_output(["wmctrl", "-l", "-p"], stderr=subprocess.DEVNULL).decode("utf-8")
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    wid, wpid = parts[0], parts[2]
                    if pid and wpid == str(pid):
                        win_ids.add(wid)
                    elif "Google Chrome" in line or "Chromium" in line or "google-chrome" in line:
                        win_ids.add(wid)
        except Exception:
            pass

        try:
            out2 = subprocess.check_output(["xdotool", "search", "--class", "google-chrome"], stderr=subprocess.DEVNULL).decode("utf-8")
            for line in out2.splitlines():
                if line.strip():
                    win_ids.add(line.strip())
        except Exception:
            pass

        return list(win_ids)

    def set_window_visibility(self, visible: bool) -> bool:
        """Dynamically toggle browser window between visible (mapped on-screen) and invisible (unmapped offscreen)."""
        self.is_currently_headless = not visible

        # 1. Toggle X11 window mapping
        win_ids = self.get_chrome_x11_window_ids()
        for wid in win_ids:
            try:
                if visible:
                    subprocess.run(["xdotool", "windowmap", wid], check=False)
                    subprocess.run(["xdotool", "windowactivate", wid], check=False)
                else:
                    subprocess.run(["xdotool", "windowunmap", wid], check=False)
            except Exception:
                pass

        # 2. Also toggle CDP window bounds
        try:
            tab = self.get_active_tab()
            target_id = tab.get("id") or tab.get("targetId") if tab else None
            if target_id:
                req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/version")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    bws = data.get("webSocketDebuggerUrl")
                if bws:
                    async def _toggle() -> None:
                        async with websockets.connect(bws, close_timeout=1.5) as ws:
                            mid = int(time.time() * 1000) % 1000000
                            await ws.send(json.dumps({"id": mid, "method": "Browser.getWindowForTarget", "params": {"targetId": target_id}}))
                            win_id = None
                            async for raw in ws:
                                resp1 = json.loads(raw)
                                if resp1.get("id") == mid:
                                    win_id = resp1.get("result", {}).get("windowId")
                                    break
                            if win_id:
                                mid2 = mid + 1
                                bounds = {
                                    "left": 100 if visible else -10000,
                                    "top": 100 if visible else -10000,
                                    "width": 1280,
                                    "height": 900,
                                    "windowState": "normal",
                                }
                                await ws.send(json.dumps({"id": mid2, "method": "Browser.setWindowBounds", "params": {"windowId": win_id, "bounds": bounds}}))
                                async for _ in ws:
                                    break
                    try:
                        cur_loop = asyncio.get_running_loop()
                    except RuntimeError:
                        cur_loop = None

                    if cur_loop and cur_loop.is_running():
                        cur_loop.create_task(_toggle())
                    else:
                        loop = asyncio.new_event_loop()
                        try:
                            loop.run_until_complete(_toggle())
                        finally:
                            loop.close()
        except Exception:
            pass

        return True

    def start_browser(self, initial_url: str = "about:blank", force_non_headless: bool = False) -> bool:
        """Launch Chrome with remote debugging enabled and persistent user session.
        Defaults to headless/invisible offscreen execution. Visible window only opens on manual user request.
        """
        if self.is_cdp_available():
            if force_non_headless:
                self.set_window_visibility(True)
            elif getattr(self, "is_currently_headless", True):
                self.set_window_visibility(False)

            if initial_url and initial_url != "about:blank":
                tabs = self.get_tabs()
                page_tabs = [t for t in tabs if t.get("type") == "page"]
                has_url = any(initial_url in t.get("url", "") for t in page_tabs)
                if not has_url:
                    self.navigate(initial_url)
            return True

        self.clean_stale_singleton_lock()

        chrome_binary = self.find_browser_binary()
        if not chrome_binary:
            return False

        use_headless = False if force_non_headless else self.headless
        self.is_currently_headless = use_headless

        cmd = [
            chrome_binary,
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            initial_url,
        ]
        if use_headless:
            # Moving a window off-screen is not headless mode.  In particular, it
            # still requires an X/Wayland display and Chrome exits before exposing
            # its CDP port on desktop-less hosts.
            cmd.extend([
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--window-size=1280,900",
            ])
        else:
            cmd.extend(["--window-position=100,100", "--window-size=1280,900"])

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            for _ in range(50):
                time.sleep(0.2)
                if self.is_cdp_available():
                    self.active_url = initial_url
                    return True
                # Do not wait the full startup timeout when Chrome has already
                # failed (for example a corrupt profile or unavailable binary).
                if self.process.poll() is not None:
                    logger.error("Chrome exited before CDP was available (exit code %s)", self.process.returncode)
                    self.process = None
                    return False
        except Exception as exc:
            logger.exception("Unable to launch Chrome CDP: %s", exc)
            self.process = None
            return False

        available = self.is_cdp_available()
        if not available and self.process and self.process.poll() is not None:
            logger.error("Chrome exited before CDP was available (exit code %s)", self.process.returncode)
            self.process = None
        return available

    def is_cdp_available(self) -> bool:
        """Check if CDP endpoint is responding."""
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/version")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.ws_url = data.get("webSocketDebuggerUrl")
                return True
        except Exception:
            return False

    def get_tabs(self) -> List[Dict[str, Any]]:
        """Retrieve list of open browser tabs from CDP."""
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/list")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                tabs = json.loads(resp.read().decode("utf-8"))
                return tabs
        except Exception:
            return []

    def get_active_tab(self) -> Optional[Dict[str, Any]]:
        """Locate active browser page tab or primary browser page tab."""
        tabs = self.get_tabs()
        page_tabs = [t for t in tabs if t.get("type") == "page"]
        return page_tabs[0] if page_tabs else None

    def get_chatgpt_tab(self) -> Optional[Dict[str, Any]]:
        """Backwards-compatible alias for get_active_tab."""
        return self.get_active_tab()

    async def _send_cdp_command(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute raw command over active page WebSocket debugger URL."""
        page_tab = self.get_active_tab()
        if not page_tab or "webSocketDebuggerUrl" not in page_tab:
            return {"error": "NO_PAGE_TARGET"}

        ws_url = page_tab["webSocketDebuggerUrl"]
        msg_id = int(time.time() * 1000) % 1000000

        try:
            async with websockets.connect(ws_url, close_timeout=2.0) as ws:
                await ws.send(json.dumps({
                    "id": msg_id,
                    "method": method,
                    "params": params or {},
                }))
                # Wait for response with matching id
                async with asyncio.timeout(3.0):
                    async for raw in ws:
                        resp = json.loads(raw)
                        if resp.get("id") == msg_id:
                            return resp.get("result", {})
        except Exception as e:
            return {"error": str(e)}

        return {}

    def _run_sync(self, coro: Any) -> Any:
        """Safely execute coroutine synchronously whether in thread or existing event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(lambda: asyncio.run(coro)).result()
        else:
            return asyncio.run(coro)

    async def execute_script_async(self, script: str) -> Any:
        """Asynchronously evaluate JavaScript in active page."""
        try:
            res = await self._send_cdp_command("Runtime.evaluate", {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": True,
            })
            if isinstance(res, dict) and "result" in res:
                result_obj = res["result"]
                if "value" in result_obj:
                    val = result_obj["value"]
                    if isinstance(val, str):
                        try:
                            return json.loads(val)
                        except Exception:
                            return val
                    return val
            return res
        except Exception as e:
            return {"error": str(e)}

    def execute_script(self, script: str) -> Any:
        """Synchronously evaluate JavaScript in active page."""
        return self._run_sync(self.execute_script_async(script))

    async def capture_screenshot_async(self) -> Optional[str]:
        """Asynchronously capture live base64 PNG screenshot of active tab viewport."""
        try:
            res = await self._send_cdp_command("Page.captureScreenshot", {"format": "png"})
            return res.get("data")
        except Exception:
            return None

    def capture_screenshot(self) -> Optional[str]:
        """Capture live base64 PNG screenshot of active tab viewport."""
        return self._run_sync(self.capture_screenshot_async())

    def get_observer_script(self) -> str:
        """Load the in-page DOM mutation observer bridge script."""
        js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "js_bridge", "observer_bridge.js")
        if os.path.exists(js_path):
            with open(js_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    async def inject_observer_bridge_async(self) -> bool:
        """Inject DOM MutationObserver bridge into current page and register on new documents."""
        script = self.get_observer_script()
        if not script:
            return False
        try:
            # Register to evaluate automatically on any subsequent navigations
            await self._send_cdp_command("Page.addScriptToEvaluateOnNewDocument", {"source": script})
            # Also evaluate in currently active page
            await self.execute_script_async(script)
            return True
        except Exception:
            return False

    async def check_and_sync_mutations_async(self) -> bool:
        """Check if mutation observer detected structural DOM changes and remap elements if so."""
        try:
            ver = await self.execute_script_async(
                "(() => (window.__voide_bridge ? window.__voide_bridge.getVersion() : null))()"
            )
            if isinstance(ver, (int, float)) and int(ver) > self.last_synced_mutation_version:
                self.last_synced_mutation_version = int(ver)
                await self.discover_elements_async()
                return True
        except Exception:
            pass
        return False

    async def discover_elements_async(self) -> List[Dict[str, Any]]:
        """Asynchronously run DOM Discovery Engine script live in page with mutation observer active."""
        if not self.is_cdp_available():
            return self.cached_elements

        # Ensure mutation observer bridge is active in the document
        await self.inject_observer_bridge_async()

        resp = await self.execute_script_async(DOM_DISCOVERY_SCRIPT)
        if isinstance(resp, dict) and resp.get("success") and "elements" in resp:
            self.cached_elements = resp["elements"]
            self.mapping_version += 1
            return self.cached_elements
        return self.cached_elements

    def discover_elements(self) -> List[Dict[str, Any]]:
        """Run DOM Discovery Engine script live in page."""
        return self._run_sync(self.discover_elements_async())

    def get_resolved_target(self, semantic_role: str) -> Optional[ScoredCandidate]:
        """Resolve semantic target role against cached elements using 8-signal resolver."""
        if not self.cached_elements:
            self.discover_elements()
        return self.resolver.resolve(self.cached_elements, semantic_role)

    def get_target_selector(self, semantic_role: str) -> Optional[str]:
        """Get best resilient CSS selector for resolved semantic target."""
        candidate = self.get_resolved_target(semantic_role)
        if not candidate:
            return None
        el = candidate.element
        selectors = el.get("selectors", {})
        if selectors.get("css"):
            return selectors["css"]
        if el.get("id"):
            return f"#{el['id']}"
        if el.get("css_selector"):
            return el["css_selector"]
        tag = el.get("tag") or "div"
        if el.get("role"):
            return f"{tag}[role='{el['role']}']"
        return tag

    async def highlight_target_async(self, selector: str, title: str) -> Dict[str, Any]:
        """Asynchronously display non-destructive pulsing visual reveal overlay in live browser."""
        script = build_highlight_script(selector, title)
        return await self.execute_script_async(script)

    def highlight_target(self, selector: str, title: str) -> Dict[str, Any]:
        """Display non-destructive pulsing visual reveal overlay in live browser."""
        return self._run_sync(self.highlight_target_async(selector, title))

    async def dispatch_action_async(self, selector: str, action: str, param: Optional[str] = None) -> Dict[str, Any]:
        """Asynchronously dispatch action through safe prototype value setter."""
        script = build_action_script(selector, action, param)
        return await self.execute_script_async(script)

    async def insert_text_async(self, text: str) -> Dict[str, Any]:
        """Insert text natively via CDP Input.insertText."""
        return await self._send_cdp_command("Input.insertText", {"text": text})

    async def click_at_async(self, x: float, y: float) -> Dict[str, Any]:
        """Dispatch native mouse click at coordinate (x, y) via CDP Input.dispatchMouseEvent atomically."""
        page_tab = self.get_active_tab()
        if not page_tab or "webSocketDebuggerUrl" not in page_tab:
            return {"error": "NO_PAGE_TARGET"}

        ws_url = page_tab["webSocketDebuggerUrl"]
        try:
            async with websockets.connect(ws_url, close_timeout=2.0) as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Input.dispatchMouseEvent",
                    "params": {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}
                }))
                await ws.recv()
                await ws.send(json.dumps({
                    "id": 2,
                    "method": "Input.dispatchMouseEvent",
                    "params": {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}
                }))
                return json.loads(await ws.recv())
        except Exception as e:
            return {"error": str(e)}

    def dispatch_action(self, selector: str, action: str, param: Optional[str] = None) -> Dict[str, Any]:
        """Dispatch action through safe prototype value setter."""
        return self._run_sync(self.dispatch_action_async(selector, action, param))

    def get_status(self) -> Dict[str, Any]:
        """Return authoritative browser, CDP, and session state."""
        connected = self.is_cdp_available()
        tabs = self.get_tabs() if connected else []
        page_tab = next((t for t in tabs if t.get("type") == "page"), None)
        
        if page_tab:
            self.active_url = page_tab.get("url", self.active_url)
            self.active_title = page_tab.get("title", self.active_title)

        return {
            "connected": connected,
            "port": self.port,
            "profile_dir": self.profile_dir,
            "active_url": self.active_url,
            "active_title": self.active_title,
            "tab_count": len([t for t in tabs if t.get("type") == "page"]),
            "mapping_version": self.mapping_version,
            "cached_elements_count": len(self.cached_elements),
        }

    async def navigate_async(self, url: str) -> Dict[str, Any]:
        """Navigate active tab or launch browser to target URL."""
        self.active_url = url
        self.mapping_version += 1
        
        if not self.is_cdp_available():
            self.start_browser(initial_url=url)
        else:
            try:
                await self._send_cdp_command("Page.navigate", {"url": url})
            except Exception:
                pass

        return {
            "status": "success",
            "url": url,
            "mapping_version": self.mapping_version,
            "timestamp": time.time(),
        }

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate active tab or launch browser to target URL."""
        return self._run_sync(self.navigate_async(url))

    def inspect_targets(self) -> Dict[str, Any]:
        """Query 8-signal semantic resolver against cached elements."""
        targets = ["MESSAGE_INPUT", "SEND_BUTTON", "STOP_BUTTON", "REGENERATE_BUTTON"]
        results: Dict[str, Any] = {}
        for t in targets:
            candidate = self.resolver.resolve(self.cached_elements, t)
            if candidate:
                results[t] = candidate.to_dict()
            else:
                results[t] = {
                    "resolved": False,
                    "confidence_band": ConfidenceBand.UNRESOLVED,
                    "score": 0.0,
                    "health": MappingHealthStatus.DEGRADED,
                    "explanation": "No candidate element satisfied minimum confidence threshold",
                }
        return {
            "mapping_version": self.mapping_version,
            "targets": results,
            "total_elements": len(self.cached_elements),
        }

    def resolve_target(self, semantic_role: str) -> Optional[ScoredCandidate]:
        return self.resolver.resolve(self.cached_elements, semantic_role)

    def simulate_click(self, semantic_role: str) -> Dict[str, Any]:
        candidate = self.resolve_target(semantic_role)
        if not candidate:
            return {
                "status": "failure",
                "error": f"Semantic target '{semantic_role}' could not be resolved",
            }

        selector = candidate.element.get("selectors", {}).get("css") or f"#{candidate.element.get('id', '')}"
        action_res = self.dispatch_action(selector, "click")

        return {
            "status": "success" if action_res.get("success") else "failure",
            "target": semantic_role,
            "selector": selector,
            "confidence": candidate.score,
            "confidence_band": candidate.confidence_band,
            "action_res": action_res,
            "action_verified": action_res.get("success", False),
        }

    def simulate_type(self, semantic_role: str, text: str) -> Dict[str, Any]:
        candidate = self.resolve_target(semantic_role)
        if not candidate:
            return {
                "status": "failure",
                "error": f"Semantic target '{semantic_role}' could not be resolved",
            }

        selector = candidate.element.get("selectors", {}).get("css") or f"#{candidate.element.get('id', '')}"
        action_res = self.dispatch_action(selector, "type", text)

        return {
            "status": "success" if action_res.get("success") else "failure",
            "target": semantic_role,
            "selector": selector,
            "confidence": candidate.score,
            "confidence_band": candidate.confidence_band,
            "action_res": action_res,
            "action_verified": action_res.get("success", False),
        }

    def close(self) -> None:
        """Terminate Chrome process and all sub-processes if spawned by controller."""
        if self.process:
            try:
                import signal
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                try:
                    self.process.terminate()
                except Exception:
                    pass
            try:
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    import signal
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except Exception:
                    self.process.kill()
            self.process = None
