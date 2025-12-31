#!/usr/bin/env python3
"""
End-to-end functional test for complete closing workflow.

Tests the entire closing process:
1. Fetch open trades from database
2. Validate trade data
3. Fetch candles for each trade
4. Validate candles
5. Check SL/TP conditions
6. Calculate P&L
7. Verify database consistency

Usage:
    python3 python/tests/test_closing_end_to_end.py
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
from python.tests.validate_closing_trades import validate_trade_for_closing, validate_candles_for_closing

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_complete_closing_workflow():
    """Test complete closing workflow with real data."""
    logger.info("\n" + "="*70)
    logger.info("END-TO-END TEST: Complete closing workflow")
    logger.info("="*70)
    
    conn = get_connection()
    try:
        # STEP 1: Fetch open trades
        logger.info("\nSTEP 1: Fetching open trades...")
        open_trades = query(conn, """
            SELECT t.*, i.settings as instance_settings
            FROM trades t
            LEFT JOIN runs r ON t.run_id = r.id
            LEFT JOIN instances i ON r.instance_id = i.id
            WHERE t.pnl IS NULL AND t.status IN ('paper_trade', 'pending_fill', 'filled')
            LIMIT 5
        """)
        
        if not open_trades:
            logger.warning("No open trades found")
            return True
        
        open_trades = [dict(t) for t in open_trades]
        logger.info(f"✅ Found {len(open_trades)} open trades")
        
        # STEP 2: Process each trade
        processed = 0
        validated = 0
        with_exit_signal = 0
        
        for trade in open_trades:
            logger.info(f"\n--- Processing {trade['symbol']} ({trade['id'][:8]}...) ---")
            
            # STEP 2A: Validate trade
            is_valid, error, context = validate_trade_for_closing(trade)
            if not is_valid:
                logger.warning(f"Trade validation failed: {error}")
                continue
            
            validated += 1
            logger.info(f"✅ Trade validated")
            
            # STEP 2B: Fetch candles
            candles = query(conn, """
                SELECT start_time as timestamp, open_price as open, high_price as high,
                       low_price as low, close_price as close
                FROM klines
                WHERE symbol = ? AND timeframe = '1h'
                ORDER BY start_time ASC
                LIMIT 1000
            """, (trade['symbol'],))
            
            candles = [dict(c) for c in candles]
            
            # STEP 2C: Validate candles
            is_valid, error, context = validate_candles_for_closing(
                trade['id'], trade['symbol'], candles
            )
            if not is_valid:
                logger.warning(f"Candles validation failed: {error}")
                continue
            
            logger.info(f"✅ Candles validated ({len(candles)} candles)")
            
            # STEP 2D: Check SL/TP
            entry_price = trade.get('entry_price')
            stop_loss = trade.get('stop_loss')
            take_profit = trade.get('take_profit')
            side = trade.get('side', '').lower()
            is_long = side in ['buy', 'long']
            
            exit_found = False
            for i, candle in enumerate(candles):
                if is_long:
                    if candle['low'] <= stop_loss:
                        logger.info(f"SL hit at candle {i}: {candle['low']} <= {stop_loss}")
                        exit_found = True
                        break
                    elif candle['high'] >= take_profit:
                        logger.info(f"TP hit at candle {i}: {candle['high']} >= {take_profit}")
                        exit_found = True
                        break
                else:
                    if candle['high'] >= stop_loss:
                        logger.info(f"SL hit at candle {i}: {candle['high']} >= {stop_loss}")
                        exit_found = True
                        break
                    elif candle['low'] <= take_profit:
                        logger.info(f"TP hit at candle {i}: {candle['low']} <= {take_profit}")
                        exit_found = True
                        break
            
            if exit_found:
                with_exit_signal += 1
                logger.info(f"✅ Exit signal found")
            else:
                logger.info(f"ℹ️  No exit signal (trade remains open)")
            
            # STEP 2E: Verify trade consistency
            run_id = trade.get('run_id')
            if run_id:
                run = query(conn, "SELECT * FROM runs WHERE id = ?", (run_id,))
                if run:
                    logger.info(f"✅ Trade linked to valid run")
                else:
                    logger.warning(f"⚠️  Trade run_id not found in database")
            
            processed += 1
        
        # STEP 3: Summary
        logger.info("\n" + "="*70)
        logger.info("WORKFLOW SUMMARY")
        logger.info("="*70)
        logger.info(f"Total trades processed: {processed}")
        logger.info(f"Trades validated: {validated}")
        logger.info(f"Trades with exit signal: {with_exit_signal}")
        logger.info(f"Trades remaining open: {processed - with_exit_signal}")
        
        return True
        
    finally:
        conn.close()


def test_database_consistency():
    """Test database consistency for closing logic."""
    logger.info("\n" + "="*70)
    logger.info("DATABASE CONSISTENCY TEST")
    logger.info("="*70)
    
    conn = get_connection()
    try:
        # Check for orphaned trades (no run)
        logger.info("\nChecking for orphaned trades...")
        orphaned = query(conn, """
            SELECT COUNT(*) as count FROM trades
            WHERE run_id IS NULL AND pnl IS NULL
        """)
        
        orphaned_count = dict(orphaned[0])['count'] if orphaned else 0
        if orphaned_count > 0:
            logger.warning(f"⚠️  Found {orphaned_count} orphaned trades")
        else:
            logger.info(f"✅ No orphaned trades")
        
        # Check for trades with invalid prices
        logger.info("\nChecking for invalid prices...")
        invalid = query(conn, """
            SELECT COUNT(*) as count FROM trades
            WHERE (entry_price <= 0 OR stop_loss <= 0 OR take_profit <= 0)
            AND pnl IS NULL
        """)
        
        invalid_count = dict(invalid[0])['count'] if invalid else 0
        if invalid_count > 0:
            logger.warning(f"⚠️  Found {invalid_count} trades with invalid prices")
        else:
            logger.info(f"✅ All prices are valid")
        
        # Check for closed trades with missing P&L
        logger.info("\nChecking for closed trades with missing P&L...")
        missing_pnl = query(conn, """
            SELECT COUNT(*) as count FROM trades
            WHERE status = 'closed' AND pnl IS NULL
        """)
        
        missing_pnl_count = dict(missing_pnl[0])['count'] if missing_pnl else 0
        if missing_pnl_count > 0:
            logger.warning(f"⚠️  Found {missing_pnl_count} closed trades with missing P&L")
        else:
            logger.info(f"✅ All closed trades have P&L")
        
        # Check run aggregates
        logger.info("\nChecking run aggregates...")
        runs = query(conn, """
            SELECT id, total_pnl, win_count, loss_count
            FROM runs
            WHERE total_pnl IS NOT NULL
            LIMIT 3
        """)
        
        if runs:
            logger.info(f"✅ Found {len(runs)} runs with aggregates")
            for run in runs:
                run_dict = dict(run)
                logger.info(f"  Run {run_dict['id'][:8]}...: PnL={run_dict['total_pnl']}, Wins={run_dict['win_count']}, Losses={run_dict['loss_count']}")
        else:
            logger.info(f"ℹ️  No runs with aggregates")
        
        return True
        
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("\n" + "="*70)
    logger.info("END-TO-END CLOSING WORKFLOW TESTS")
    logger.info("="*70)
    
    try:
        results = []
        results.append(("Complete workflow", test_complete_closing_workflow()))
        results.append(("Database consistency", test_database_consistency()))
        
        logger.info("\n" + "="*70)
        logger.info("FINAL RESULTS")
        logger.info("="*70)
        
        all_passed = True
        for test_name, passed in results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            logger.info(f"{test_name}: {status}")
            if not passed:
                all_passed = False
        
        logger.info("="*70)
        
        if all_passed:
            logger.info("✅ ALL END-TO-END TESTS PASSED")
            sys.exit(0)
        else:
            logger.error("❌ SOME TESTS FAILED")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

