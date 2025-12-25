#!/bin/bash

# Reset all spread-based trades back to paper_trade status
# This script:
# 1. Shows a sample and count of spread-based trades (dry-run by default)
# 2. Resets them to paper_trade status while preserving entry data
# 3. Clears all fill/exit/pnl data

set -e

# Load environment
if [ -f .env.local ]; then
  export $(grep -v '^#' .env.local | grep -v '^$' | xargs)
fi

DRY_RUN=true
if [ "$1" == "--apply" ]; then
  DRY_RUN=false
fi

echo ""
echo "🔍 Finding spread-based trades to reset..."
echo ""

# Get count and status breakdown
COUNT_RESULT=$(psql "$DATABASE_URL" -t -c "
  SELECT 
    COUNT(*) as total_count,
    COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_count,
    COUNT(CASE WHEN status = 'filled' THEN 1 END) as filled_count
  FROM trades
  WHERE strategy_type = 'spread_based' 
    AND status IN ('filled', 'closed')
")

TOTAL_COUNT=$(echo "$COUNT_RESULT" | awk '{print $1}')
CLOSED_COUNT=$(echo "$COUNT_RESULT" | awk '{print $2}')
FILLED_COUNT=$(echo "$COUNT_RESULT" | awk '{print $3}')

echo "📊 Total spread-based trades to reset: $TOTAL_COUNT"
echo "   - Closed trades: $CLOSED_COUNT"
echo "   - Filled trades: $FILLED_COUNT"
echo ""

if [ "$TOTAL_COUNT" -eq 0 ]; then
  echo "✅ No spread-based trades to reset!"
  exit 0
fi

# Show sample
echo "📋 Sample of spread-based trades to reset:"
psql "$DATABASE_URL" -c "
  SELECT 
    id, 
    symbol, 
    side, 
    entry_price, 
    quantity, 
    stop_loss, 
    take_profit,
    status, 
    exit_reason,
    pnl, 
    pnl_percent
  FROM trades
  WHERE strategy_type = 'spread_based' 
    AND status IN ('filled', 'closed')
  ORDER BY created_at DESC
  LIMIT 5
"
echo ""

if [ "$DRY_RUN" = true ]; then
  echo "🔍 DRY RUN MODE - No changes will be made"
  echo ""
  echo "✅ Dry run complete. To apply changes, run:"
  echo "   bash scripts/reset-spread-trades.sh --apply"
  echo ""
  exit 0
fi

# Ask for confirmation
read -p "⚠️  Reset $TOTAL_COUNT spread-based trades? (yes/no): " -r RESPONSE
echo ""

if [ "$RESPONSE" != "yes" ]; then
  echo "❌ Cancelled"
  echo ""
  exit 0
fi

echo "⏳ Resetting spread-based trades..."
echo ""

# Reset all spread-based trades to paper_trade status
# CRITICAL: Preserve entry data (entry_price, stop_loss, take_profit, strategy_metadata)
psql "$DATABASE_URL" -c "
  UPDATE trades
  SET
    status = 'paper_trade',
    fill_price = NULL,
    fill_quantity = NULL,
    fill_time = NULL,
    filled_at = NULL,
    pair_fill_price = NULL,
    exit_price = NULL,
    pair_exit_price = NULL,
    exit_reason = NULL,
    closed_at = NULL,
    pnl = NULL,
    pnl_percent = NULL,
    avg_exit_price = NULL,
    closed_size = NULL,
    updated_at = CURRENT_TIMESTAMP
  WHERE strategy_type = 'spread_based' 
    AND status IN ('filled', 'closed')
"

echo "✅ Reset $TOTAL_COUNT spread-based trades to paper_trade status"
echo ""

# Verify the reset
echo "✔️ Verifying reset..."
VERIFY_RESULT=$(psql "$DATABASE_URL" -t -c "
  SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN status = 'paper_trade' THEN 1 END) as paper_trade_count,
    COUNT(CASE WHEN filled_at IS NULL THEN 1 END) as unfilled_count
  FROM trades
  WHERE strategy_type = 'spread_based' 
    AND status IN ('paper_trade', 'filled', 'closed')
")

VERIFY_TOTAL=$(echo "$VERIFY_RESULT" | awk '{print $1}')
VERIFY_PAPER=$(echo "$VERIFY_RESULT" | awk '{print $2}')
VERIFY_UNFILLED=$(echo "$VERIFY_RESULT" | awk '{print $3}')

echo "✅ Verification complete:"
echo "   - Total spread trades: $VERIFY_TOTAL"
echo "   - Now paper_trade: $VERIFY_PAPER"
echo "   - Unfilled: $VERIFY_UNFILLED"
echo ""

echo "📝 Trades are now ready for simulator re-evaluation:"
echo "   ✓ status: paper_trade"
echo "   ✓ filled_at: NULL"
echo "   ✓ All fill/exit/pnl data: NULL"
echo "   ✓ Entry setup (entry_price, stop_loss, take_profit): INTACT"
echo "   ✓ Strategy metadata: INTACT"
echo ""

