-- ============================================
-- COMPREHENSIVE AUDIT: Closed Spread-Based Trades
-- ============================================
-- Purpose: Verify accuracy of fill and close timestamps
-- Focus: Identify trades closed on same candle as fill (suspicious pattern)
-- Run with: psql $DATABASE_URL -f scripts/audit_spread_trades.sql

-- ============================================
-- 1. IDENTIFY ALL CLOSED SPREAD-BASED TRADES
-- ============================================
\echo '=== CLOSED SPREAD-BASED TRADES SUMMARY ==='
SELECT 
  COUNT(*) as total_closed_spread_trades,
  COUNT(CASE WHEN filled_at IS NOT NULL THEN 1 END) as with_filled_at,
  COUNT(CASE WHEN closed_at IS NOT NULL THEN 1 END) as with_closed_at,
  COUNT(CASE WHEN filled_at IS NOT NULL AND closed_at IS NOT NULL THEN 1 END) as with_both_timestamps
FROM trades
WHERE status = 'closed' 
  AND strategy_type = 'spread_based'
  AND strategy_metadata IS NOT NULL;

-- ============================================
-- 2. SAME-CANDLE FILL/CLOSE DETECTION (SUSPICIOUS)
-- ============================================
\echo ''
\echo '=== SUSPICIOUS: Trades filled and closed on SAME CANDLE ==='
SELECT 
  id,
  symbol,
  timeframe,
  created_at,
  filled_at,
  closed_at,
  EXTRACT(EPOCH FROM (closed_at - filled_at)) / 60 as minutes_between_fill_close,
  fill_price,
  exit_price,
  pnl,
  pnl_percent,
  exit_reason,
  strategy_name
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND filled_at IS NOT NULL
  AND closed_at IS NOT NULL
  AND DATE_TRUNC('hour', filled_at) = DATE_TRUNC('hour', closed_at)
ORDER BY filled_at DESC
LIMIT 50;

-- ============================================
-- 3. TIME DISTRIBUTION ANALYSIS
-- ============================================
\echo ''
\echo '=== TIME DISTRIBUTION: Fill to Close Duration ==='
SELECT 
  timeframe,
  COUNT(*) as trade_count,
  ROUND(AVG(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 3600)::numeric, 2) as avg_hours_open,
  ROUND(MIN(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 3600)::numeric, 2) as min_hours,
  ROUND(MAX(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 3600)::numeric, 2) as max_hours,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (closed_at - filled_at)) / 3600)::numeric, 2) as median_hours
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND filled_at IS NOT NULL
  AND closed_at IS NOT NULL
GROUP BY timeframe
ORDER BY timeframe;

-- ============================================
-- 4. TIMESTAMP VALIDATION CHECKS
-- ============================================
\echo ''
\echo '=== TIMESTAMP VIOLATIONS: created_at > filled_at or filled_at > closed_at ==='
SELECT 
  id,
  symbol,
  created_at,
  filled_at,
  closed_at,
  CASE 
    WHEN created_at > filled_at THEN 'created_at > filled_at'
    WHEN filled_at > closed_at THEN 'filled_at > closed_at'
    ELSE 'UNKNOWN'
  END as violation_type,
  exit_reason
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND (created_at > filled_at OR filled_at > closed_at)
ORDER BY created_at DESC;

-- ============================================
-- 5. PNL CALCULATION VERIFICATION
-- ============================================
\echo ''
\echo '=== PNL ANALYSIS: Verify calculations against price movements ==='
SELECT 
  id,
  symbol,
  side,
  quantity,
  fill_price,
  exit_price,
  pair_quantity,
  pair_fill_price,
  pair_exit_price,
  pnl,
  pnl_percent,
  exit_reason,
  CASE 
    WHEN side = 'Buy' THEN (exit_price - fill_price) * quantity
    WHEN side = 'Sell' THEN (fill_price - exit_price) * quantity
    ELSE NULL
  END as calculated_main_pnl,
  CASE 
    WHEN pair_quantity IS NOT NULL AND pair_fill_price IS NOT NULL AND pair_exit_price IS NOT NULL THEN
      CASE 
        WHEN side = 'Buy' THEN (pair_fill_price - pair_exit_price) * pair_quantity
        WHEN side = 'Sell' THEN (pair_exit_price - pair_fill_price) * pair_quantity
        ELSE NULL
      END
    ELSE NULL
  END as calculated_pair_pnl
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND filled_at IS NOT NULL
  AND closed_at IS NOT NULL
ORDER BY closed_at DESC
LIMIT 50;

-- ============================================
-- 6. SL/TP HIT VERIFICATION
-- ============================================
\echo ''
\echo '=== SL/TP HIT VERIFICATION ==='
SELECT 
  id,
  symbol,
  side,
  entry_price,
  stop_loss,
  take_profit,
  exit_price,
  exit_reason,
  CASE 
    WHEN side = 'Buy' AND exit_price <= stop_loss THEN 'SL_HIT_VERIFIED'
    WHEN side = 'Buy' AND exit_price >= take_profit THEN 'TP_HIT_VERIFIED'
    WHEN side = 'Sell' AND exit_price >= stop_loss THEN 'SL_HIT_VERIFIED'
    WHEN side = 'Sell' AND exit_price <= take_profit THEN 'TP_HIT_VERIFIED'
    ELSE 'PRICE_MISMATCH'
  END as verification_status
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND filled_at IS NOT NULL
  AND closed_at IS NOT NULL
  AND exit_reason IN ('sl_hit', 'tp_hit')
ORDER BY closed_at DESC
LIMIT 50;

-- ============================================
-- 7. STRATEGY METADATA INSPECTION
-- ============================================
\echo ''
\echo '=== STRATEGY METADATA SAMPLE (First 10 spread trades) ==='
SELECT 
  id,
  symbol,
  strategy_name,
  strategy_metadata
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND strategy_metadata IS NOT NULL
LIMIT 10;

