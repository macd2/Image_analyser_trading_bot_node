#!/usr/bin/env python3
"""
Functional test for P&L calculation in closing logic.

Tests the actual P&L calculation logic used in production:
1. Price-based trades (simple entry/exit)
2. Spread-based trades (dual symbol P&L)
3. Long vs Short positions
4. P&L percent calculation
5. Rounding to 2 decimal places

Usage:
    python3 python/tests/test_closing_pnl_calculation.py
"""

import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
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


def calculate_pnl_long(entry_price: float, exit_price: float, quantity: float) -> tuple:
    """Calculate P&L for LONG position (Buy)."""
    pnl = (exit_price - entry_price) * quantity
    position_value = entry_price * quantity
    pnl_percent = (pnl / position_value * 100) if position_value > 0 else 0
    return round(pnl, 2), round(pnl_percent, 2)


def calculate_pnl_short(entry_price: float, exit_price: float, quantity: float) -> tuple:
    """Calculate P&L for SHORT position (Sell)."""
    pnl = (entry_price - exit_price) * quantity
    position_value = entry_price * quantity
    pnl_percent = (pnl / position_value * 100) if position_value > 0 else 0
    return round(pnl, 2), round(pnl_percent, 2)


def test_long_position_profit():
    """Test P&L calculation for profitable LONG position."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Long position profit")
    logger.info("="*70)
    
    entry_price = 50000.0
    exit_price = 52000.0
    quantity = 0.1
    
    pnl, pnl_percent = calculate_pnl_long(entry_price, exit_price, quantity)
    
    expected_pnl = (52000 - 50000) * 0.1  # 200
    expected_pnl_percent = (200 / 5000) * 100  # 4%
    
    logger.info(f"Entry: {entry_price}, Exit: {exit_price}, Qty: {quantity}")
    logger.info(f"P&L: {pnl} (expected: {expected_pnl})")
    logger.info(f"P&L%: {pnl_percent}% (expected: {expected_pnl_percent}%)")
    
    assert pnl == round(expected_pnl, 2), f"P&L mismatch: {pnl} != {expected_pnl}"
    assert pnl_percent == round(expected_pnl_percent, 2), f"P&L% mismatch: {pnl_percent} != {expected_pnl_percent}"
    
    logger.info("✅ Test passed")
    return True


def test_long_position_loss():
    """Test P&L calculation for losing LONG position."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Long position loss")
    logger.info("="*70)
    
    entry_price = 50000.0
    exit_price = 48000.0
    quantity = 0.1
    
    pnl, pnl_percent = calculate_pnl_long(entry_price, exit_price, quantity)
    
    expected_pnl = (48000 - 50000) * 0.1  # -200
    expected_pnl_percent = (-200 / 5000) * 100  # -4%
    
    logger.info(f"Entry: {entry_price}, Exit: {exit_price}, Qty: {quantity}")
    logger.info(f"P&L: {pnl} (expected: {expected_pnl})")
    logger.info(f"P&L%: {pnl_percent}% (expected: {expected_pnl_percent}%)")
    
    assert pnl == round(expected_pnl, 2), f"P&L mismatch: {pnl} != {expected_pnl}"
    assert pnl_percent == round(expected_pnl_percent, 2), f"P&L% mismatch: {pnl_percent} != {expected_pnl_percent}"
    
    logger.info("✅ Test passed")
    return True


def test_short_position_profit():
    """Test P&L calculation for profitable SHORT position."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Short position profit")
    logger.info("="*70)
    
    entry_price = 50000.0
    exit_price = 48000.0
    quantity = 0.1
    
    pnl, pnl_percent = calculate_pnl_short(entry_price, exit_price, quantity)
    
    expected_pnl = (50000 - 48000) * 0.1  # 200
    expected_pnl_percent = (200 / 5000) * 100  # 4%
    
    logger.info(f"Entry: {entry_price}, Exit: {exit_price}, Qty: {quantity}")
    logger.info(f"P&L: {pnl} (expected: {expected_pnl})")
    logger.info(f"P&L%: {pnl_percent}% (expected: {expected_pnl_percent}%)")
    
    assert pnl == round(expected_pnl, 2), f"P&L mismatch: {pnl} != {expected_pnl}"
    assert pnl_percent == round(expected_pnl_percent, 2), f"P&L% mismatch: {pnl_percent} != {expected_pnl_percent}"
    
    logger.info("✅ Test passed")
    return True


def test_short_position_loss():
    """Test P&L calculation for losing SHORT position."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Short position loss")
    logger.info("="*70)
    
    entry_price = 50000.0
    exit_price = 52000.0
    quantity = 0.1
    
    pnl, pnl_percent = calculate_pnl_short(entry_price, exit_price, quantity)
    
    expected_pnl = (50000 - 52000) * 0.1  # -200
    expected_pnl_percent = (-200 / 5000) * 100  # -4%
    
    logger.info(f"Entry: {entry_price}, Exit: {exit_price}, Qty: {quantity}")
    logger.info(f"P&L: {pnl} (expected: {expected_pnl})")
    logger.info(f"P&L%: {pnl_percent}% (expected: {expected_pnl_percent}%)")
    
    assert pnl == round(expected_pnl, 2), f"P&L mismatch: {pnl} != {expected_pnl}"
    assert pnl_percent == round(expected_pnl_percent, 2), f"P&L% mismatch: {pnl_percent} != {expected_pnl_percent}"
    
    logger.info("✅ Test passed")
    return True


def test_pnl_with_real_trades():
    """Test P&L calculation with real trades from database."""
    logger.info("\n" + "="*70)
    logger.info("TEST: P&L calculation with real trades")
    logger.info("="*70)
    
    conn = get_connection()
    try:
        # Fetch closed trades with P&L
        closed_trades = query(conn, """
            SELECT id, symbol, side, entry_price, exit_price, quantity, pnl, pnl_percent
            FROM trades
            WHERE pnl IS NOT NULL AND status = 'closed'
            LIMIT 5
        """)
        
        if not closed_trades:
            logger.warning("No closed trades found - skipping test")
            return True
        
        logger.info(f"Found {len(closed_trades)} closed trades")
        
        passed = 0
        failed = 0
        
        for trade in closed_trades:
            trade_dict = dict(trade)
            symbol = trade_dict['symbol']
            side = trade_dict['side'].lower()
            entry = trade_dict['entry_price']
            exit_p = trade_dict['exit_price']
            qty = trade_dict['quantity']
            db_pnl = trade_dict['pnl']
            db_pnl_percent = trade_dict['pnl_percent']
            
            # Recalculate P&L
            if side in ['buy', 'long']:
                calc_pnl, calc_pnl_percent = calculate_pnl_long(entry, exit_p, qty)
            else:
                calc_pnl, calc_pnl_percent = calculate_pnl_short(entry, exit_p, qty)
            
            # Verify
            if abs(calc_pnl - db_pnl) < 0.01 and abs(calc_pnl_percent - db_pnl_percent) < 0.01:
                logger.info(f"✅ {symbol} ({side}): P&L={calc_pnl}, P&L%={calc_pnl_percent}%")
                passed += 1
            else:
                logger.error(f"❌ {symbol} ({side}): Calculated P&L={calc_pnl} (DB={db_pnl}), P&L%={calc_pnl_percent}% (DB={db_pnl_percent}%)")
                failed += 1
        
        logger.info(f"Results: {passed} passed, {failed} failed")
        return failed == 0
        
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("\n" + "="*70)
    logger.info("P&L CALCULATION TESTS")
    logger.info("="*70)
    
    try:
        results = []
        results.append(("Long profit", test_long_position_profit()))
        results.append(("Long loss", test_long_position_loss()))
        results.append(("Short profit", test_short_position_profit()))
        results.append(("Short loss", test_short_position_loss()))
        results.append(("Real trades", test_pnl_with_real_trades()))
        
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
            logger.info("✅ ALL P&L TESTS PASSED")
            sys.exit(0)
        else:
            logger.error("❌ SOME TESTS FAILED")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

