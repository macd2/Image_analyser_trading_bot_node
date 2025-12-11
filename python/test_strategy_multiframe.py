#!/usr/bin/env python3
"""
Test strategy with multiple timeframes (top-down analysis).
"""

import sys
import asyncio
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.strategies.alex_analysis_module import AlexAnalysisModule


async def test_multiframe():
    """Test strategy with multiple timeframes."""
    print("\n" + "="*70)
    print("STRATEGY TEST - MULTIPLE TIMEFRAMES (TOP-DOWN)")
    print("="*70)
    
    symbols = ["CAKEUSDT", "AAVEUSDT"]
    
    # Create strategy with custom config for multiple timeframes
    strategy = AlexAnalysisModule(
        config=Mock(),
        instance_id="multiframe-test",
        run_id="run-multiframe-001",
        strategy_config={
            "timeframes": ["1h", "4h", "1d"],  # Top-down analysis
            "lookback_periods": 20,
            "min_confidence": 0.7,
        }
    )
    
    print(f"\n🔍 Running top-down analysis...")
    print(f"   Symbols: {', '.join(symbols)}")
    print(f"   Timeframes: 1h, 4h, 1d (top-down)")
    
    # Run analysis
    results = await strategy.run_analysis_cycle(
        symbols=symbols,
        timeframe="1h",  # This is ignored, uses configured timeframes
        cycle_id="cycle-multiframe-001"
    )
    
    print(f"\n✅ Analysis Complete!")
    
    # Print results
    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    
    for result in results:
        if "error" not in result and not result.get("skipped"):
            print(f"\n{result['symbol']}")
            print(f"  Recommendation: {result['recommendation']}")
            print(f"  Confidence: {result['confidence']:.2%}")
            print(f"  Timeframes Analyzed: {result['analysis'].get('timeframes_analyzed', [])}")
            print(f"  Primary Timeframe: {result['analysis'].get('primary_timeframe', 'N/A')}")
            print(f"  Trend: {result['analysis']['trend']['trend'].upper()}")
            print(f"  Strength: {result['analysis']['trend']['strength']:.2%}")
        else:
            status = result.get('error', 'SKIPPED')
            print(f"\n{result['symbol']}: {status}")


async def main():
    """Main entry point."""
    try:
        await test_multiframe()
        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

