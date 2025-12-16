# PromptStrategy Integration Guide

## Current Status

✅ PromptStrategy is **production-ready** as a drop-in replacement for TradingCycle's internal sourcer/cleaner/analyzer.

## How to Integrate

### Option 1: Gradual Integration (Recommended)

Keep TradingCycle as-is, but use PromptStrategy for new instances:

```python
# In TradingCycle.__init__()
if use_strategy_system:
    # Use new pluggable strategy system
    from trading_bot.strategies.factory import StrategyFactory
    self.strategy = StrategyFactory.create(
        instance_id=instance_id,
        config=config,
        run_id=run_id,
        heartbeat_callback=heartbeat_callback
    )
else:
    # Use legacy sourcer/cleaner/analyzer
    self.sourcer = ChartSourcer(config=config)
    self.analyzer = ChartAnalyzer(...)
    self.cleaner = ChartCleaner(...)
```

### Option 2: Full Migration

Replace TradingCycle's internal components with PromptStrategy:

```python
# In TradingCycle.__init__()
from trading_bot.strategies.factory import StrategyFactory

self.strategy = StrategyFactory.create(
    instance_id=instance_id,
    config=config,
    run_id=run_id,
    heartbeat_callback=heartbeat_callback
)
```

Then in `_analyze_cycle_async()`:

```python
# OLD:
recommendations = await self._analyze_all_charts_parallel(symbols, cycle_id)

# NEW:
recommendations = await self.strategy.run_analysis_cycle(
    symbols=[],  # Ignored - strategy uses watchlist
    timeframe="",  # Ignored - strategy uses config
    cycle_id=cycle_id
)
```

## Data Compatibility

PromptStrategy returns **identical output format** to current system:

```python
{
    "symbol": "BTCUSDT",
    "recommendation": "BUY",
    "confidence": 0.85,
    "entry_price": 50000.0,
    "stop_loss": 49000.0,
    "take_profit": 52000.0,
    "risk_reward": 2.0,
    "setup_quality": 0.8,
    "market_environment": 0.7,
    "analysis": {
        # Full analyzer result with metadata
        "prompt_id": "...",
        "prompt_version": "...",
        "assistant_model": "...",
        "raw_response": "...",
        "market_data_snapshot": {...},
        "analysis_prompt": "...",
        # ... more fields
    },
    "chart_path": "/path/to/chart.png",
    "timeframe": "1h",
    "cycle_id": "cycle-123"
}
```

**No changes needed to downstream code** - TradingCycle._record_recommendation() works unchanged.

## Testing Before Integration

### 1. Run Mock Tests (No Database)
```bash
python python/trading_bot/strategies/prompt/test_prompt_strategy_mock.py
```

### 2. Run Standalone Tests (With Database)
```bash
python python/trading_bot/strategies/prompt/test_prompt_strategy_standalone.py
```

### 3. Test with Real Instance
```python
from trading_bot.strategies.factory import StrategyFactory
from trading_bot.config.settings_v2 import ConfigV2

# Load real config
config = ConfigV2.from_instance("your-instance-id")

# Create strategy
strategy = StrategyFactory.create(
    instance_id="your-instance-id",
    config=config,
    run_id="test-run"
)

# Run analysis
recommendations = await strategy.run_analysis_cycle(
    symbols=[],
    timeframe="",
    cycle_id="test-cycle"
)

print(f"Got {len(recommendations)} recommendations")
```

## Rollback Plan

If issues arise:

1. Keep TradingCycle's original sourcer/cleaner/analyzer
2. Use Option 1 (gradual integration) with feature flag
3. Switch back to legacy system for affected instances
4. Debug PromptStrategy independently

## Performance Considerations

PromptStrategy uses:
- **Async/await** for parallel chart analysis
- **Thread pool executor** for blocking analyzer calls
- **Same API calls** as original system (no extra overhead)

Expected performance: **Identical to current system**

## Next Steps

1. ✅ PromptStrategy is ready
2. ⏳ Choose integration approach (gradual or full)
3. ⏳ Add feature flag to TradingCycle
4. ⏳ Test with real instances
5. ⏳ Monitor and validate
6. ⏳ Migrate remaining instances

