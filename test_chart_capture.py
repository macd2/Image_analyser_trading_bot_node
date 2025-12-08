#!/usr/bin/env python3
"""
Test script to verify chart capture with new symbol verification.
Tests the fix for ATHUSDT price bug.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'python'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv('.env.local')

from trading_bot.core.sourcer import ChartSourcer
from trading_bot.config.settings_v2 import ConfigV2
from trading_bot.db.client import get_connection, query_one
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_chart_capture(symbol: str = "ATHUSDT", timeframe: str = "4h", instance_id: str = None):
    """Test chart capture with verification for a specific symbol."""

    logger.info("=" * 70)
    logger.info(f"🧪 TESTING CHART CAPTURE WITH VERIFICATION")
    logger.info(f"   Symbol: {symbol}")
    logger.info(f"   Timeframe: {timeframe}")
    logger.info("=" * 70)

    # Get an instance ID if not provided
    if not instance_id:
        logger.info("Looking for an active instance...")
        conn = get_connection()
        result = query_one(conn, "SELECT id FROM instances LIMIT 1")
        if result:
            instance_id = result['id']
            logger.info(f"Using instance: {instance_id}")
        else:
            logger.error("No instance found in database. Please create an instance first.")
            logger.info("You can specify an instance ID with --instance <id>")
            return False

    # Load config from instance
    logger.info(f"Loading config for instance: {instance_id}")
    try:
        config = ConfigV2.load(instance_id=instance_id)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        logger.info("Make sure the instance exists and has valid configuration.")
        return False

    # Create sourcer
    sourcer = ChartSourcer(config)
    
    try:
        # Capture chart
        logger.info(f"\n📸 Starting chart capture for {symbol}...")
        chart_path = await sourcer.capture_tradingview_chart(symbol, timeframe)
        
        if chart_path:
            logger.info(f"\n✅ SUCCESS!")
            logger.info(f"   Chart saved to: {chart_path}")
            logger.info(f"\n🔍 Verification layers passed:")
            logger.info(f"   ✓ URL navigation")
            logger.info(f"   ✓ Symbol verification")
            logger.info(f"   ✓ Screenshot capture")
            return True
        else:
            logger.error(f"\n❌ FAILED!")
            logger.error(f"   Chart capture returned None")
            return False
            
    except Exception as e:
        logger.error(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await sourcer.cleanup_browser_session()

async def test_multiple_symbols(instance_id: str = None):
    """Test chart capture for multiple symbols to verify verification works."""

    test_symbols = [
        ("ATHUSDT", "4h"),
        ("DOGEUSDT", "4h"),
        ("BTCUSDT", "1h"),
    ]

    results = {}

    for symbol, timeframe in test_symbols:
        logger.info(f"\n{'='*70}")
        success = await test_chart_capture(symbol, timeframe, instance_id)
        results[symbol] = success

        # Wait between captures
        if symbol != test_symbols[-1][0]:
            logger.info("\n⏳ Waiting 5 seconds before next capture...")
            await asyncio.sleep(5)
    
    # Summary
    logger.info(f"\n{'='*70}")
    logger.info("📊 TEST SUMMARY")
    logger.info(f"{'='*70}")
    for symbol, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"   {symbol}: {status}")
    
    total = len(results)
    passed = sum(1 for s in results.values() if s)
    logger.info(f"\n   Total: {passed}/{total} passed")
    logger.info(f"{'='*70}\n")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test chart capture with verification")
    parser.add_argument("--symbol", type=str, default="ATHUSDT", help="Symbol to test")
    parser.add_argument("--timeframe", type=str, default="4h", help="Timeframe to test")
    parser.add_argument("--instance", type=str, help="Instance ID to use")
    parser.add_argument("--multiple", action="store_true", help="Test multiple symbols")

    args = parser.parse_args()

    if args.multiple:
        asyncio.run(test_multiple_symbols(args.instance))
    else:
        asyncio.run(test_chart_capture(args.symbol, args.timeframe, args.instance))

if __name__ == "__main__":
    main()

