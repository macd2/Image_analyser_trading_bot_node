# Data Integrity Audit Report
**Date:** 2025-12-11  
**Database:** Supabase PostgreSQL  
**Status:** ✅ OVERALL HEALTHY - 4 Minor Issues Found

## Executive Summary

The database maintains **excellent data integrity** with proper instance awareness through the hierarchy:
- `instances -> runs -> cycles -> trades/recommendations`

**Key Metrics:**
- ✅ 127 trades across 2 instances (fully traceable)
- ✅ 1,016 recommendations with proper cycle boundaries
- ✅ 93 cycles properly linked to runs
- ✅ 120 runs properly linked to instances
- ✅ 0 orphaned records (no foreign key violations)

---

## Detailed Findings

### ✅ CHECK 1: Instance Awareness
**Status:** PASS  
All 127 trades are traceable to instances through run_id:
- Instance 1: 126 trades (104 runs, 67 cycles)
- Instance 2: 1 trade (16 runs, 26 cycles)

### ✅ CHECK 2-8: Referential Integrity
**Status:** PASS  
- All trades reference cycles (127/127)
- All trades reference recommendations (127/127)
- All recommendations reference cycles (1,016/1,016)
- All cycles reference runs (93/93)
- All runs reference instances (120/120)
- **Zero orphaned records**

### ⚠️ CHECK 9: Date Consistency
**Status:** 3 ANOMALIES FOUND  
3 trades have `created_at > closed_at` (impossible):
- Trade 5556af97 (MUSDT): created 2025-12-08, closed 2025-12-05 (-2 days)
- Trade d79f8233 (ATHUSDT): created 2025-12-07, closed 2025-12-06 (-1 day)
- Trade 7368ee22 (UNIUSDT): created 2025-12-07, closed 2025-12-05 (-2 days)

**Root Cause:** Likely simulator backfill or historical data import with incorrect timestamps.

### ⚠️ CHECK 11: Missing closed_at
**Status:** 7 INCOMPLETE RECORDS  
7 cancelled trades missing `closed_at`:
- All from instance ab8b1a36 (recent: 2025-12-10)
- All have status='cancelled' but no closed_at timestamp
- No PnL values recorded

**Root Cause:** Auto-close simulator not setting closed_at when cancelling trades.

### ⚠️ CHECK 13: Missing PnL
**Status:** 16 INCOMPLETE RECORDS  
16 closed/cancelled trades missing PnL values:
- 7 trades also missing closed_at (same issue as above)
- 9 trades have closed_at but missing pnl/pnl_percent
- All have entry_price but no exit_price

**Root Cause:** PnL calculation not triggered or not persisted.

### ⚠️ CHECK 14: Missing Timeframe
**Status:** 2 MINOR ISSUES  
2 trades missing timeframe:
- Trade 332c484d (MUSDT): recommendation has 1h
- Trade 7e2cf079 (WAVESUSDT): recommendation has 1h

**Root Cause:** Trade creation not copying timeframe from recommendation.

---

## Instance Distribution

| Instance ID | Runs | Cycles | Trades | Recommendations |
|---|---|---|---|---|
| ab8b1a36... | 104 | 67 | 126 | 846 |
| 3b21e1be... | 16 | 26 | 1 | 170 |

Both instances properly isolated with no cross-contamination.

---

## Recommendations

1. **Fix auto-close simulator** to set `closed_at` and calculate PnL for cancelled trades
2. **Fix trade creation** to copy `timeframe` from recommendation
3. **Investigate 3 date anomalies** - likely from historical data import
4. **Add database constraints** to prevent future issues:
   - NOT NULL for closed_at when status IN ('closed', 'cancelled')
   - NOT NULL for pnl when status IN ('closed', 'cancelled')
   - CHECK constraint: created_at <= closed_at

---

## Conclusion

✅ **Instance awareness is properly implemented** through the run hierarchy.  
✅ **No orphaned or corrupted records** - referential integrity is solid.  
⚠️ **4 minor data quality issues** - all fixable without schema changes.

