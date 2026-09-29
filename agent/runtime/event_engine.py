"""Event & Trigger Engine for V.O.I.D.E.

Implements event-driven agent wakeups, timer triggers, and external observation
dispatching without wasteful polling loops.
"""

from __future__ import annotations
import asyncio
import time
import uuid
from typing import Any, Callable, Dict, List, Optional


class EventPriority:
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventEnvelope:
    """Structured envelope for all system, process, file, and browser events."""

    def __init__(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
        task_id: Optional[str] = None,
        priority: str = EventPriority.NORMAL,
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        self.event_id: str = event_id or f"evt-{int(time.time()*1000)}-{uuid.uuid4().hex[:4]}"
        self.event_type: str = event_type
        self.source: str = source
        self.data: Dict[str, Any] = data
        self.task_id: Optional[str] = task_id
        self.priority: str = priority
        self.correlation_id: Optional[str] = correlation_id
        self.timestamp: float = timestamp or time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "data": self.data,
            "task_id": self.task_id,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }


class TimerRule:
    """Configurable timer for scheduled checks, deadlines, or delayed wakeups."""

    def __init__(
        self,
        timer_id: str,
        task_id: str,
        delay_seconds: float,
        action: str = "WAKE_AGENT",
        recurrence_seconds: Optional[float] = None,
        condition: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.timer_id: str = timer_id
        self.task_id: str = task_id
        self.due_at: float = time.time() + delay_seconds
        self.action: str = action
        self.recurrence_seconds: Optional[float] = recurrence_seconds
        self.condition: Optional[Callable[[], bool]] = condition
        self.is_cancelled: bool = False


class EventEngine:
    """Coordinates event queues, listeners, and timer loops."""

    def __init__(self) -> None:
        self.subscribers: Dict[str, List[Callable[[EventEnvelope], None]]] = {}
        self.timers: Dict[str, TimerRule] = {}
        self._event_queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._timer_task: Optional[asyncio.Task] = None

    def subscribe(self, event_type: str, callback: Callable[[EventEnvelope], None]) -> None:
        """Register a callback for a specific event type, or '*' for all."""
        self.subscribers.setdefault(event_type, []).append(callback)

    def emit(self, envelope: EventEnvelope) -> None:
        """Publish an event synchronously to listeners and enqueue for async processors."""
        # Synchronous callback invocation
        for callback in self.subscribers.get(envelope.event_type, []):
            try:
                callback(envelope)
            except Exception:
                pass
        for callback in self.subscribers.get("*", []):
            try:
                callback(envelope)
            except Exception:
                pass
        try:
            self._event_queue.put_nowait(envelope)
        except Exception:
            pass

    def schedule_timer(
        self,
        task_id: str,
        delay_seconds: float,
        action: str = "WAKE_AGENT",
        recurrence: Optional[float] = None,
    ) -> str:
        """Schedule a timer rule."""
        timer_id = f"tmr-{uuid.uuid4().hex[:6]}"
        rule = TimerRule(timer_id, task_id, delay_seconds, action, recurrence)
        self.timers[timer_id] = rule
        return timer_id

    def cancel_timer(self, timer_id: str) -> bool:
        if timer_id in self.timers:
            self.timers[timer_id].is_cancelled = True
            del self.timers[timer_id]
            return True
        return False

    async def start(self) -> None:
        """Start background loop processing timers and events."""
        self._timer_task = asyncio.create_task(self._timer_loop())

    async def stop(self) -> None:
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        for t in self.timers.values():
            t.is_cancelled = True
        self.timers.clear()

    async def _timer_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            now = time.time()
            expired = [t for t in self.timers.values() if not t.is_cancelled and t.due_at <= now]
            for timer in expired:
                if timer.is_cancelled:
                    continue
                evt = EventEnvelope(
                    event_type="TIMER_FIRED",
                    source="timer_engine",
                    task_id=timer.task_id,
                    data={"timer_id": timer.timer_id, "action": timer.action},
                )
                self.emit(evt)

                if timer.recurrence_seconds and not timer.is_cancelled:
                    timer.due_at = now + timer.recurrence_seconds
                else:
                    self.timers.pop(timer.timer_id, None)
