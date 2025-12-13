# Simulator Sanity Checks - Implementation Summary

**Date**: 2025-12-14
**Status**: COMPLETE ✅

## Overview

Comprehensive sanity checks have been added to ALL simulator components to prevent timestamp violations and ensure data integrity. All checks log errors for audit trail and prevent invalid data from being written to the database.

## Critical Rule

**A trade MUST follow this timeline**: `created_at <= filled_at <= closed_at`

Any violation of this rule will:
1. **Block the database update** (trade will not be modified)
2. **Log a detailed error** with trade ID, violation type, and metadata
3. **Continue processing other trades** (fail gracefully)

## Implementation Details

### 1. TypeScript Simulator (`app/api/bot/simulator/auto-close/route.ts`)

#### Functions Added

**`validateTradeTimestamps()`** (Lines 49-93)
- Validates complete timestamp chain
- Returns error message if validation fails, null if valid
- Checks all three conditions: created_at <= filled_at <= closed_at

**`logSimulatorError()`** (Lines 98-114)
- Logs errors with structured format for audit trail
- Includes trade ID, error type, error message, and metadata
- TODO: Consider adding simulator_errors table for persistent tracking

#### Validation Points

**1. Before Filling Trade** (Lines 771-793)
- Validates `filled_at >= created_at`
- Logs `TIMESTAMP_VIOLATION_ON_FILL` error if invalid
- Skips trade update if validation fails

**2. Before Closing Trade** (Lines 867-933)
- Validates complete chain: `created_at <= filled_at <= closed_at`
- Logs `TIMESTAMP_VIOLATION_ON_CLOSE` error if invalid
- Includes exit reason, exit price, and P&L in metadata
- Skips trade update if validation fails

**3. Before Cancelling Filled Trade** (Lines 999-1024)
- Validates complete chain before cancellation
- Logs `TIMESTAMP_VIOLATION_ON_CANCEL` error if invalid
- Includes bars_open and max_bars in metadata
- Skips trade update if validation fails

### 2. Python Simulator (`python/trading_bot/engine/paper_trade_simulator.py`)

#### Methods Added

**`_validate_trade_timestamps()`** (Lines 50-82)
- Python equivalent of TypeScript validation
- Handles ISO format timestamps with timezone
- Returns error message or None

**`_log_simulator_error()`** (Lines 84-99)
- Logs errors using Python logger with structured metadata
- TODO: Consider adding simulator_errors table

#### Validation Points

**1. Before Any Trade Update** (Lines 125-189 in `update_trade_status()`)
- Fetches current trade data from database
- Validates timestamps before applying updates
- Logs `TIMESTAMP_VIOLATION_ON_UPDATE` error if invalid
- Returns False without updating database if validation fails

## Error Types

| Error Type | Description | Logged When |
|------------|-------------|-------------|
| `TIMESTAMP_VIOLATION_ON_FILL` | filled_at < created_at | Trade is being filled |
| `TIMESTAMP_VIOLATION_ON_CLOSE` | closed_at < created_at OR closed_at < filled_at | Trade is being closed (SL/TP hit) |
| `TIMESTAMP_VIOLATION_ON_CANCEL` | Same as close | Trade is being cancelled (max_bars_exceeded) |
| `TIMESTAMP_VIOLATION_ON_UPDATE` | Any timestamp violation | Python simulator updates trade |
| `MISSING_FILLED_AT_ON_CLOSE` | Attempting to close unfilled trade | Trade has closed_at but no filled_at |

## Metadata Logged

Each error includes:
- `trade_id`: Unique trade identifier
- `symbol`: Trading pair
- `created_at`: Trade creation timestamp
- `filled_at`: Trade fill timestamp (if applicable)
- `closed_at`: Trade close timestamp (if applicable)
- Additional context: exit_reason, exit_price, pnl, bars_open, etc.

## Testing

To verify sanity checks are working:

```sql
-- This query should return 0 rows (no timestamp violations)
SELECT COUNT(*) as violations
FROM trades 
WHERE 
  (filled_at IS NOT NULL AND filled_at < created_at) OR
  (closed_at IS NOT NULL AND closed_at < created_at) OR
  (closed_at IS NOT NULL AND filled_at IS NOT NULL AND closed_at < filled_at);
```

## Future Enhancements

1. **Persistent Error Tracking**: Create `simulator_errors` table to store all validation failures
2. **Alerting**: Send notifications when critical errors occur
3. **Metrics**: Track error rates and types over time
4. **Auto-Recovery**: Automatically reset corrupted trades to paper_trade status

## Related Files

- `app/api/bot/simulator/auto-close/route.ts` - TypeScript simulator with sanity checks
- `python/trading_bot/engine/paper_trade_simulator.py` - Python simulator with sanity checks
- `SIMULATOR_AUDIT_REPORT.md` - Complete audit findings
- `SIMULATOR_TEST_PLAN.md` - Test cases and verification queries

