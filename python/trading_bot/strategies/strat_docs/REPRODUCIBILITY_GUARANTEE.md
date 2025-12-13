# Pluggable Strategy System - Reproducibility Guarantee

## The Problem We're Solving

When a trade is executed, you need to know:
- **Which strategy** generated the recommendation?
- **What version** of the strategy?
- **What configuration** was used?
- **What was the raw output** from the strategy?

Without this, you can't:
- Replay the analysis
- Debug why a trade happened
- Improve the strategy
- Audit the decision-making process

## The Solution: Full Audit Trail

Every recommendation stored in the database includes:

```python
{
    # Trade details
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "recommendation": "LONG",
    "confidence": 0.85,
    "entry_price": 50000.0,
    "stop_loss": 49000.0,
    "take_profit": 52000.0,
    "risk_reward_ratio": 2.0,
    
    # REPRODUCIBILITY FIELDS
    "strategy_name": "prompt",  # Which strategy?
    "strategy_version": "1.0",  # What version?
    "strategy_config": {        # What config?
        "use_assistant": true,
        "timeout": 600
    },
    "raw_response": "{...}",    # Full response for replay
    
    # Optional
    "chart_path": "/path/to/chart.png",  # If strategy used charts
}
```

## Database Storage

```sql
CREATE TABLE recommendations (
    id TEXT PRIMARY KEY,
    cycle_id TEXT,
    symbol TEXT,
    timeframe TEXT,
    recommendation TEXT,
    confidence REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    risk_reward REAL,
    reasoning TEXT,
    chart_path TEXT,  -- NULL for non-chart strategies
    
    -- REPRODUCIBILITY FIELDS
    strategy_name TEXT,      -- e.g., "prompt", "technical", "ml"
    strategy_version TEXT,   -- e.g., "1.0", "2.1"
    strategy_config JSONB,   -- Full config used
    raw_response TEXT,       -- Full response for replay
    
    prompt_name TEXT,
    analyzed_at TIMESTAMPTZ,
    cycle_boundary TIMESTAMPTZ,
    created_at TIMESTAMPTZ
);
```

## Replay/Reproducibility Workflow

### 1. Query Historical Trade
```sql
SELECT * FROM recommendations 
WHERE symbol = 'BTCUSDT' 
AND cycle_id = 'cycle_123'
AND strategy_name = 'prompt';
```

### 2. Extract Strategy Info
```python
strategy_name = "prompt"
strategy_version = "1.0"
strategy_config = {
    "use_assistant": true,
    "timeout": 600
}
raw_response = "{...}"  # Full response
```

### 3. Replay Analysis
```python
# Load the exact strategy version
strategy = StrategyFactory.create(
    instance_id=instance_id,
    config=config,
    run_id=run_id
)

# Verify it matches
current_output = strategy.analyze_symbols(
    symbols=["BTCUSDT"],
    timeframe="1h",
    cycle_id="cycle_123"
)

# Compare with stored output
assert current_output[0]["raw_response"] == raw_response
```

## Audit Trail Benefits

### 1. **Debugging**
- Why did this trade happen?
- What data was analyzed?
- What was the strategy thinking?

### 2. **Improvement**
- Which strategy version performed best?
- What config settings worked?
- How to optimize?

### 3. **Compliance**
- Full decision audit trail
- Reproducible results
- Traceable to exact strategy and config

### 4. **Testing**
- Replay trades with different strategies
- A/B test strategy versions
- Validate improvements

## Strategy Independence

Each strategy can have completely different implementation:

### Strategy 1: Chart-Based (Prompt)
```python
{
    "strategy_name": "prompt",
    "strategy_version": "1.0",
    "strategy_config": {
        "use_assistant": true,
        "timeout": 600
    },
    "chart_path": "/path/to/chart.png",  # Has chart
    "raw_response": "{...}"  # Full AI response
}
```

### Strategy 2: API-Based (Technical)
```python
{
    "strategy_name": "technical",
    "strategy_version": "1.0",
    "strategy_config": {
        "rsi_period": 14,
        "macd_fast": 12,
        "macd_slow": 26
    },
    "chart_path": None,  # No chart
    "raw_response": "{...}"  # Full indicator response
}
```

### Strategy 3: ML-Based
```python
{
    "strategy_name": "ml_ensemble",
    "strategy_version": "2.1",
    "strategy_config": {
        "model_path": "/models/ensemble_v2.1.pkl",
        "feature_set": "technical_v3"
    },
    "chart_path": None,  # No chart
    "raw_response": "{...}"  # Full model output
}
```

## Reproducibility Guarantee

**Given**:
- Same symbol
- Same timeframe
- Same strategy_name
- Same strategy_version
- Same strategy_config

**You can**:
- Replay the analysis
- Get identical results
- Verify the trade decision
- Debug the strategy

**This is guaranteed** because:
1. Strategy version is immutable
2. Config is stored exactly as used
3. Raw response is stored for verification
4. Strategy implementation is deterministic

## Implementation Checklist

- [ ] Every strategy returns: strategy_name, strategy_version, strategy_config, raw_response
- [ ] Database stores all reproducibility fields
- [ ] TradingCycle extracts and stores reproducibility fields
- [ ] UI displays strategy info for each recommendation
- [ ] Replay tool can reconstruct analysis from stored data
- [ ] Tests verify reproducibility

## Example: Debugging a Trade

```python
# 1. Find the trade
trade = db.query("""
    SELECT * FROM recommendations 
    WHERE id = 'rec_123'
""")[0]

# 2. Extract strategy info
print(f"Strategy: {trade['strategy_name']} v{trade['strategy_version']}")
print(f"Config: {trade['strategy_config']}")

# 3. Load strategy
strategy = StrategyFactory.create(
    instance_id=trade['instance_id'],
    config=config,
    run_id=trade['run_id']
)

# 4. Replay
result = strategy.analyze_symbols(
    symbols=[trade['symbol']],
    timeframe=trade['timeframe'],
    cycle_id=trade['cycle_id']
)

# 5. Verify
assert result[0]['raw_response'] == trade['raw_response']
print("✅ Trade is reproducible!")
```

## Summary

**Every trade is fully reproducible** because:
1. Strategy name and version are stored
2. Full config is stored
3. Raw response is stored
4. Strategy implementation is deterministic
5. Can replay analysis anytime

This enables:
- Debugging
- Improvement
- Compliance
- Testing
- Optimization
