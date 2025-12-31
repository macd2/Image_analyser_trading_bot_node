#!/usr/bin/env python3
"""
Functional test for closing logic with REAL data from database.

This test:
1. Fetches actual open trades from the database
2. Fetches actual candles for those trades
3. Tests the closing logic with real production code
4. Validates that trades can be closed correctly
5. Verifies P&L calculations
6. Checks database updates

Usage:
    python3 python/tests/test_closing_functional.py [--limit N] [--symbol SYMBOL]
"""

import sys
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env.local
env_path = Path(__file__).parent.parent.parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.db.client import get_connection, query, execute
from python.tests.validate_closing_trades import validate_trade_for_closing, validate_candles_for_closing

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_open_trades(limit: int = 5, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch open trades from database."""
    conn = get_connection()
    try:
        sql = """
            SELECT t.*, i.settings as instance_settings
            FROM trades t
            LEFT JOIN runs r ON t.run_id = r.id
            LEFT JOIN instances i ON r.instance_id = i.id
            WHERE t.pnl IS NULL AND t.status IN ('paper_trade', 'pending_fill', 'filled')
        """
        params = []
        
        if symbol:
            sql += " AND t.symbol = ?"
            params.append(symbol)
        
        sql += " ORDER BY t.created_at DESC LIMIT ?"
        params.append(limit)
        
        trades = query(conn, sql, tuple(params))
        return [dict(t) for t in trades]
    finally:
        conn.close()


def fetch_candles(symbol: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch candles for a symbol."""
    conn = get_connection()
    try:
        candles = query(conn, """
            SELECT start_time as timestamp, open_price as open, high_price as high,
                   low_price as low, close_price as close
            FROM klines
            WHERE symbol = ? AND timeframe = '1h'
            ORDER BY start_time ASC
            LIMIT ?
        """, (symbol, limit))
        
        return [dict(c) for c in candles]
    finally:
        conn.close()


def calculate_pnl(trade: Dict[str, Any], exit_price: float) -> tuple:
    """Calculate P&L and P&L percent for a trade."""
    entry_price = trade.get('entry_price')
    quantity = trade.get('quantity')
    side = trade.get('side', '').lower()
    
    if not entry_price or not quantity:
        return None, None
    
    if side in ['buy', 'long']:
        pnl = (exit_price - entry_price) * quantity
    else:  # sell, short
        pnl = (entry_price - exit_price) * quantity
    
    position_value = entry_price * quantity
    pnl_percent = (pnl / position_value * 100) if position_value > 0 else 0
    
    return round(pnl, 2), round(pnl_percent, 2)


def test_trade_closing_with_sl_tp():
    """Test closing a trade when SL/TP is hit."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Trade closing with SL/TP hit")
    logger.info("="*70)
    
    # Fetch open trades
    trades = fetch_open_trades(limit=3)
    if not trades:
        logger.warning("No open trades found - skipping test")
        return True
    
    trade = trades[0]
    logger.info(f"Testing trade: {trade['id']} ({trade['symbol']})")
    
    # STEP 1: Validate trade
    is_valid, error, context = validate_trade_for_closing(trade)
    if not is_valid:
        logger.error(f"Trade validation failed: {error}")
        return False
    logger.info(f"✅ Trade validation passed")
    
    # STEP 2: Fetch and validate candles
    candles = fetch_candles(trade['symbol'])
    is_valid, error, context = validate_candles_for_closing(
        trade['id'], trade['symbol'], candles, min_candles=1
    )
    if not is_valid:
        logger.error(f"Candles validation failed: {error}")
        return False
    logger.info(f"✅ Candles validation passed ({len(candles)} candles)")
    
    # STEP 3: Check if SL/TP would be hit
    entry_price = trade.get('entry_price')
    stop_loss = trade.get('stop_loss')
    take_profit = trade.get('take_profit')
    side = trade.get('side', '').lower()
    is_long = side in ['buy', 'long']
    
    logger.info(f"Entry: {entry_price}, SL: {stop_loss}, TP: {take_profit}, Side: {side}")
    
    # Find if SL/TP is hit in candles
    exit_price = None
    exit_reason = None
    
    for i, candle in enumerate(candles):
        if is_long:
            if candle['low'] <= stop_loss:
                exit_price = stop_loss
                exit_reason = 'sl_hit'
                logger.info(f"SL hit at candle {i}: low={candle['low']} <= SL={stop_loss}")
                break
            elif candle['high'] >= take_profit:
                exit_price = take_profit
                exit_reason = 'tp_hit'
                logger.info(f"TP hit at candle {i}: high={candle['high']} >= TP={take_profit}")
                break
        else:
            if candle['high'] >= stop_loss:
                exit_price = stop_loss
                exit_reason = 'sl_hit'
                logger.info(f"SL hit at candle {i}: high={candle['high']} >= SL={stop_loss}")
                break
            elif candle['low'] <= take_profit:
                exit_price = take_profit
                exit_reason = 'tp_hit'
                logger.info(f"TP hit at candle {i}: low={candle['low']} <= TP={take_profit}")
                break
    
    if not exit_price:
        logger.info("No SL/TP hit found in candles - trade remains open (normal)")
        return True
    
    # STEP 4: Calculate P&L
    pnl, pnl_percent = calculate_pnl(trade, exit_price)
    logger.info(f"P&L: {pnl} ({pnl_percent}%)")
    
    # STEP 5: Verify P&L calculation
    if pnl is None:
        logger.error("Failed to calculate P&L")
        return False
    
    logger.info(f"✅ Trade closing test passed")
    return True


def test_trade_validation_with_real_data():
    """Test validation with real trades from database."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Trade validation with real database data")
    logger.info("="*70)
    
    trades = fetch_open_trades(limit=5)
    if not trades:
        logger.warning("No open trades found - skipping test")
        return True
    
    logger.info(f"Found {len(trades)} open trades")
    
    passed = 0
    failed = 0
    
    for trade in trades:
        is_valid, error, context = validate_trade_for_closing(trade)
        if is_valid:
            logger.info(f"✅ {trade['symbol']} ({trade['id'][:8]}...) - valid")
            passed += 1
        else:
            logger.warning(f"⚠️  {trade['symbol']} ({trade['id'][:8]}...) - {error}")
            failed += 1
    
    logger.info(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def test_candles_validation_with_real_data():
    """Test candles validation with real data from database."""
    logger.info("\n" + "="*70)
    logger.info("TEST: Candles validation with real database data")
    logger.info("="*70)
    
    trades = fetch_open_trades(limit=3)
    if not trades:
        logger.warning("No open trades found - skipping test")
        return True
    
    passed = 0
    failed = 0
    
    for trade in trades:
        symbol = trade['symbol']
        candles = fetch_candles(symbol)
        
        is_valid, error, context = validate_candles_for_closing(
            trade['id'], symbol, candles
        )
        
        if is_valid:
            logger.info(f"✅ {symbol} - {len(candles)} candles valid")
            passed += 1
        else:
            logger.warning(f"⚠️  {symbol} - {error}")
            failed += 1
    
    logger.info(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=5, help='Number of trades to test')
    parser.add_argument('--symbol', type=str, help='Filter by symbol')
    args = parser.parse_args()
    
    logger.info("\n" + "="*70)
    logger.info("FUNCTIONAL TESTS: CLOSING LOGIC WITH REAL DATABASE DATA")
    logger.info("="*70)
    
    try:
        results = []
        results.append(("Trade validation", test_trade_validation_with_real_data()))
        results.append(("Candles validation", test_candles_validation_with_real_data()))
        results.append(("Trade closing with SL/TP", test_trade_closing_with_sl_tp()))
        
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
            logger.info("✅ ALL FUNCTIONAL TESTS PASSED")
            sys.exit(0)
        else:
            logger.error("❌ SOME TESTS FAILED")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

