import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class PulseEvent:
    level: str
    kind: str
    message: str
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_sse(self) -> dict:
        return {
            "ts": self.ts.isoformat(),
            "level": self.level,
            "kind": self.kind,
            "message": self.message,
        }


class PulseBus:
    def __init__(self, buffer_size: int = 500) -> None:
        self._subscribers: set[threading.Event] = set()
        self._listeners: list = []
        self._buffer: deque[PulseEvent] = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
        self._durable_sink = None

    def bind_durable_sink(self, sink) -> None:
        self._durable_sink = sink

    def emit(self, level: str, kind: str, message: str) -> PulseEvent:
        event = PulseEvent(level=level, kind=kind, message=message)
        with self._lock:
            self._buffer.append(event)
            listeners = list(self._listeners)
        if self._durable_sink is not None:
            try:
                self._durable_sink(event)
            except Exception:
                pass
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                pass
        return event

    def subscribe(self, listener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def unsubscribe(self, listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def recent(self, count: int = 50) -> list[PulseEvent]:
        with self._lock:
            return list(self._buffer)[-count:]


pulse_bus = PulseBus()
