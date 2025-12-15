-- Backfill position sizing metrics for trades
-- This script calculates position_size_usd and risk_amount_usd from existing trade data

-- Update position_size_usd = entry_price * quantity
UPDATE trades
SET position_size_usd = entry_price * quantity
WHERE position_size_usd IS NULL
  AND entry_price > 0
  AND quantity > 0;

-- Update risk_amount_usd based on side
-- For LONG (Buy): risk = quantity * (entry_price - stop_loss)
-- For SHORT (Sell): risk = quantity * (stop_loss - entry_price)
UPDATE trades
SET risk_amount_usd = CASE
  WHEN side = 'Buy' THEN quantity * (entry_price - stop_loss)
  WHEN side = 'Sell' THEN quantity * (stop_loss - entry_price)
  ELSE 0
END
WHERE risk_amount_usd IS NULL
  AND entry_price > 0
  AND stop_loss > 0
  AND quantity > 0;

-- Set sizing_method to 'fixed' for all backfilled trades (since we don't have Kelly data)
UPDATE trades
SET sizing_method = 'fixed'
WHERE sizing_method IS NULL
  AND (position_size_usd IS NOT NULL OR risk_amount_usd IS NOT NULL);

-- Verify the backfill
SELECT 
  COUNT(*) as total_trades,
  COUNT(CASE WHEN position_size_usd IS NOT NULL THEN 1 END) as with_position_size,
  COUNT(CASE WHEN risk_amount_usd IS NOT NULL THEN 1 END) as with_risk_amount,
  COUNT(CASE WHEN sizing_method IS NOT NULL THEN 1 END) as with_sizing_method
FROM trades;

