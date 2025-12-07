"""
Simple event emitter for bot state tracking.
Emits events when bot enters waiting state and during progress updates.
"""

import logging
from typing import Callable, Dict, Any, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class BotEvent(Enum):
    """Bot event types."""
    WAITING_START = "waiting_start"
    WAITING_PROGRESS = "waiting_progress"
    WAITING_END = "waiting_end"
    CYCLE_START = "cycle_start"
    CYCLE_END = "cycle_end"


class EventEmitter:
    """Simple event emitter for bot state tracking."""

    def __init__(self):
        """Initialize event emitter."""
        self._listeners: Dict[BotEvent, List[Callable]] = {event: [] for event in BotEvent}

    def on(self, event: BotEvent, callback: Callable) -> None:
        """
        Register a listener for an event.

        Args:
            event: Event type to listen for
            callback: Function to call when event is emitted
        """
        self._listeners[event].append(callback)

    def off(self, event: BotEvent, callback: Callable) -> None:
        """
        Unregister a listener for an event.

        Args:
            event: Event type
            callback: Function to remove
        """
        if callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def emit(self, event: BotEvent, data: Dict[str, Any]) -> None:
        """
        Emit an event to all registered listeners.

        Args:
            event: Event type to emit
            data: Event data
        """
        for callback in self._listeners[event]:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Error in event listener for {event.value}: {e}")

    def emit_waiting_start(self, total_seconds: float, next_boundary: datetime, timeframe: str) -> None:
        """Emit waiting start event."""
        self.emit(BotEvent.WAITING_START, {
            "total_seconds": total_seconds,
            "next_boundary": next_boundary.isoformat(),
            "timeframe": timeframe,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def emit_waiting_progress(self, elapsed_seconds: float, total_seconds: float, progress_percent: float) -> None:
        """Emit waiting progress event."""
        self.emit(BotEvent.WAITING_PROGRESS, {
            "elapsed_seconds": elapsed_seconds,
            "total_seconds": total_seconds,
            "progress_percent": progress_percent,
            "remaining_seconds": total_seconds - elapsed_seconds,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def emit_waiting_end(self, total_seconds: float) -> None:
        """Emit waiting end event."""
        self.emit(BotEvent.WAITING_END, {
            "total_seconds": total_seconds,
            "timestamp": datetime.utcnow().isoformat(),
        })


# Global event emitter instance
_event_emitter = EventEmitter()


def get_event_emitter() -> EventEmitter:
    """Get the global event emitter instance."""
    return _event_emitter

