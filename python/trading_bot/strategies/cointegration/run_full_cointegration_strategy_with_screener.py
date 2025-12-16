#!/usr/bin/env python3
"""
Run Cointegration Strategy with Auto-Screener

This script:
1. Checks if screener_results.json exists and is < 24 hours old
2. If not, runs the full pair screener
3. Converts pairs to strategy format
4. Runs the cointegration strategy with discovered pairs

Usage:
    source venv/bin/activate
    cd python/trading_bot/strategies/cointegration
    python run_cointegration_strategy.py
    
Or from project root:
    PYTHONPATH=python python python/trading_bot/strategies/cointegration/run_cointegration_strategy.py
"""

import asyncio
import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock

# Add python folder to path
python_path = os.path.join(os.path.dirname(__file__), '..', '..', '..')
if python_path not in sys.path:
    sys.path.insert(0, python_path)

from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule


def check_and_refresh_screener_results(results_file: Path, timeframe: str = "1h", max_age_hours: int = 24) -> dict:
    """
    Check if screener results exist and are fresh.
    If not, run the full screener.

    Args:
        results_file: Path to screener results JSON
        timeframe: Timeframe for analysis (e.g., "1h", "4h")
        max_age_hours: Maximum age of cached results in hours

    Returns: dict with pairs data
    """

    # Check if file exists and is fresh
    if results_file.exists():
        file_age = datetime.now() - datetime.fromtimestamp(results_file.stat().st_mtime)
        if file_age < timedelta(hours=max_age_hours):
            with open(results_file, 'r') as f:
                cached_results = json.load(f)
            # Check if timeframe matches
            cached_timeframe = cached_results.get('timeframe', '1h')
            if cached_timeframe == timeframe:
                print(f"✅ Using cached screener results ({file_age.total_seconds()/3600:.1f}h old, timeframe={timeframe})")
                return cached_results
            else:
                print(f"⚠️  Screener results have different timeframe ({cached_timeframe} vs {timeframe}), refreshing...")
        else:
            print(f"⚠️  Screener results are {file_age.total_seconds()/3600:.1f}h old, refreshing...")
    else:
        print("📊 No screener results found, running full screener...")

    # Run full screener with timeframe parameter
    screener_script = Path(__file__).parent / "run_full_screener.py"
    print(f"\n🔄 Running: {screener_script} (timeframe={timeframe})")
    result = subprocess.run(
        [sys.executable, str(screener_script), "--timeframe", timeframe],
        cwd=Path(__file__).parent,
        capture_output=False
    )

    if result.returncode != 0:
        print("❌ Screener failed!")
        sys.exit(1)

    # Load results
    with open(results_file, 'r') as f:
        return json.load(f)


def convert_pairs_to_strategy_format(screener_results: dict) -> dict:
    """
    Convert screener results to strategy format.
    
    Input: {"pairs": [{"symbol1": "X", "symbol2": "Y", ...}, ...]}
    Output: {"pairs": {"X": "Y", ...}}
    """
    pairs_dict = {}
    
    for pair_data in screener_results.get('pairs', []):
        symbol1 = pair_data['symbol1'].replace('USDT', '')
        symbol2 = pair_data['symbol2'].replace('USDT', '')
        pairs_dict[symbol1] = symbol2
        print(f"  ✓ {symbol1} ↔ {symbol2} (confidence: {pair_data['confidence_score']:.2%})")
    
    return pairs_dict


async def main(timeframe: str = "1h"):
    """
    Main entry point.

    Args:
        timeframe: Analysis timeframe (e.g., "1h", "4h", "1d")
    """

    print("=" * 70)
    print("COINTEGRATION STRATEGY WITH AUTO-SCREENER")
    print(f"Timeframe: {timeframe}")
    print("=" * 70)

    # Step 1: Check and refresh screener results
    results_file = Path(__file__).parent / "screener_results.json"
    print("\nSTEP 1: Checking screener results...")
    screener_results = check_and_refresh_screener_results(results_file, timeframe=timeframe)

    # Step 2: Convert pairs to strategy format
    print("\nSTEP 2: Converting pairs to strategy format...")
    pairs_dict = convert_pairs_to_strategy_format(screener_results)

    if not pairs_dict:
        print("❌ No pairs found!")
        return False

    print(f"\n✅ Found {len(pairs_dict)} cointegrated pairs")

    # Step 3: Initialize strategy with discovered pairs
    print("\nSTEP 3: Initializing cointegration strategy...")
    mock_config = Mock()
    strategy_config = {
        "analysis_timeframe": timeframe,
        "pairs": pairs_dict,
        "lookback": 120,
        "z_entry": 2.0,
        "z_exit": 0.5,
        "use_soft_vol": False,
    }

    strategy = CointegrationAnalysisModule(
        config=mock_config,
        instance_id="screener-run",
        strategy_config=strategy_config
    )
    print("✅ Strategy initialized")

    # Step 4: Run analysis cycle
    print("\nSTEP 4: Running cointegration analysis...")
    print("=" * 70)

    symbols = list(pairs_dict.keys())
    results = await strategy.run_analysis_cycle(
        symbols=symbols,
        timeframe=timeframe,
        cycle_id="screener-cycle"
    )

    # Step 5: Display results
    print("\nSTEP 5: Analysis Results:")
    print("=" * 70)

    for result in results:
        if result.get('skipped'):
            print(f"\n⏭️  {result['symbol']}: SKIPPED - {result.get('skip_reason', 'Unknown')}")
        else:
            print(f"\n✅ {result['symbol']}")
            print(f"   Recommendation: {result['recommendation']}")
            print(f"   Confidence: {result['confidence']:.2%}")

            entry = result['entry_price']
            sl = result['stop_loss']
            tp = result['take_profit']

            entry_str = f"{entry:.8f}" if entry is not None else "N/A"
            sl_str = f"{sl:.8f}" if sl is not None else "N/A"
            tp_str = f"{tp:.8f}" if tp is not None else "N/A"

            print(f"   Entry: {entry_str}")
            print(f"   Stop Loss: {sl_str}")
            print(f"   Take Profit: {tp_str}")
            print(f"   Risk/Reward: {result['risk_reward']:.2f}")

            if result.get('analysis'):
                z_score = result['analysis'].get('z_score', 'N/A')
                if isinstance(z_score, (int, float)):
                    print(f"   Z-Score: {z_score:.2f}")
                else:
                    print(f"   Z-Score: {z_score}")

                # Debug: show if mean reverting
                is_mr = result['analysis'].get('is_mean_reverting', False)
                print(f"   Mean Reverting: {is_mr}")

    print("\n" + "=" * 70)
    print("✅ Cointegration analysis complete!")

    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run cointegration strategy with auto-screener"
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1h",
        choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
        help="Analysis timeframe (default: 1h)"
    )

    args = parser.parse_args()

    try:
        success = asyncio.run(main(timeframe="1h"))
        # success = asyncio.run(main(timeframe=args.timeframe))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

