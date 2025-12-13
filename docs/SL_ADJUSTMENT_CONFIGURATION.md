# Stop Loss Adjustment Configuration

## Overview

The SL Adjustment feature allows you to automatically widen stop loss prices before trade execution. This is useful when your strategy has consistently tight stop losses that cause unnecessary losses.

**Key Points:**
- Adjustments happen **before trade execution** (pre-execution)
- Separate from position tightening (which happens on open positions)
- Fully auditable - all adjustments recorded in `sl_adjustments` table
- Per-instance configuration - different instances can have different adjustments
- Configured via UI in Instance Settings → Trading tab

---

## Configuration

### Via UI (Recommended)

1. Open Instance Settings modal
2. Go to **Trading** tab
3. Configure these settings:
   - **sl_adjustment_enabled**: Toggle to enable/disable
   - **sl_adjustment_long_pct**: Percentage to widen SL for LONG trades (default: 1.5)
   - **sl_adjustment_short_pct**: Percentage to widen SL for SHORT trades (default: 1.5)

### Via Database (Direct)

```sql
-- Enable SL adjustment
UPDATE config
SET value = 'true'
WHERE instance_id = 'your-instance-id'
AND key = 'trading.sl_adjustment_enabled';

-- Set LONG adjustment percentage
UPDATE config
SET value = '1.5'
WHERE instance_id = 'your-instance-id'
AND key = 'trading.sl_adjustment_long_pct';

-- Set SHORT adjustment percentage
UPDATE config
SET value = '1.5'
WHERE instance_id = 'your-instance-id'
AND key = 'trading.sl_adjustment_short_pct';
```

### Settings

**trading.sl_adjustment_enabled** (boolean)
- Enable/disable pre-execution SL adjustment
- Default: `false`

**trading.sl_adjustment_long_pct** (number)
- Percentage to widen SL for LONG trades
- Example: `1.5` = 1.5% wider
- Default: `1.5`

**trading.sl_adjustment_short_pct** (number)
- Percentage to widen SL for SHORT trades
- Example: `1.5` = 1.5% wider
- Default: `1.5`

---

## How It Works

### Example: LONG Trade

**Original Recommendation:**
- Entry: 100.00
- Stop Loss: 95.00 (5 points risk)
- Take Profit: 110.00

**With 1.5% Adjustment:**
- Risk = 100.00 - 95.00 = 5.00
- Adjustment = 5.00 × 1.5% = 0.075
- **Adjusted SL = 95.00 - 0.075 = 94.925**

**Result:**
- Original SL: 95.00
- Adjusted SL: 94.925 (0.075 points wider)
- Trade executed with adjusted SL

---

## Audit Trail

All adjustments are recorded in the `sl_adjustments` table:

```sql
SELECT 
    sa.id,
    sa.recommendation_id,
    sa.original_stop_loss,
    sa.adjusted_stop_loss,
    sa.adjustment_value,
    sa.created_at
FROM sl_adjustments sa
WHERE sa.recommendation_id = 'rec_123';
```

### Full Trade History Query

```sql
SELECT 
    t.id as trade_id,
    r.stop_loss as original_rec_sl,
    sa.original_stop_loss,
    sa.adjusted_stop_loss,
    sa.adjustment_value,
    t.stop_loss as executed_sl,
    el.message as tightening_event
FROM trades t
LEFT JOIN recommendations r ON t.recommendation_id = r.id
LEFT JOIN sl_adjustments sa ON r.id = sa.recommendation_id
LEFT JOIN error_logs el ON t.id = el.trade_id 
    AND el.event = 'sl_tightened'
WHERE t.id = 'trade_789'
ORDER BY el.created_at;
```

---

## Disabling

To disable SL adjustment via UI:
1. Open Instance Settings
2. Go to Trading tab
3. Toggle **sl_adjustment_enabled** to OFF
4. Click Save

Or via database:
```sql
UPDATE config
SET value = 'false'
WHERE instance_id = 'your-instance-id'
AND key = 'trading.sl_adjustment_enabled';
```

---

## Testing

1. Open Instance Settings → Trading tab
2. Enable **sl_adjustment_enabled**
3. Set **sl_adjustment_long_pct** and **sl_adjustment_short_pct** to desired values
4. Click Save
5. Start a trading cycle
6. Check logs for: `📊 SL Adjusted: X.XX → Y.YY (Z% wider)`
7. Query `sl_adjustments` table to verify recording:
   ```sql
   SELECT * FROM sl_adjustments
   ORDER BY created_at DESC
   LIMIT 10;
   ```
8. Check trade's `stop_loss` field matches adjusted value

