# Backfill Spread Trade Historical Entry Stats

## Overview
This migration backfills `spread_mean_at_entry` and `spread_std_at_entry` for all existing spread-based trades. These values are needed for the chart to display entry lines frozen at signal time.

## What Gets Updated
For each spread-based trade (identified by `pair_symbol` in `strategy_metadata`):
- `spread_mean_at_entry` ← copied from `spread_mean`
- `spread_std_at_entry` ← copied from `spread_std`

This ensures the chart shows entry levels frozen at the moment the signal was generated.

## Running the Migration

### Option 1: PostgreSQL (Production)
```bash
# Run the SQL migration directly
psql $DATABASE_URL -f lib/db/migrations/015_backfill_spread_trade_entry_stats.sql

# Or via psql interactive
psql $DATABASE_URL
\i lib/db/migrations/015_backfill_spread_trade_entry_stats.sql
```

### Option 2: Python Script (SQLite or PostgreSQL)
```bash
# Run the Python backfill script
python python/scripts/backfill_spread_trade_stats.py
```

## Verification
After running the migration, verify the backfill:

```sql
-- Check how many trades were updated
SELECT 
  COUNT(*) as total_spread_trades,
  COUNT(CASE WHEN strategy_metadata->'spread_mean_at_entry' IS NOT NULL THEN 1 END) as with_mean_at_entry,
  COUNT(CASE WHEN strategy_metadata->'spread_std_at_entry' IS NOT NULL THEN 1 END) as with_std_at_entry
FROM trades
WHERE strategy_metadata IS NOT NULL
  AND strategy_metadata->>'pair_symbol' IS NOT NULL;
```

Expected output: All three counts should be equal.

## Impact
- ✅ Chart entry lines now frozen at signal time
- ✅ Exit lines remain realtime
- ✅ Z-score calculation uses historical entry stats
- ✅ Accurate simulation of real exchange behavior
- ✅ No breaking changes to existing data

## Rollback
If needed, you can remove the backfilled values:

```sql
UPDATE trades
SET strategy_metadata = strategy_metadata - 'spread_mean_at_entry' - 'spread_std_at_entry'
WHERE strategy_metadata IS NOT NULL
  AND strategy_metadata->>'pair_symbol' IS NOT NULL;
```

## Notes
- Trades that already have `spread_mean_at_entry` are skipped
- Only spread-based trades (with `pair_symbol`) are updated
- Safe to run multiple times (idempotent)

