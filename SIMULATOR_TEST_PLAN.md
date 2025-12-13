# Simulator Test Plan

## Overview
This document outlines the test plan for verifying the simulator logic after the critical fix for run aggregates updates.

## Test Cases

### Test 1: Trade Closes Due to TP Hit
**Scenario**: A long trade hits take profit
**Expected Behavior**:
- Trade status changes to 'closed'
- exit_price = take_profit
- exit_reason = 'tp_hit'
- pnl = (exit_price - entry_price) * quantity
- runs.total_pnl += pnl
- runs.win_count += 1 (if pnl > 0)

**Verification**:
```sql
SELECT t.id, t.symbol, t.pnl, t.status, r.total_pnl, r.win_count 
FROM trades t 
JOIN runs r ON t.run_id = r.id 
WHERE t.exit_reason = 'tp_hit' AND t.status = 'closed' 
LIMIT 1;
```

### Test 2: Trade Closes Due to SL Hit
**Scenario**: A short trade hits stop loss
**Expected Behavior**:
- Trade status changes to 'closed'
- exit_price = stop_loss
- exit_reason = 'sl_hit'
- pnl = (entry_price - exit_price) * quantity
- runs.total_pnl += pnl
- runs.loss_count += 1 (if pnl < 0)

### Test 3: Trade Cancelled Before Fill
**Scenario**: Trade stays pending_fill for max_bars_before_filled bars
**Expected Behavior**:
- Trade status changes to 'cancelled'
- exit_reason = 'max_bars_exceeded'
- pnl = NULL (never filled)
- exit_price = NULL
- runs aggregates NOT updated (trade never opened)

### Test 4: Trade Cancelled After Fill
**Scenario**: Filled trade stays open for max_bars_after_filled bars
**Expected Behavior**:
- Trade status changes to 'cancelled'
- exit_reason = 'max_bars_exceeded'
- exit_price = current_price
- pnl = (current_price - fill_price) * quantity
- runs.total_pnl += pnl
- runs.win_count or loss_count += 1

### Test 5: Run Aggregates Consistency
**Scenario**: Verify run aggregates match actual trades
**Expected Behavior**:
```sql
-- Should return 0 rows if aggregates are correct
SELECT r.id, r.total_pnl, r.win_count, r.loss_count,
  SUM(t.pnl) as actual_pnl,
  SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as actual_wins,
  SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) as actual_losses
FROM runs r
LEFT JOIN trades t ON t.run_id = r.id AND t.pnl IS NOT NULL
GROUP BY r.id
HAVING r.total_pnl != COALESCE(SUM(t.pnl), 0)
  OR r.win_count != SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END)
  OR r.loss_count != SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END);
```

## Execution Steps

1. Run auto-close endpoint: `POST /api/bot/simulator/auto-close`
2. Wait for trades to close
3. Execute Test 1-4 queries to verify individual trade behavior
4. Execute Test 5 query to verify aggregates consistency
5. Check logs for any errors or warnings

## Success Criteria

- ✅ All trades with pnl IS NOT NULL have status = 'closed' or 'cancelled'
- ✅ All closed trades have exit_price and exit_reason set
- ✅ All cancelled trades before fill have pnl = NULL
- ✅ All cancelled trades after fill have pnl set
- ✅ Run aggregates match actual trades (Test 5 returns 0 rows)
- ✅ No database errors in logs

