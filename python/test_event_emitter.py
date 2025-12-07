"""
Test script for event emitter functionality.
Verifies that waiting events are emitted correctly.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from trading_bot.core.event_emitter import get_event_emitter, BotEvent

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)


def test_event_emitter():
    """Test event emitter with mock waiting scenario."""
    emitter = get_event_emitter()
    
    # Track events
    events_received = []
    
    def on_waiting_start(data):
        logger.info(f"✅ WAITING_START: {data['total_seconds']:.0f}s until {data['next_boundary']}")
        events_received.append(('start', data))
    
    def on_waiting_progress(data):
        logger.info(f"⏳ WAITING_PROGRESS: {data['progress_percent']:.0f}% | {data['remaining_seconds']:.0f}s remaining")
        events_received.append(('progress', data))
    
    def on_waiting_end(data):
        logger.info(f"✅ WAITING_END: Completed after {data['total_seconds']:.0f}s")
        events_received.append(('end', data))
    
    # Register listeners
    emitter.on(BotEvent.WAITING_START, on_waiting_start)
    emitter.on(BotEvent.WAITING_PROGRESS, on_waiting_progress)
    emitter.on(BotEvent.WAITING_END, on_waiting_end)
    
    # Simulate waiting scenario
    logger.info("\n" + "="*60)
    logger.info("Testing event emitter with 100 second wait")
    logger.info("="*60 + "\n")
    
    total_seconds = 100.0
    next_boundary = datetime.now(timezone.utc) + timedelta(seconds=total_seconds)
    
    # Emit start
    emitter.emit_waiting_start(total_seconds, next_boundary, "1h")
    
    # Simulate progress at 10%, 20%, 30%, etc.
    for progress in range(10, 101, 10):
        elapsed = (progress / 100.0) * total_seconds
        emitter.emit_waiting_progress(elapsed, total_seconds, float(progress))
    
    # Emit end
    emitter.emit_waiting_end(total_seconds)
    
    # Verify events
    logger.info("\n" + "="*60)
    logger.info("Event Summary")
    logger.info("="*60)
    logger.info(f"Total events received: {len(events_received)}")
    logger.info(f"  - Start events: {sum(1 for e in events_received if e[0] == 'start')}")
    logger.info(f"  - Progress events: {sum(1 for e in events_received if e[0] == 'progress')}")
    logger.info(f"  - End events: {sum(1 for e in events_received if e[0] == 'end')}")
    
    # Verify we got the right number of events
    assert len(events_received) == 12, f"Expected 12 events (1 start + 10 progress + 1 end), got {len(events_received)}"
    assert events_received[0][0] == 'start', "First event should be start"
    assert events_received[-1][0] == 'end', "Last event should be end"
    
    logger.info("\n✅ All tests passed!")


if __name__ == "__main__":
    test_event_emitter()

