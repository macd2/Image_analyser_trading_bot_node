-- ============================================
-- DETAILED AUDIT: Spread-Based Trade Analysis
-- ============================================
-- Advanced diagnostics for auto-close logic verification

-- ============================================
-- 1. CANDLE-BASED ANALYSIS
-- ============================================
\echo '=== CANDLE DURATION ANALYSIS ==='
SELECT 
  symbol,
  timeframe,
  COUNT(*) as trade_count,
  COUNT(CASE WHEN candles_between_fill_close = 0 THEN 1 END) as same_candle_fills,
  COUNT(CASE WHEN candles_between_fill_close = 1 THEN 1 END) as one_candle_apart,
  COUNT(CASE WHEN candles_between_fill_close > 1 THEN 1 END) as multiple_candles_apart,
  ROUND(100.0 * COUNT(CASE WHEN candles_between_fill_close = 0 THEN 1 END) / COUNT(*), 2) as pct_same_candle
FROM (
  SELECT 
    symbol,
    timeframe,
    filled_at,
    closed_at,
    CASE 
      WHEN timeframe = '1m' THEN FLOOR(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 60)
      WHEN timeframe = '5m' THEN FLOOR(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 300)
      WHEN timeframe = '15m' THEN FLOOR(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 900)
      WHEN timeframe = '1h' THEN FLOOR(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 3600)
      WHEN timeframe = '4h' THEN FLOOR(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 14400)
      WHEN timeframe = '1d' THEN FLOOR(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 86400)
      ELSE 0
    END as candles_between_fill_close
  FROM trades
  WHERE status = 'closed'
    AND strategy_type = 'spread_based'
    AND filled_at IS NOT NULL
    AND closed_at IS NOT NULL
) t
GROUP BY symbol, timeframe
ORDER BY pct_same_candle DESC;

-- ============================================
-- 2. FILL PRICE ACCURACY CHECK
-- ============================================
\echo ''
\echo '=== FILL PRICE ACCURACY: Entry vs Actual Fill ==='
SELECT 
  id,
  symbol,
  entry_price,
  fill_price,
  ABS(entry_price - fill_price) as price_deviation,
  ROUND(100.0 * ABS(entry_price - fill_price) / entry_price, 4) as deviation_pct,
  pair_entry_price,
  pair_fill_price,
  ABS(pair_entry_price - pair_fill_price) as pair_price_deviation,
  filled_at,
  created_at
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND filled_at IS NOT NULL
  AND fill_price IS NOT NULL
  AND ABS(entry_price - fill_price) > 0
ORDER BY deviation_pct DESC
LIMIT 30;

-- ============================================
-- 3. EXIT PRICE VALIDATION
-- ============================================
\echo ''
\echo '=== EXIT PRICE VALIDATION: SL/TP vs Actual Exit ==='
SELECT 
  id,
  symbol,
  side,
  stop_loss,
  take_profit,
  exit_price,
  exit_reason,
  CASE 
    WHEN side = 'Buy' AND exit_reason = 'sl_hit' AND exit_price > stop_loss THEN 'SL_MISMATCH'
    WHEN side = 'Buy' AND exit_reason = 'tp_hit' AND exit_price < take_profit THEN 'TP_MISMATCH'
    WHEN side = 'Sell' AND exit_reason = 'sl_hit' AND exit_price < stop_loss THEN 'SL_MISMATCH'
    WHEN side = 'Sell' AND exit_reason = 'tp_hit' AND exit_price > take_profit THEN 'TP_MISMATCH'
    ELSE 'OK'
  END as validation_status,
  ABS(exit_price - CASE WHEN exit_reason = 'sl_hit' THEN stop_loss ELSE take_profit END) as price_diff
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND exit_reason IN ('sl_hit', 'tp_hit')
  AND exit_price IS NOT NULL
ORDER BY price_diff DESC
LIMIT 30;

-- ============================================
-- 4. PAIR SYMBOL CONSISTENCY
-- ============================================
\echo ''
\echo '=== PAIR SYMBOL CONSISTENCY CHECK ==='
SELECT 
  id,
  symbol,
  strategy_metadata->>'pair_symbol' as pair_symbol,
  pair_quantity,
  pair_fill_price,
  pair_exit_price,
  CASE 
    WHEN pair_quantity IS NULL THEN 'MISSING_PAIR_QTY'
    WHEN pair_fill_price IS NULL THEN 'MISSING_PAIR_FILL'
    WHEN pair_exit_price IS NULL THEN 'MISSING_PAIR_EXIT'
    ELSE 'OK'
  END as data_completeness
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND strategy_metadata IS NOT NULL
ORDER BY closed_at DESC
LIMIT 30;

-- ============================================
-- 5. RISK/REWARD RATIO VERIFICATION
-- ============================================
\echo ''
\echo '=== RISK/REWARD RATIO VERIFICATION ==='
SELECT 
  id,
  symbol,
  entry_price,
  stop_loss,
  take_profit,
  rr_ratio,
  CASE 
    WHEN side = 'Buy' THEN (take_profit - entry_price) / (entry_price - stop_loss)
    WHEN side = 'Sell' THEN (entry_price - take_profit) / (stop_loss - entry_price)
    ELSE NULL
  END as calculated_rr,
  CASE 
    WHEN rr_ratio IS NOT NULL AND calculated_rr IS NOT NULL 
      AND ABS(rr_ratio - calculated_rr) > 0.01 THEN 'MISMATCH'
    ELSE 'OK'
  END as rr_validation
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND entry_price IS NOT NULL
  AND stop_loss IS NOT NULL
  AND take_profit IS NOT NULL
ORDER BY closed_at DESC
LIMIT 30;

-- ============================================
-- 6. SUMMARY STATISTICS
-- ============================================
\echo ''
\echo '=== SUMMARY STATISTICS ==='
SELECT 
  COUNT(*) as total_trades,
  COUNT(CASE WHEN exit_reason = 'tp_hit' THEN 1 END) as tp_hits,
  COUNT(CASE WHEN exit_reason = 'sl_hit' THEN 1 END) as sl_hits,
  COUNT(CASE WHEN exit_reason NOT IN ('tp_hit', 'sl_hit') THEN 1 END) as other_exits,
  ROUND(AVG(pnl_percent), 4) as avg_pnl_pct,
  ROUND(STDDEV(pnl_percent), 4) as stddev_pnl_pct,
  ROUND(MIN(pnl_percent), 4) as min_pnl_pct,
  ROUND(MAX(pnl_percent), 4) as max_pnl_pct,
  COUNT(CASE WHEN pnl > 0 THEN 1 END) as winning_trades,
  COUNT(CASE WHEN pnl < 0 THEN 1 END) as losing_trades,
  ROUND(100.0 * COUNT(CASE WHEN pnl > 0 THEN 1 END) / COUNT(*), 2) as win_rate_pct
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based';

