# Complete Trade Traceability Guide

## Overview

Every trade in the system is fully traceable from analysis through closure with complete audit trail. Each trade is linked to:
- **strategy_uuid**: Exact strategy instance that created it
- **run_id**: Bot session it belongs to
- **cycle_id**: Trading cycle it was generated in
- **instance_id**: Bot instance configuration
- **All settings and decisions** at each phase

## Critical Factors Affecting Trade Outcomes

### 1. Position Sizing Impact
Position size directly determines P&L magnitude. Current system tracks:
- ✅ `position_size_usd`: Position value in USD
- ✅ `risk_amount_usd`: Risk amount in USD
- ✅ `risk_percentage`: Risk as % of wallet
- ✅ `confidence_weight`: Confidence multiplier (0.8x to 1.2x)
- ✅ `sizing_method`: 'kelly' or 'fixed'
- ✅ `risk_pct_used`: Actual risk % used

**Formula**: `position_size = (wallet_balance × risk_pct × confidence_weight) / risk_per_unit`

### 2. Trade Ranking Impact
Ranking determines which signals get executed. Current system:
- ✅ Ranks by composite score: (confidence×0.4) + (RR×0.3) + (setup_quality×0.2) + (market_env×0.1)
- ✅ Selects top N signals based on available slots
- ✅ Stores ranking_score in recommendations

**Missing**: `ranking_score` not stored in trades table for traceability

## Trade Lifecycle Phases

### 1. Analysis Phase
```sql
-- Strategy generates recommendation
SELECT * FROM recommendations 
WHERE strategy_uuid = 'abc-123-def'
  AND cycle_id = 'cycle-456'
  AND symbol = 'BTCUSDT';
```
**Stored**: strategy_uuid, strategy_type, strategy_name, strategy_config

### 2. Execution Phase
```sql
-- Trade created from recommendation
SELECT t.*, r.strategy_uuid, r.strategy_type
FROM trades t
JOIN recommendations r ON t.recommendation_id = r.id
WHERE t.id = 'trade-789';
```
**Stored**: strategy_uuid, status, submitted_at, filled_at, fill_price

### 3. Monitoring Phase
```sql
-- All position monitor actions logged
SELECT * FROM position_monitor_logs
WHERE trade_id = 'trade-789'
  AND strategy_uuid = 'abc-123-def'
ORDER BY created_at;
```
**Logged**: sl_tightened, tp_proximity_activated, age_tightening

### 4. Simulation/Live Phase
```sql
-- Exit condition checks and results
SELECT * FROM error_logs
WHERE trade_id = 'trade-789'
  AND component = 'simulator'
  AND event = 'exit_triggered'
ORDER BY created_at;
```
**Logged**: exit_reason, exit_price, z_score (for spread-based)

### 5. Closure Phase
```sql
-- Final trade state
SELECT * FROM trades
WHERE id = 'trade-789';
```
**Stored**: exit_price, exit_reason, pnl, pnl_percent, closed_at

## Complete Trade Query

```sql
-- Get complete trade history with all actions
SELECT 
  t.id as trade_id,
  t.symbol,
  t.side,
  t.entry_price,
  t.stop_loss,
  t.take_profit,
  t.strategy_uuid,
  t.strategy_type,
  r.strategy_name,
  r.strategy_config,
  t.submitted_at,
  t.filled_at,
  t.closed_at,
  t.exit_reason,
  t.pnl,
  t.pnl_percent,
  COUNT(DISTINCT e.id) as execution_count,
  COUNT(DISTINCT pml.id) as monitor_actions,
  COUNT(DISTINCT el.id) as error_events
FROM trades t
LEFT JOIN recommendations r ON t.recommendation_id = r.id
LEFT JOIN executions e ON t.id = e.trade_id
LEFT JOIN position_monitor_logs pml ON t.id = pml.trade_id
LEFT JOIN error_logs el ON t.id = el.trade_id
WHERE t.id = 'trade-789'
GROUP BY t.id;
```

## Reproducibility: Replay a Trade

```python
# Query complete trade history
trade = query_one(db, """
    SELECT t.*, r.strategy_uuid, r.strategy_type, r.strategy_name,
           r.strategy_config, i.settings as instance_settings
    FROM trades t
    JOIN recommendations r ON t.recommendation_id = r.id
    JOIN runs run ON t.run_id = run.id
    JOIN instances i ON run.instance_id = i.id
    WHERE t.id = ?
""", (trade_id,))

# Recreate exact strategy instance
strategy = recreate_strategy_from_uuid(
    strategy_uuid=trade['strategy_uuid'],
    strategy_type=trade['strategy_type'],
    strategy_name=trade['strategy_name'],
    config=json.loads(trade['strategy_config']),
    instance_settings=json.loads(trade['instance_settings'])
)

# Now you can:
# 1. Replay exit condition with fresh candles
# 2. Test different monitoring settings
# 3. Analyze what would have happened with different parameters
```

## What Gets Tracked

✅ **Analysis**: Strategy type, config, confidence, entry/SL/TP  
✅ **Execution**: Order submission, fills, fees, timing  
✅ **Monitoring**: All SL adjustments, TP proximity, age-based actions  
✅ **Simulation**: Exit conditions, z-score crosses, price touches  
✅ **Errors**: All errors with full context and stack traces  
✅ **Settings**: Instance config snapshot at trade creation  
✅ **Timing**: Every timestamp from analysis to closure  

## Missing Data for Complete Traceability

### In recommendations table:
- ❌ `ranking_score`: Composite quality score (needed for understanding why trade was selected)
- ❌ `ranking_position`: Position in ranked list (1st, 2nd, 3rd, etc.)
- ❌ `setup_quality`: Setup quality score (currently only in signal, not stored)
- ❌ `market_environment`: Market environment score (currently only in signal, not stored)

### In trades table:
- ❌ `ranking_score`: Copied from recommendation (for quick analysis)
- ❌ `ranking_position`: Position in ranked list when trade was selected
- ❌ `available_slots`: How many slots were available when trade was selected
- ❌ `total_signals_analyzed`: Total signals analyzed in cycle
- ❌ `total_signals_ranked`: Total actionable signals ranked
- ❌ `kelly_fraction_used`: Kelly fraction if Kelly Criterion was used
- ❌ `wallet_balance_at_trade`: Wallet balance when trade was created (for reproducibility)

### In position_monitor_logs table (NEW):
- ❌ `ranking_score`: Original ranking score (for context)
- ❌ `original_position_size`: Original position size before any adjustments
- ❌ `adjusted_position_size`: Position size after adjustments (if any)

## Audit Trail Benefits

- **Reproducibility**: Replay any trade with original settings
- **Testing**: Test different strategies on historical trades
- **Enhancement**: Analyze decisions and improve strategy
- **Compliance**: Full audit trail for regulatory requirements
- **Debugging**: Trace any issue back to root cause
- **Ranking Analysis**: Understand why specific trades were selected over others
- **Position Sizing Analysis**: Verify sizing decisions and Kelly Criterion calculations

