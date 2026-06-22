"""
core/event_bus.py
=================
In-memory Pub/Sub Event Bus.
Allows plugins and core modules to communicate asynchronously without tight coupling.

Example:
    bus.on("new_article", my_callback)
    bus.emit("new_article", {"title": "Hello", "content": "World"})
"""

import threading
import traceback
from typing import Callable, Any


class EventBus:
    """
    Thread-safe synchronous/asynchronous event dispatcher.
    """

    def __init__(self):
        self._listeners: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()

    def on(self, event_name: str, callback: Callable[[Any], None]) -> None:
        """Register a callback for an event."""
        with self._lock:
            if event_name not in self._listeners:
                self._listeners[event_name] = []
            self._listeners[event_name].append(callback)

    def off(self, event_name: str, callback: Callable[[Any], None]) -> None:
        """Remove a previously registered callback."""
        with self._lock:
            if event_name in self._listeners:
                try:
                    self._listeners[event_name].remove(callback)
                except ValueError:
                    pass

    def emit(self, event_name: str, data: Any = None) -> None:
        """
        Emit an event synchronously (blocks until all listeners finish).
        If you want async, use emit_async.
        """
        with self._lock:
            callbacks = self._listeners.get(event_name, []).copy()

        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                print(f"[EventBus] Error in listener for '{event_name}': {e}")
                traceback.print_exc()

    def emit_async(self, event_name: str, data: Any = None) -> None:
        """
        Emit an event in a background thread.
        Useful for non-blocking notifications.
        """
        def _runner():
            self.emit(event_name, data)
            
        threading.Thread(target=_runner, daemon=True).start()


# Global event bus instance
bus = EventBus()
