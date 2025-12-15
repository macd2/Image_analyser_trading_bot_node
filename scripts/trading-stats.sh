#!/bin/bash

# Trading Statistics Analysis Script
# Analyzes trading performance by instance to identify improvement areas
# Distinguishes between paper trades, dry runs, and live trades
# Usage: ./scripts/trading-stats.sh

set -e

# Load environment variables
if [ -f .env.local ]; then
  source .env.local
else
  echo "Error: .env.local not found"
  exit 1
fi

if [ -z "$DATABASE_URL" ]; then
  echo "Error: DATABASE_URL not set in .env.local"
  exit 1
fi

echo "=========================================="
echo "TRADING STATISTICS BY INSTANCE"
echo "=========================================="
echo ""

echo "1. EXECUTION BREAKDOWN (Paper Trades, Dry Runs, Live)"
echo "-------------------------------------------"
psql "$DATABASE_URL" << 'EOF'
SELECT
  i.name,
  COUNT(t.id) as total_generated,
  COUNT(CASE WHEN t.status = 'rejected' THEN 1 END) as rejected,
  COUNT(CASE WHEN (t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL) AND COALESCE(t.dry_run, false) = false THEN 1 END) as live_executed,
  COUNT(CASE WHEN (t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL) AND COALESCE(t.dry_run, false) = true THEN 1 END) as dry_run_executed,
  COUNT(CASE WHEN t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL THEN 1 END) as total_executed,
  ROUND(100.0 * COUNT(CASE WHEN t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL THEN 1 END)::numeric / NULLIF(COUNT(t.id), 0), 2) as execution_rate_pct,
  COUNT(DISTINCT t.symbol) as unique_symbols
FROM instances i
LEFT JOIN runs r ON i.id = r.instance_id
LEFT JOIN cycles c ON r.id = c.run_id
LEFT JOIN trades t ON c.id = t.cycle_id
GROUP BY i.id, i.name
ORDER BY total_generated DESC;
EOF

echo ""
echo "2. EXECUTED TRADES BREAKDOWN (Live vs Dry Run)"
echo "-------------------------------------------"
psql "$DATABASE_URL" << 'EOF'
SELECT
  i.name,
  CASE WHEN COALESCE(t.dry_run, false) = false THEN 'LIVE' ELSE 'DRY RUN' END as trade_type,
  COUNT(*) as count,
  COUNT(CASE WHEN t.side = 'Buy' THEN 1 END) as longs,
  COUNT(CASE WHEN t.side = 'Sell' THEN 1 END) as shorts,
  ROUND(AVG(t.confidence)::numeric, 3) as avg_confidence,
  ROUND(AVG(t.rr_ratio)::numeric, 2) as avg_rr_ratio,
  ROUND(AVG(t.position_size_usd)::numeric, 2) as avg_position_size_usd,
  ROUND(AVG(t.risk_amount_usd)::numeric, 2) as avg_risk_per_trade,
  ROUND(SUM(t.pnl)::numeric, 2) as total_pnl,
  ROUND(AVG(t.pnl_percent)::numeric, 2) as avg_pnl_pct
FROM instances i
LEFT JOIN runs r ON i.id = r.instance_id
LEFT JOIN cycles c ON r.id = c.run_id
LEFT JOIN trades t ON c.id = t.cycle_id
WHERE t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL
GROUP BY i.id, i.name, trade_type
ORDER BY i.name, trade_type DESC;
EOF

echo ""
echo "3. PROFITABILITY ANALYSIS (Executed Trades Only)"
echo "-------------------------------------------"
psql "$DATABASE_URL" << 'EOF'
SELECT
  i.name,
  CASE WHEN COALESCE(t.dry_run, false) = false THEN 'LIVE' ELSE 'DRY RUN' END as trade_type,
  COUNT(*) as total_trades,
  COUNT(CASE WHEN t.pnl > 0 THEN 1 END) as winners,
  COUNT(CASE WHEN t.pnl < 0 THEN 1 END) as losers,
  COUNT(CASE WHEN t.pnl = 0 THEN 1 END) as breakeven,
  ROUND(100.0 * COUNT(CASE WHEN t.pnl > 0 THEN 1 END)::numeric / NULLIF(COUNT(*), 0), 2) as win_rate_pct,
  ROUND(SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END)::numeric, 2) as total_wins_usd,
  ROUND(SUM(CASE WHEN t.pnl < 0 THEN t.pnl ELSE 0 END)::numeric, 2) as total_losses_usd,
  ROUND(SUM(t.pnl)::numeric, 2) as net_pnl_usd,
  ROUND(AVG(CASE WHEN t.pnl > 0 THEN t.pnl_percent ELSE NULL END)::numeric, 2) as avg_win_pct,
  ROUND(AVG(CASE WHEN t.pnl < 0 THEN t.pnl_percent ELSE NULL END)::numeric, 2) as avg_loss_pct
FROM instances i
LEFT JOIN runs r ON i.id = r.instance_id
LEFT JOIN cycles c ON r.id = c.run_id
LEFT JOIN trades t ON c.id = t.cycle_id
WHERE t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL
GROUP BY i.id, i.name, trade_type
ORDER BY i.name, trade_type DESC;
EOF

echo ""
echo "4. TOP REJECTION REASONS (Blocking Execution)"
echo "-------------------------------------------"
psql "$DATABASE_URL" << 'EOF'
SELECT
  i.name,
  t.rejection_reason,
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*)::numeric / SUM(COUNT(*)) OVER (PARTITION BY i.id), 2) as pct_of_rejections
FROM instances i
LEFT JOIN runs r ON i.id = r.instance_id
LEFT JOIN cycles c ON r.id = c.run_id
LEFT JOIN trades t ON c.id = t.cycle_id
WHERE t.status = 'rejected' AND t.rejection_reason IS NOT NULL
GROUP BY i.id, i.name, t.rejection_reason
ORDER BY i.name, count DESC
LIMIT 20;
EOF

echo ""
echo "5. SIGNAL QUALITY ANALYSIS (Rejected vs Executed)"
echo "-------------------------------------------"
psql "$DATABASE_URL" << 'EOF'
SELECT
  i.name,
  'REJECTED' as status,
  COUNT(*) as count,
  ROUND(AVG(t.confidence)::numeric, 3) as avg_confidence,
  ROUND(AVG(t.rr_ratio)::numeric, 2) as avg_rr_ratio,
  ROUND(MIN(t.confidence)::numeric, 3) as min_confidence,
  ROUND(MAX(t.confidence)::numeric, 3) as max_confidence
FROM instances i
LEFT JOIN runs r ON i.id = r.instance_id
LEFT JOIN cycles c ON r.id = c.run_id
LEFT JOIN trades t ON c.id = t.cycle_id
WHERE t.status = 'rejected'
GROUP BY i.id, i.name

UNION ALL

SELECT
  i.name,
  'EXECUTED' as status,
  COUNT(*) as count,
  ROUND(AVG(t.confidence)::numeric, 3) as avg_confidence,
  ROUND(AVG(t.rr_ratio)::numeric, 2) as avg_rr_ratio,
  ROUND(MIN(t.confidence)::numeric, 3) as min_confidence,
  ROUND(MAX(t.confidence)::numeric, 3) as max_confidence
FROM instances i
LEFT JOIN runs r ON i.id = r.instance_id
LEFT JOIN cycles c ON r.id = c.run_id
LEFT JOIN trades t ON c.id = t.cycle_id
WHERE t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL
GROUP BY i.id, i.name

ORDER BY name, status DESC;
EOF

echo ""
echo "=========================================="
echo "SUMMARY & INSIGHTS"
echo "=========================================="
psql "$DATABASE_URL" << 'EOF'
WITH stats AS (
  SELECT
    i.name,
    COUNT(t.id) as total_generated,
    COUNT(CASE WHEN t.status = 'rejected' THEN 1 END) as rejected,
    COUNT(CASE WHEN t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL THEN 1 END) as executed,
    COUNT(CASE WHEN (t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL) AND COALESCE(t.dry_run, false) = false THEN 1 END) as live_trades,
    ROUND(100.0 * COUNT(CASE WHEN t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL THEN 1 END)::numeric / NULLIF(COUNT(t.id), 0), 2) as exec_rate,
    ROUND(AVG(CASE WHEN t.status = 'rejected' THEN t.confidence END)::numeric, 3) as rejected_avg_conf,
    ROUND(AVG(CASE WHEN t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL THEN t.confidence END)::numeric, 3) as executed_avg_conf,
    ROUND(AVG(CASE WHEN t.status = 'rejected' THEN t.rr_ratio END)::numeric, 2) as rejected_avg_rr,
    ROUND(AVG(CASE WHEN t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL THEN t.rr_ratio END)::numeric, 2) as executed_avg_rr,
    ROUND(SUM(CASE WHEN (t.filled_at IS NOT NULL OR t.closed_at IS NOT NULL) AND COALESCE(t.dry_run, false) = false THEN t.pnl ELSE 0 END)::numeric, 2) as live_pnl
  FROM instances i
  LEFT JOIN runs r ON i.id = r.instance_id
  LEFT JOIN cycles c ON r.id = c.run_id
  LEFT JOIN trades t ON c.id = t.cycle_id
  GROUP BY i.id, i.name
)
SELECT
  name,
  total_generated || ' generated' as trades_generated,
  executed || ' executed (' || exec_rate || '%)' as execution,
  live_trades || ' live' as live_trades,
  CASE
    WHEN exec_rate < 10 THEN '🔴 CRITICAL: Very low execution rate'
    WHEN exec_rate < 30 THEN '🟠 WARNING: Low execution rate'
    WHEN exec_rate < 50 THEN '🟡 CAUTION: Below 50% execution'
    ELSE '🟢 GOOD: Healthy execution rate'
  END as execution_health,
  CASE
    WHEN rejected_avg_conf > executed_avg_conf THEN '⚠️  Rejected trades have HIGHER confidence - check filters'
    WHEN rejected_avg_rr < executed_avg_rr THEN '✓ RR ratio filtering working'
    ELSE '✓ Signal quality looks reasonable'
  END as signal_quality,
  CASE
    WHEN live_pnl > 0 THEN '✓ Profitable: $' || live_pnl
    WHEN live_pnl < 0 THEN '✗ Losing: $' || live_pnl
    ELSE '- No live trades yet'
  END as live_performance
FROM stats
ORDER BY total_generated DESC;
EOF

echo ""
echo "=========================================="
echo "Analysis complete!"
echo "=========================================="

