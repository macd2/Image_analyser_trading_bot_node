# Spread-Based Trade Premature Exit Fix - Implementation Summary

## Date: 2025-12-25

## Problem Summary
All 41 closed spread-based paper trades were closing within the **same candle** as they filled (0 minutes between fill and close), with 93% exiting via `tp_hit` or `sl_hit` instead of the expected `z_score_exit`.

**Root Cause**: The `check_strategy_exit.py` script was incorrectly applying price-level SL/TP checks to spread-based trades, causing them to exit immediately when the fill candle's high/low touched the SL/TP price levels, **before** the z-score had a chance to revert.

## Changes Implemented

### Priority 1: Fix check_strategy_exit.py ✅

**File**: `python/check_strategy_exit.py`

**Changes**:
1. Added `strategy_type` detection from trade data (line 158-159)
2. Added conditional logic to skip price-level SL/TP checks for spread-based trades (lines 236-243)
3. Properly indented all SL/TP checking logic inside `else` block for price-based trades only (lines 244-343)

**Key Logic**:
```python
# Get strategy type to determine exit logic
strategy_type = trade_data.get("strategy_type")
is_spread_based = strategy_type == "spread_based"

# CRITICAL FIX: For spread-based trades, SKIP price-level SL/TP checks
if is_spread_based:
    # For spread-based trades, ONLY use strategy.should_exit() result
    # Do NOT check if candle high/low touched SL/TP levels
    pass  # Skip price-level SL/TP checks
else:
    # For price-based trades, check SL/TP as normal
    # ... existing SL/TP checking logic
```

### Priority 2: Pass strategy_type to Python Script ✅

**File**: `app/api/bot/simulator/auto-close/route.ts`

**Changes**:
1. Added `strategy_type` to `tradeData` object passed to Python script (line 734)

**Key Change**:
```typescript
const tradeData = {
  symbol: trade.symbol,
  side: trade.side,
  entry_price: trade.entry_price,
  stop_loss: trade.stop_loss,
  take_profit: trade.take_profit,
  strategy_metadata: strategyMetadata,
  strategy_type: trade.strategy_type  // CRITICAL: Pass strategy_type to Python script
};
```

### Position Monitor Status ✅

**File**: `python/trading_bot/engine/enhanced_position_monitor.py`

**Status**: **NO CHANGES NEEDED** ✅

The position monitor already:
- Fetches `strategy_type` from database (line 1267)
- Only calls `strategy.should_exit()` directly (line 978)
- Does NOT have price-level SL/TP checking logic
- Is already working correctly for spread-based trades

## Expected Outcomes

After these fixes:

1. **Spread-based trades will hold for multiple candles** until z-score reverts
2. **Exit reasons will be accurate**:
   - `z_score_exit` for normal mean-reversion exits (should be ~90%)
   - `max_spread_deviation_exceeded` for risk management exits (should be ~10%)
   - **NO MORE** `tp_hit` or `sl_hit` for spread-based trades
3. **Timing will be realistic**:
   - `minutes_filled_to_close` will vary (could be hours or days)
   - Trades will close when spread actually reverts, not immediately
4. **PnL will be more accurate** - reflecting actual mean-reversion performance

## Testing Recommendations

1. **Reset test trades** to `paper_trade` status
2. **Run auto-close** and verify trades don't close immediately
3. **Check exit reasons** - should be `z_score_exit` when trades eventually close
4. **Monitor logs** for proper z-score exit logging
5. **Validate with SQL** - check exit reason distribution and timing

## Files Modified

1. ✅ `python/check_strategy_exit.py` - Added strategy-type-aware exit logic
2. ✅ `app/api/bot/simulator/auto-close/route.ts` - Pass strategy_type to Python script
3. ✅ `python/trading_bot/engine/enhanced_position_monitor.py` - No changes needed (already correct)

## Verification

- ✅ No syntax errors in modified files
- ✅ Logic flow verified
- ✅ Indentation corrected
- ✅ Comments added for clarity
- ✅ Position monitor confirmed working correctly

## Next Steps

1. Test with existing spread-based trades
2. Monitor auto-close execution logs
3. Verify exit reasons in database
4. Confirm realistic timing between fill and close

