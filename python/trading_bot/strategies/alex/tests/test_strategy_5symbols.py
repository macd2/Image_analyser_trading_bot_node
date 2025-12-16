#!/usr/bin/env python3
"""
Test strategy with 5 real symbols we have data for.

Symbols: CAKEUSDT, AAVEUSDT, ADAUSDT, DOGEUSDT, XRPUSDT
All have 18k+ candles in database cache.
"""

import sys
import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.strategies.alex.alex_analysis_module import AlexAnalysisModule
from prompt_performance.core.database_utils import CandleStoreDatabase


async def test_5_symbols():
    """Test strategy with 5 real symbols."""
    print("\n" + "="*70)
    print("STRATEGY TEST WITH 5 REAL SYMBOLS")
    print("="*70)
    
    symbols = ["CAKEUSDT", "AAVEUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT"]
    timeframe = "1h"
    
    print(f"\n⏳ Loading real data from database...")
    print(f"   Symbols: {', '.join(symbols)}")
    print(f"   Timeframe: {timeframe}")
    
    # Check database
    db = CandleStoreDatabase()
    
    print(f"\n📥 Database cache status:")
    for symbol in symbols:
        count = db.get_candle_count(symbol, timeframe)
        if count > 0:
            date_range = db.get_candle_date_range(symbol, timeframe)
            from datetime import datetime
            earliest = datetime.fromtimestamp(date_range['earliest']/1000)
            latest = datetime.fromtimestamp(date_range['latest']/1000)
            print(f"   ✅ {symbol:<12} {count:>6} candles ({earliest.date()} to {latest.date()})")
        else:
            print(f"   ❌ {symbol:<12} No candles")
    
    # Create strategy
    strategy = AlexAnalysisModule(
        config=Mock(),
        instance_id="5-symbols-test",
        run_id="run-5-symbols-001",
    )
    
    print(f"\n🔍 Running analysis...")
    
    # Run analysis
    results = await strategy.run_analysis_cycle(
        symbols=symbols,
        timeframe=timeframe,
        cycle_id="cycle-5-symbols-001"
    )
    
    print(f"\n✅ Analysis Complete!")
    
    # Print summary table
    print(f"\n{'='*70}")
    print("RESULTS SUMMARY")
    print(f"{'='*70}")
    
    print(f"\n{'Symbol':<12} {'Recommendation':<15} {'Confidence':<12} {'Trend':<12} {'Strength':<10}")
    print(f"{'-'*70}")
    
    for result in results:
        if "error" not in result and not result.get("skipped"):
            trend = result['analysis']['trend']
            print(f"{result['symbol']:<12} {result['recommendation']:<15} {result['confidence']:.2%}        {trend['trend']:<12} {trend['strength']:.2%}")
        else:
            status = result.get('error', 'SKIPPED')
            print(f"{result['symbol']:<12} {status:<15}")
    
    # Detailed results
    print(f"\n{'='*70}")
    print("DETAILED RESULTS")
    print(f"{'='*70}")
    
    for i, result in enumerate(results, 1):
        print(f"\n{'─'*70}")
        print(f"#{i}: {result['symbol']}")
        print(f"{'─'*70}")
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            continue
        
        if result.get("skipped"):
            print(f"⏭️  Skipped: {result.get('skip_reason', 'Unknown')}")
            continue
        
        print(f"Recommendation:  {result['recommendation']}")
        print(f"Confidence:      {result['confidence']:.2%}")
        
        trend = result['analysis']['trend']
        print(f"\nTrend:           {trend['trend'].upper()}")
        print(f"Strength:        {trend['strength']:.2%}")
        print(f"Last Close:      ${trend['last_close']:.4f}")
        
        sr = result['analysis']['support_resistance']
        if sr['nearest_support'] and sr['nearest_resistance']:
            print(f"\nSupport:         ${sr['nearest_support']:.4f}")
            print(f"Resistance:      ${sr['nearest_resistance']:.4f}")
        
        print(f"\nSetup Quality:   {result['setup_quality']:.2%}")
        print(f"Market Env:      {result['market_environment']:.2%}")
    
    # JSON output
    print(f"\n{'='*70}")
    print("RAW JSON OUTPUT")
    print(f"{'='*70}")
    
    valid_results = [r for r in results if "error" not in r and not r.get("skipped")]
    print(json.dumps(valid_results, indent=2))
    
    return True


async def main():
    """Main entry point."""
    try:
        success = await test_5_symbols()
        return success
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

