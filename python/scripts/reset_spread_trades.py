#!/usr/bin/env python3
"""
Reset all spread-based trades back to paper_trade status.

This script:
1. Finds all spread-based trades with status 'filled' or 'closed'
2. Shows a sample and count (dry-run by default)
3. Resets them to paper_trade status while preserving entry data
4. Clears all fill/exit/pnl data

Usage:
  python python/scripts/reset_spread_trades.py --dry-run  # Show what would be reset
  python python/scripts/reset_spread_trades.py --apply    # Actually reset trades
"""

import sys
import os
from pathlib import Path

# Load environment variables from .env.local
from dotenv import load_dotenv
load_dotenv('.env.local')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.db.client import get_connection, release_connection, query, execute

def reset_spread_trades(dry_run: bool = True):
    """Reset all spread-based trades to paper_trade status."""
    
    conn = get_connection()
    
    try:
        print("\n🔍 Finding spread-based trades to reset...\n")
        
        # Get count and status breakdown
        count_result = query(conn, """
            SELECT 
              COUNT(*) as total_count,
              COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_count,
              COUNT(CASE WHEN status = 'filled' THEN 1 END) as filled_count
            FROM trades
            WHERE strategy_type = 'spread_based' 
              AND status IN ('filled', 'closed')
        """)
        
        if not count_result:
            print("✅ No spread-based trades to reset!")
            return
        
        result = count_result[0]
        total_count = result['total_count']
        closed_count = result['closed_count']
        filled_count = result['filled_count']
        
        print(f"📊 Total spread-based trades to reset: {total_count}")
        print(f"   - Closed trades: {closed_count}")
        print(f"   - Filled trades: {filled_count}\n")
        
        if total_count == 0:
            print("✅ No spread-based trades to reset!")
            return
        
        # Show sample
        samples = query(conn, """
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
        """)
        
        print("📋 Sample of spread-based trades to reset:")
        for trade in samples:
            print(f"  {trade['id'][:8]}... {trade['symbol']:10} {trade['side']:4} "
                  f"Entry: {trade['entry_price']:.2f} Exit: {trade['exit_reason']:20} "
                  f"PnL: {trade['pnl']:.2f}")
        print()
        
        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be made\n")
            print("✅ Dry run complete. To apply changes, run:")
            print("   python python/scripts/reset_spread_trades.py --apply\n")
            return
        
        # Ask for confirmation
        response = input(f"⚠️  Reset {total_count} spread-based trades? (yes/no): ").strip().lower()
        
        if response != 'yes':
            print("❌ Cancelled\n")
            return
        
        print("\n⏳ Resetting spread-based trades...\n")
        
        # Reset all spread-based trades to paper_trade status
        # CRITICAL: Preserve entry data (entry_price, stop_loss, take_profit, strategy_metadata)
        execute(conn, """
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
        """)
        
        print(f"✅ Reset {total_count} spread-based trades to paper_trade status\n")
        
        # Verify the reset
        print("✔️ Verifying reset...")
        verify_result = query(conn, """
            SELECT 
              COUNT(*) as total,
              COUNT(CASE WHEN status = 'paper_trade' THEN 1 END) as paper_trade_count,
              COUNT(CASE WHEN filled_at IS NULL THEN 1 END) as unfilled_count
            FROM trades
            WHERE strategy_type = 'spread_based' 
              AND status IN ('paper_trade', 'filled', 'closed')
        """)
        
        if verify_result:
            v = verify_result[0]
            print(f"✅ Verification complete:")
            print(f"   - Total spread trades: {v['total']}")
            print(f"   - Now paper_trade: {v['paper_trade_count']}")
            print(f"   - Unfilled: {v['unfilled_count']}\n")
        
        print("📝 Trades are now ready for simulator re-evaluation:")
        print("   ✓ status: paper_trade")
        print("   ✓ filled_at: NULL")
        print("   ✓ All fill/exit/pnl data: NULL")
        print("   ✓ Entry setup (entry_price, stop_loss, take_profit): INTACT")
        print("   ✓ Strategy metadata: INTACT\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        release_connection(conn)

if __name__ == '__main__':
    dry_run = '--apply' not in sys.argv
    
    if dry_run:
        print("🔍 Running in DRY RUN mode (no changes will be made)")
    
    reset_spread_trades(dry_run=dry_run)

