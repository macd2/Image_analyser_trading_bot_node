#!/bin/bash

# Trading Statistics Analysis Script
# Analyzes trading performance by instance to identify improvement areas
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

echo "1. OVERVIEW STATS"
echo "-------------------------------------------"
psql "$DATABASE_URL" << 'EOF'
SELECT 
  i.id,
  i.name,
  COUNT(t.id) as total_trades,
  COUNT(CASE WHEN t.status = 'paper_trade' THEN 1 END) as executed_trades,
  COUNT(CASE WHEN t.status = 'rejected' THEN 1 END) as rejected_trades,
  ROUND(100.0 * COUNT(CASE WHEN t.status = 'paper_trade' THEN 1 END)::numeric / NULLIF(COUNT(t.id), 0), 2) as execution_rate_pct,
  COUNT(CASE WHEN t.status = 'paper_trade' AND t.side = 'Buy' THEN 1 END) as long_trades,
  COUNT(CASE WHEN t.status = 'paper_trade' AND t.side = 'Sell' THEN 1 END) as short_trades,
  COUNT(DISTINCT t.symbol) as unique_symbols,
  ROUND(AVG(CASE WHEN t.status = 'paper_trade' THEN t.confidence END)::numeric, 3) as avg_confidence,
  ROUND(AVG(CASE WHEN t.status = 'paper_trade' THEN t.rr_ratio END)::numeric, 2) as avg_rr_ratio,
  ROUND(AVG(CASE WHEN t.status = 'paper_trade' THEN t.position_size_usd END)::numeric, 2) as avg_position_size_usd,
  ROUND(AVG(CASE WHEN t.status = 'paper_trade' THEN t.risk_amount_usd END)::numeric, 2) as avg_risk_per_trade
FROM instances i
LEFT JOIN runs r ON i.id = r.instance_id
LEFT JOIN cycles c ON r.id = c.run_id
LEFT JOIN trades t ON c.id = t.cycle_id
GROUP BY i.id, i.name
ORDER BY total_trades DESC;
EOF

echo ""
echo "2. WIN/LOSS ANALYSIS"
echo "-------------------------------------------"
psql "$DATABASE_URL" << 'EOF'
SELECT 
  i.id,
  i.name,
  COUNT(CASE WHEN t.status = 'paper_trade' THEN 1 END) as total_executed,
  COUNT(CASE WHEN t.status = 'paper_trade' AND t.pnl > 0 THEN 1 END) as winning_trades,
  COUNT(CASE WHEN t.status = 'paper_trade' AND t.pnl < 0 THEN 1 END) as losing_trades,
  COUNT(CASE WHEN t.status = 'paper_trade' AND t.pnl = 0 THEN 1 END) as breakeven_trades,
  ROUND(100.0 * COUNT(CASE WHEN t.status = 'paper_trade' AND t.pnl > 0 THEN 1 END)::numeric / NULLIF(COUNT(CASE WHEN t.status = 'paper_trade' THEN 1 END), 0), 2) as win_rate_pct,
  ROUND(SUM(CASE WHEN t.status = 'paper_trade' AND t.pnl > 0 THEN t.pnl ELSE 0 END)::numeric, 2) as total_wins_usd,
  ROUND(SUM(CASE WHEN t.status = 'paper_trade' AND t.pnl < 0 THEN t.pnl ELSE 0 END)::numeric, 2) as total_losses_usd,
  ROUND(SUM(CASE WHEN t.status = 'paper_trade' THEN t.pnl ELSE 0 END)::numeric, 2) as net_pnl_usd,
  ROUND(AVG(CASE WHEN t.status = 'paper_trade' AND t.pnl > 0 THEN t.pnl_percent ELSE NULL END)::numeric, 2) as avg_win_pct,
  ROUND(AVG(CASE WHEN t.status = 'paper_trade' AND t.pnl < 0 THEN t.pnl_percent ELSE NULL END)::numeric, 2) as avg_loss_pct
FROM instances i
LEFT JOIN runs r ON i.id = r.instance_id
LEFT JOIN cycles c ON r.id = c.run_id
LEFT JOIN trades t ON c.id = t.cycle_id
GROUP BY i.id, i.name
ORDER BY total_executed DESC;
EOF

echo ""
echo "3. TOP REJECTION REASONS"
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
LIMIT 30;
EOF

echo ""
echo "=========================================="
echo "Analysis complete!"
echo "=========================================="

