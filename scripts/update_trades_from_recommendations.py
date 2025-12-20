"""
Update trades table with corrected prices from recommendations.

This script:
1. Finds all trades that correspond to updated recommendations
2. Updates entry_price, stop_loss, take_profit, and rr_ratio in trades table
3. Logs all changes for verification
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from trading_bot.db.client import get_connection, release_connection, query, execute


def main():
    conn = get_connection()

    try:
        # Get all cointegration recommendations that were updated
        recs = query(conn,
            "SELECT id, symbol, entry_price, stop_loss, take_profit, risk_reward, created_at FROM recommendations WHERE strategy_metadata IS NOT NULL AND recommendation != 'HOLD'",
            ())

        print(f"Found {len(recs)} cointegration recommendations\n")

        updated_count = 0
        error_count = 0

        for rec in recs:
            rec_id = rec['id']
            symbol = rec['symbol']
            entry = rec['entry_price']
            sl = rec['stop_loss']
            tp = rec['take_profit']
            rr = rec['risk_reward']
            created_at = rec['created_at']

            # Find trades for this recommendation
            # First try by recommendation_id
            trades = query(conn,
                "SELECT id, symbol FROM trades WHERE recommendation_id = %s",
                (rec_id,))

            # If not found, try by symbol and strategy_type and creation time (within 1 minute)
            if not trades:
                trades = query(conn,
                    """SELECT id, symbol FROM trades
                       WHERE symbol = %s AND strategy_type = 'spread_based'
                       AND created_at >= %s - INTERVAL '1 minute'
                       AND created_at <= %s + INTERVAL '1 minute'
                       LIMIT 1""",
                    (symbol, created_at, created_at))

            if not trades:
                continue

            # Update each trade with the new prices
            for trade in trades:
                trade_id = trade['id']

                try:
                    execute(conn,
                        """UPDATE trades
                           SET entry_price = %s, stop_loss = %s, take_profit = %s, rr_ratio = %s
                           WHERE id = %s""",
                        (entry, sl, tp, rr, trade_id))

                    updated_count += 1
                    print(f"✅ Updated trade {trade_id[:8]}... ({symbol})")
                    print(f"   Entry: {entry:.6f}, SL: {sl:.6f}, TP: {tp:.6f}, RR: {rr:.4f}")

                except Exception as e:
                    error_count += 1
                    print(f"❌ Error updating trade {trade_id}: {e}")
        
        print(f"\n{'='*60}")
        print(f"✅ Updated: {updated_count}")
        print(f"❌ Errors: {error_count}")
        
    finally:
        release_connection(conn)


if __name__ == "__main__":
    main()

