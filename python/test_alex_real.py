#!/usr/bin/env python3
"""
Test AlexAnalysisModule with real cached candles from database.
"""

import sys
import asyncio
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.strategies.alex_analysis_module import AlexAnalysisModule


async def test_alex_real():
    """Test strategy with real Bybit API candles."""
    print("\n" + "="*80)
    print("ALEX STRATEGY - REAL BYBIT API CANDLES TEST")
    print("="*80)

    # Test with one symbol first
    symbols = ["BTCUSDT"]
    
    # Create strategy
    strategy = AlexAnalysisModule(
        config=Mock(),
        instance_id="test-alex-real",
        run_id="run-alex-real-001",
        strategy_config={
            "timeframes": ["1h", "4h", "1d"],
            "lookback_periods": 20,
            "min_confidence": 0.5,
        }
    )
    
    print(f"\n🔍 Testing with {len(symbols)} symbols")
    print(f"   Timeframes: 1h, 4h, 1d (top-down)")
    print(f"   Symbols: {', '.join(symbols)}")

    # Run analysis
    print(f"\n📊 Starting analysis cycle...")
    results = await strategy.run_analysis_cycle(
        symbols=symbols,
        timeframe="1h",
        cycle_id="cycle-alex-real-001"
    )
    print(f"✅ Analysis cycle complete!")
    
    print(f"\n✅ Analysis Complete!")
    print(f"\n{'='*80}")
    print("RESULTS SUMMARY")
    print(f"{'='*80}")
    
    # Summary table
    print(f"\n{'Symbol':<12} {'Rec':<6} {'Conf':<8} {'Trend':<8} {'Strength':<10}")
    print("-" * 50)
    
    for result in results:
        if "error" not in result and not result.get("skipped"):
            symbol = result['symbol']
            rec = result['recommendation'][:3].upper()
            conf = f"{result['confidence']:.1%}"
            trend = result['analysis']['trend']['trend'][:3].upper()
            strength = f"{result['analysis']['trend']['strength']:.1%}"
            print(f"{symbol:<12} {rec:<6} {conf:<8} {trend:<8} {strength:<10}")
        else:
            status = result.get('error', 'SKIPPED')
            print(f"{result['symbol']:<12} {status}")
    
    # Detailed output
    print(f"\n{'='*80}")
    print("DETAILED RESULTS")
    print(f"{'='*80}")
    
    for result in results:
        if "error" not in result and not result.get("skipped"):
            print(f"\n{result['symbol']}")
            print(f"  Recommendation: {result['recommendation'].upper()}")
            print(f"  Confidence: {result['confidence']:.2%}")
            print(f"  Timeframes Analyzed: {result['analysis'].get('timeframes_analyzed', [])}")
            print(f"  Trend: {result['analysis']['trend']['trend'].upper()}")
            print(f"  Strength: {result['analysis']['trend']['strength']:.2%}")
            
            prices = result['analysis'].get('prices', {})
            if prices:
                print(f"  Support: {prices.get('support', 'N/A')}")
                print(f"  Resistance: {prices.get('resistance', 'N/A')}")


async def main():
    """Main entry point."""
    try:
        await test_alex_real()
        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

