# Bot Waiting and Wake-Up Log Example

## Complete Log Flow for 1-Hour Timeframe

```
2025-12-07 09:00:00 | INFO | __main__ | 🚀 Running initial cycle immediately...
2025-12-07 09:00:05 | INFO | trading_bot.engine.trading_cycle | ============================================================
2025-12-07 09:00:05 | INFO | trading_bot.engine.trading_cycle | 🔄 CYCLE #1 [a1b2c3d4] - 2025-12-07 09:00:05 UTC
2025-12-07 09:00:05 | INFO | trading_bot.engine.trading_cycle | ============================================================
2025-12-07 09:00:15 | INFO | trading_bot.engine.trading_cycle | ✅ Captured 5 charts from watchlist
2025-12-07 09:00:20 | INFO | trading_bot.engine.trading_cycle | ✅ Parallel analysis completed in 5.2s
2025-12-07 09:00:25 | INFO | trading_bot.engine.trading_cycle | ✅ Executed 2 trades
2025-12-07 09:00:26 | INFO | trading_bot.engine.trading_cycle | Trades executed: 2
2025-12-07 09:00:26 | INFO | trading_bot.engine.trading_cycle | Errors: 0

⏰ ENTERING WAITING PHASE ⏰

2025-12-07 09:00:27 | INFO | __main__ | 
⏰ Next cycle at 10:00:00 UTC
   Waiting 3600 seconds...

2025-12-07 09:00:27 | INFO | trading_bot.core.event_emitter | [WAITING_START] Total: 3600s, Next: 10:00:00 UTC

⏳ PROGRESS UPDATES EVERY 10% ⏳

2025-12-07 09:06:00 | INFO | __main__ | ⏳ Progress: 10% | Remaining: 54.0 minutes (3240s)
2025-12-07 09:12:00 | INFO | __main__ | ⏳ Progress: 20% | Remaining: 48.0 minutes (2880s)
2025-12-07 09:18:00 | INFO | __main__ | ⏳ Progress: 30% | Remaining: 42.0 minutes (2520s)
2025-12-07 09:24:00 | INFO | __main__ | ⏳ Progress: 40% | Remaining: 36.0 minutes (2160s)
2025-12-07 09:30:00 | INFO | __main__ | ⏳ Progress: 50% | Remaining: 30.0 minutes (1800s)
2025-12-07 09:36:00 | INFO | __main__ | ⏳ Progress: 60% | Remaining: 24.0 minutes (1440s)
2025-12-07 09:42:00 | INFO | __main__ | ⏳ Progress: 70% | Remaining: 18.0 minutes (1080s)
2025-12-07 09:48:00 | INFO | __main__ | ⏳ Progress: 80% | Remaining: 12.0 minutes (720s)
2025-12-07 09:54:00 | INFO | __main__ | ⏳ Progress: 90% | Remaining: 6.0 minutes (360s)
2025-12-07 09:59:30 | INFO | __main__ | ⏳ Progress: 100% | Remaining: 0.0 minutes (0s)

⏰ BOUNDARY REACHED - WAKING UP! ⏰

2025-12-07 10:00:00 | INFO | trading_bot.core.event_emitter | [WAITING_END] Completed after 3600s
2025-12-07 10:00:00 | INFO | __main__ | 
============================================================
2025-12-07 10:00:00 | INFO | __main__ | ⏰ BOUNDARY REACHED - WAKING UP!
2025-12-07 10:00:00 | INFO | __main__ |    Current time: 10:00:00 UTC
2025-12-07 10:00:00 | INFO | __main__ |    Starting trading cycle...
2025-12-07 10:00:00 | INFO | __main__ | ============================================================

🔄 NEXT CYCLE STARTS 🔄

2025-12-07 10:00:00 | INFO | trading_bot.engine.trading_cycle | ============================================================
2025-12-07 10:00:00 | INFO | trading_bot.engine.trading_cycle | 🔄 CYCLE #2 [e5f6g7h8] - 2025-12-07 10:00:00 UTC
2025-12-07 10:00:00 | INFO | trading_bot.engine.trading_cycle | ============================================================
2025-12-07 10:00:10 | INFO | trading_bot.engine.trading_cycle | ✅ Captured 5 charts from watchlist
2025-12-07 10:00:15 | INFO | trading_bot.engine.trading_cycle | ✅ Parallel analysis completed in 5.1s
2025-12-07 10:00:20 | INFO | trading_bot.engine.trading_cycle | ✅ Executed 1 trade
2025-12-07 10:00:21 | INFO | trading_bot.engine.trading_cycle | Trades executed: 1
2025-12-07 10:00:21 | INFO | trading_bot.engine.trading_cycle | Errors: 0

⏰ ENTERING WAITING PHASE AGAIN ⏰

2025-12-07 10:00:22 | INFO | __main__ | 
⏰ Next cycle at 11:00:00 UTC
   Waiting 3600 seconds...
```

## Key Log Markers

| Marker | Meaning | When |
|--------|---------|------|
| `⏰ Next cycle at HH:MM:SS UTC` | Entering wait phase | After cycle completes |
| `⏳ Progress: XX%` | Progress update | Every 10% of wait time |
| `⏰ BOUNDARY REACHED - WAKING UP!` | Bot waking up | When boundary time reached |
| `Current time: HH:MM:SS UTC` | Exact wake-up time | Confirms accurate timing |
| `Starting trading cycle...` | Cycle about to start | Before cycle execution |

## Monitoring the Bot

You can monitor the bot's health by watching for:

1. **Regular progress updates** - Should see one every ~6 minutes for 1h timeframe
2. **Wake-up message** - Should appear exactly at boundary time
3. **Cycle execution** - Should start immediately after wake-up
4. **No gaps** - Should see continuous logs, no long silences

## Event Emission

The bot also emits events that can be captured programmatically:

```python
from trading_bot.core.event_emitter import get_event_emitter, BotEvent

emitter = get_event_emitter()

# Listen for wake-up
emitter.on(BotEvent.WAITING_END, lambda data: print("Bot waking up!"))

# Listen for progress
emitter.on(BotEvent.WAITING_PROGRESS, lambda data: 
    print(f"Progress: {data['progress_percent']}%"))
```

