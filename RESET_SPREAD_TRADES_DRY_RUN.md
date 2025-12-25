# Reset Spread-Based Trades - Dry Run Report

**Date**: 2025-12-25  
**Status**: ✅ DRY RUN COMPLETE - Ready for approval

---

## Summary

**46 spread-based trades** will be reset from `closed`/`filled` status back to `paper_trade` status.

- **Closed trades**: 41
- **Filled trades**: 5
- **Total**: 46

---

## Key Finding: Bug Confirmation ✅

**ALL 46 trades are exiting via `tp_hit`** - This confirms the bug we just fixed!

Sample exit reasons from the trades:
- `tp_hit` (100% of trades)

This proves that spread-based trades were incorrectly exiting on price-level TP hits instead of waiting for z-score mean reversion.

---

## What Will Be Reset

For each of the 46 trades:

**Cleared (set to NULL)**:
- `fill_price`
- `fill_quantity`
- `fill_time`
- `filled_at`
- `pair_fill_price`
- `exit_price`
- `pair_exit_price`
- `exit_reason`
- `closed_at`
- `pnl`
- `pnl_percent`
- `avg_exit_price`
- `closed_size`

**Preserved (unchanged)**:
- ✅ `entry_price` - Entry signal price
- ✅ `stop_loss` - Risk management level
- ✅ `take_profit` - Profit target level
- ✅ `strategy_metadata` - Pair symbol, z-score data, etc.
- ✅ `created_at` - Signal creation timestamp
- ✅ All other trade setup data

**Status Change**:
- `closed` → `paper_trade`
- `filled` → `paper_trade`

---

## Sample Trades to Be Reset

| Symbol | Side | Entry Price | Exit Reason | PnL | Status |
|--------|------|-------------|-------------|-----|--------|
| HANAUSDT | Sell | 0.0258073 | tp_hit | -263.3 | closed |
| DAMUSDT | Buy | 0.0579421 | tp_hit | -190.34 | closed |
| OGUSDT | Sell | 13.5922 | tp_hit | 263.88 | closed |
| OGUSDT | Sell | 13.5894 | tp_hit | 263.84 | closed |
| OGUSDT | Sell | 13.5866 | tp_hit | 263.83 | closed |

---

## Next Steps

### To Apply Changes:

```bash
bash scripts/reset-spread-trades.sh --apply
```

Then confirm with `yes` when prompted.

### After Reset:

1. ✅ Trades will be in `paper_trade` status
2. ✅ Entry data (entry_price, SL, TP, metadata) will be intact
3. ✅ All fill/exit/pnl data will be cleared
4. ✅ Ready for simulator re-evaluation with the fixed exit logic

### Expected Outcomes:

- Trades will hold for multiple candles (not close immediately)
- Exit reasons will be `z_score_exit` or `max_spread_deviation_exceeded`
- Timing will be realistic (hours/days, not 0 minutes)
- PnL will reflect actual mean-reversion performance

---

## Verification

After applying, you can verify with:

```sql
SELECT 
  COUNT(*) as total,
  COUNT(CASE WHEN status = 'paper_trade' THEN 1 END) as paper_trade_count,
  COUNT(CASE WHEN filled_at IS NULL THEN 1 END) as unfilled_count
FROM trades
WHERE strategy_type = 'spread_based';
```

Expected result: All 46 trades should be `paper_trade` with `filled_at = NULL`.

---

## Files Created

- ✅ `scripts/reset-spread-trades.sh` - Bash script for resetting trades
- ✅ `python/scripts/reset_spread_trades.py` - Python alternative (for reference)
- ✅ `scripts/reset-spread-trades.ts` - TypeScript alternative (for reference)

**Recommended**: Use the bash script (`scripts/reset-spread-trades.sh`) as it's the most reliable.

---

**Ready to apply? Run:**
```bash
bash scripts/reset-spread-trades.sh --apply
```

