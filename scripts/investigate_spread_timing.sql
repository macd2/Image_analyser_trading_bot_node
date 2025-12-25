-- Investigation: Suspicious timing patterns in spread-based paper trades
-- Focus: Trades filled and closed within unusually short timeframes

-- Query 1: Basic timing analysis for all closed spread-based trades
\echo '=== QUERY 1: Timing Analysis for Closed Spread-Based Trades ==='
SELECT
  id,
  symbol,
  strategy_metadata::jsonb->>'pair_symbol' as pair_symbol,
  status,
  created_at,
  filled_at,
  closed_at,
  exit_reason,
  ROUND(EXTRACT(EPOCH FROM (filled_at - created_at)) / 60, 2) as minutes_to_fill,
  ROUND(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 60, 2) as minutes_filled_to_close,
  ROUND(EXTRACT(EPOCH FROM (closed_at - created_at)) / 60, 2) as total_minutes,
  timeframe,
  ROUND(pnl::numeric, 4) as pnl,
  ROUND(pnl_percent::numeric, 2) as pnl_percent
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND strategy_metadata IS NOT NULL
  AND strategy_metadata::jsonb->>'pair_symbol' IS NOT NULL
  AND closed_at IS NOT NULL
ORDER BY closed_at DESC
LIMIT 30;

\echo ''
\echo '=== QUERY 2: Trades Closed Within Same Candle (Suspicious) ==='
-- For 1h timeframe, same candle = closed within 60 minutes of fill
SELECT
  id,
  symbol,
  strategy_metadata::jsonb->>'pair_symbol' as pair_symbol,
  timeframe,
  created_at,
  filled_at,
  closed_at,
  exit_reason,
  ROUND(EXTRACT(EPOCH FROM (filled_at - created_at)) / 60, 2) as minutes_to_fill,
  ROUND(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 60, 2) as minutes_filled_to_close,
  ROUND(pnl_percent::numeric, 2) as pnl_percent
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND filled_at IS NOT NULL
  AND closed_at IS NOT NULL
  AND EXTRACT(EPOCH FROM (closed_at - filled_at)) < 3600  -- Less than 1 hour
ORDER BY (closed_at - filled_at) ASC;

\echo ''
\echo '=== QUERY 3: Trades Filled Immediately (Within 1 Candle) ==='
SELECT
  id,
  symbol,
  strategy_metadata::jsonb->>'pair_symbol' as pair_symbol,
  timeframe,
  created_at,
  filled_at,
  ROUND(EXTRACT(EPOCH FROM (filled_at - created_at)) / 60, 2) as minutes_to_fill,
  entry_price,
  fill_price,
  status
FROM trades
WHERE strategy_type = 'spread_based'
  AND filled_at IS NOT NULL
  AND EXTRACT(EPOCH FROM (filled_at - created_at)) < 3600  -- Less than 1 hour
ORDER BY (filled_at - created_at) ASC
LIMIT 20;

\echo ''
\echo '=== QUERY 4: Exit Reason Distribution for Spread-Based Trades ==='
SELECT 
  exit_reason,
  COUNT(*) as count,
  ROUND(AVG(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 60), 2) as avg_minutes_to_close,
  ROUND(AVG(pnl_percent)::numeric, 2) as avg_pnl_percent
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND closed_at IS NOT NULL
  AND filled_at IS NOT NULL
GROUP BY exit_reason
ORDER BY count DESC;

\echo ''
\echo '=== QUERY 5: Timestamp Validation - Check for Invalid Sequences ==='
SELECT 
  id,
  symbol,
  created_at,
  filled_at,
  closed_at,
  CASE 
    WHEN filled_at < created_at THEN 'ERROR: filled_at before created_at'
    WHEN closed_at < filled_at THEN 'ERROR: closed_at before filled_at'
    WHEN closed_at < created_at THEN 'ERROR: closed_at before created_at'
    ELSE 'OK'
  END as timestamp_validation
FROM trades
WHERE strategy_type = 'spread_based'
  AND status = 'closed'
  AND (filled_at < created_at OR closed_at < filled_at OR closed_at < created_at);

\echo ''
\echo '=== QUERY 6: Strategy Metadata Analysis ==='
SELECT
  id,
  symbol,
  strategy_metadata::jsonb->>'pair_symbol' as pair_symbol,
  strategy_metadata::jsonb->>'z_score_at_entry' as z_score_entry,
  strategy_metadata::jsonb->>'z_exit_threshold' as z_exit_threshold,
  strategy_metadata::jsonb->>'beta' as beta,
  exit_reason,
  ROUND(EXTRACT(EPOCH FROM (closed_at - filled_at)) / 60, 2) as minutes_to_close
FROM trades
WHERE status = 'closed'
  AND strategy_type = 'spread_based'
  AND closed_at IS NOT NULL
ORDER BY closed_at DESC
LIMIT 20;

