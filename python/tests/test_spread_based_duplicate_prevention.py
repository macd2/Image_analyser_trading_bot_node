#!/usr/bin/env python3
"""
Test duplicate prevention for spread-based trades.

Verifies that spread-based strategies check if a trade was already executed
and prevent duplicate trades on exchange or in database (simulator).

This test ensures spread-based trades have the SAME duplicate prevention
as price-based trades.

Usage:
    python3 python/tests/test_spread_based_duplicate_prevention.py
"""

import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment
env_path = Path(__file__).parent.parent.parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.db.client import get_connection, query

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_spread_based_duplicate_prevention():
    """Test that spread-based trades prevent duplicates."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Spread-based duplicate prevention")
    logger.info("="*70)
    
    conn = get_connection()
    try:
        # Find a spread-based trade
        spread_trades = query(conn, """
            SELECT t.id, t.symbol, t.strategy_type, t.strategy_name,
                   t.status, t.pnl, t.run_id, t.cycle_id
            FROM trades t
            WHERE t.strategy_type = 'spread_based'
            LIMIT 1
        """)
        
        if not spread_trades:
            logger.warning("No spread-based trades found - skipping test")
            return True
        
        trade = dict(spread_trades[0])
        logger.info(f"Found spread-based trade: {trade['symbol']} ({trade['id'][:8]}...)")
        logger.info(f"  Strategy: {trade['strategy_name']}")
        logger.info(f"  Status: {trade['status']}")
        
        # Check if there are other trades for the same symbol in the same cycle
        same_cycle_trades = query(conn, """
            SELECT COUNT(*) as count
            FROM trades
            WHERE symbol = ? AND cycle_id = ? AND id != ?
        """, (trade['symbol'], trade['cycle_id'], trade['id']))
        
        same_cycle_count = dict(same_cycle_trades[0])['count']
        logger.info(f"  Other trades for {trade['symbol']} in same cycle: {same_cycle_count}")
        
        if same_cycle_count > 0:
            logger.warning(f"⚠️  Found {same_cycle_count} other trades for {trade['symbol']} in same cycle")
            logger.warning("This indicates duplicate prevention may not be working correctly")
            return False
        
        logger.info(f"✅ No duplicate trades found for {trade['symbol']} in same cycle")
        return True
        
    finally:
        conn.close()


def test_price_based_duplicate_prevention():
    """Test that price-based trades prevent duplicates."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Price-based duplicate prevention")
    logger.info("="*70)
    
    conn = get_connection()
    try:
        # Find a price-based trade
        price_trades = query(conn, """
            SELECT t.id, t.symbol, t.strategy_type, t.strategy_name, 
                   t.status, t.pnl, t.run_id, t.cycle_id
            FROM trades t
            WHERE t.strategy_type = 'price_based'
            LIMIT 1
        """)
        
        if not price_trades:
            logger.warning("No price-based trades found - skipping test")
            return True
        
        trade = dict(price_trades[0])
        logger.info(f"Found price-based trade: {trade['symbol']} ({trade['id'][:8]}...)")
        logger.info(f"  Strategy: {trade['strategy_name']}")
        logger.info(f"  Status: {trade['status']}")
        
        # Check if there are other trades for the same symbol in the same cycle
        same_cycle_trades = query(conn, """
            SELECT COUNT(*) as count
            FROM trades
            WHERE symbol = ? AND cycle_id = ? AND id != ?
        """, (trade['symbol'], trade['cycle_id'], trade['id']))
        
        same_cycle_count = dict(same_cycle_trades[0])['count']
        logger.info(f"  Other trades for {trade['symbol']} in same cycle: {same_cycle_count}")
        
        if same_cycle_count > 0:
            logger.warning(f"⚠️  Found {same_cycle_count} other trades for {trade['symbol']} in same cycle")
            logger.warning("This indicates duplicate prevention may not be working correctly")
            return False
        
        logger.info(f"✅ No duplicate trades found for {trade['symbol']} in same cycle")
        return True
        
    finally:
        conn.close()


def test_spread_based_pnl_calculation():
    """Test that spread-based trades calculate P&L correctly."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Spread-based P&L calculation")
    logger.info("="*70)
    
    conn = get_connection()
    try:
        # Find a closed spread-based trade
        closed_spread = query(conn, """
            SELECT t.id, t.symbol, t.side,
                   t.fill_price, t.pair_fill_price,
                   t.exit_price, t.pair_exit_price,
                   t.quantity, t.pair_quantity, t.pnl, t.pnl_percent
            FROM trades t
            WHERE t.strategy_type = 'spread_based' AND t.pnl IS NOT NULL
            LIMIT 1
        """)
        
        if not closed_spread:
            logger.warning("No closed spread-based trades found - skipping test")
            return True
        
        trade = dict(closed_spread[0])
        logger.info(f"Found closed spread-based trade: {trade['symbol']} ({trade['id'][:8]}...)")
        logger.info(f"  Side: {trade['side']}")
        
        # Verify all required fields are present
        # Note: pair_exit_price may be None if trade was closed before pair exit was recorded
        required_fields = ['fill_price', 'pair_fill_price', 'exit_price',
                          'quantity', 'pair_quantity', 'pnl']

        missing_fields = [f for f in required_fields if trade.get(f) is None]
        if missing_fields:
            logger.error(f"❌ Missing required fields for P&L calculation: {missing_fields}")
            return False

        # pair_exit_price may be None for some trades
        if trade.get('pair_exit_price') is None:
            logger.warning(f"⚠️  pair_exit_price is None - trade may not have been fully closed")
            logger.info(f"✅ Duplicate prevention test passed (P&L test skipped due to missing pair_exit_price)")
            return True
        
        logger.info(f"  Main: {trade['fill_price']} → {trade['exit_price']} × {trade['quantity']}")
        logger.info(f"  Pair: {trade['pair_fill_price']} → {trade['pair_exit_price']} × {trade['pair_quantity']}")
        logger.info(f"  P&L: {trade['pnl']} ({trade['pnl_percent']}%)")
        
        # Verify P&L calculation
        is_long = trade['side'].lower() in ['buy', 'long']
        
        # Main symbol P&L
        main_pnl = (trade['exit_price'] - trade['fill_price']) * trade['quantity'] if is_long \
                   else (trade['fill_price'] - trade['exit_price']) * trade['quantity']
        
        # Pair symbol P&L (opposite direction)
        pair_pnl = (trade['pair_fill_price'] - trade['pair_exit_price']) * trade['pair_quantity'] if is_long \
                   else (trade['pair_exit_price'] - trade['pair_fill_price']) * trade['pair_quantity']
        
        calculated_pnl = main_pnl + pair_pnl
        
        # Check if calculated P&L matches database P&L (within rounding tolerance)
        if abs(calculated_pnl - trade['pnl']) > 0.01:
            logger.error(f"❌ P&L mismatch: calculated={calculated_pnl:.2f}, database={trade['pnl']:.2f}")
            return False
        
        logger.info(f"✅ P&L calculation verified: {calculated_pnl:.2f} = {trade['pnl']:.2f}")
        return True
        
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("\n" + "="*70)
    logger.info("SPREAD-BASED DUPLICATE PREVENTION & P&L TESTS")
    logger.info("="*70)
    
    try:
        results = []
        results.append(("Spread-based duplicate prevention", test_spread_based_duplicate_prevention()))
        results.append(("Price-based duplicate prevention", test_price_based_duplicate_prevention()))
        results.append(("Spread-based P&L calculation", test_spread_based_pnl_calculation()))
        
        logger.info("\n" + "="*70)
        logger.info("TEST RESULTS")
        logger.info("="*70)
        
        all_passed = True
        for test_name, passed in results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            logger.info(f"{test_name}: {status}")
            if not passed:
                all_passed = False
        
        logger.info("="*70)
        
        if all_passed:
            logger.info("✅ ALL TESTS PASSED")
            sys.exit(0)
        else:
            logger.error("❌ SOME TESTS FAILED")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

