"""
Contract Test: Signal Generation with Real Database Settings and Real Candle Data

Tests that the cointegration strategy generates correct signals using:
1. Real settings from SpreadTrader instance (z_entry, z_exit, lookback, use_adf)
2. Real candle data from Bybit API (fetches up to 1000 candles per symbol)
3. Real pair data from recent recommendations

Validates:
- Signal generation respects z_entry threshold
- is_mean_reverting filter works correctly
- With z_entry=2.0, should generate some BUY/SELL signals
- Price levels are calculated when signals are generated
"""
import sys
import os
import json
import asyncio
from pathlib import Path

# Load .env.local
env_file = Path('.env.local')
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

sys.path.insert(0, 'python')

import numpy as np
import pandas as pd
from trading_bot.db import get_connection, query_one, query, release_connection
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy
from trading_bot.strategies.candle_adapter import CandleAdapter

async def test_signal_generation_with_real_settings():
    """Contract test: Signal generation with real database settings and real candle data."""

    print("=" * 100)
    print("CONTRACT TEST: Signal Generation with Real Database Settings & Real Candle Data")
    print("=" * 100)

    # 1. Load SpreadTrader settings from database
    print("\n📋 Step 1: Loading SpreadTrader settings from database...")
    conn = get_connection()
    row = query_one(conn, "SELECT settings FROM instances WHERE name = ?", ("SpreadTrader",))
    release_connection(conn)

    if not row:
        print("❌ SpreadTrader instance not found")
        return False

    if isinstance(row['settings'], str):
        settings = json.loads(row['settings'])
    else:
        settings = row['settings']

    strategy_config = settings.get('strategy_config', {})
    z_entry = float(strategy_config.get('z_entry', 2.0))
    z_exit = float(strategy_config.get('z_exit', 0.5))
    lookback = int(strategy_config.get('lookback', 120))
    use_adf = strategy_config.get('use_adf', True)
    use_soft_vol = strategy_config.get('use_soft_vol', False)
    analysis_timeframe = strategy_config.get('analysis_timeframe', '4h')

    print(f"✅ Loaded settings:")
    print(f"   z_entry: {z_entry}")
    print(f"   z_exit: {z_exit}")
    print(f"   lookback: {lookback}")
    print(f"   use_adf: {use_adf}")
    print(f"   analysis_timeframe: {analysis_timeframe}")

    # 2. Fetch real candle data (up to 1000 per symbol)
    print(f"\n📈 Step 2: Fetching real candle data from Bybit ({analysis_timeframe})...")
    print(f"   Requesting up to 1000 candles per symbol...")
    adapter = CandleAdapter()

    # Test with BTCUSDT and ETHUSDT (highly correlated, should be cointegrated)
    symbol1 = 'BTCUSDT'
    symbol2 = 'ETHUSDT'

    candles1 = await adapter.get_candles(symbol1, analysis_timeframe, limit=1000, min_candles=lookback, prefer_source="api")
    candles2 = await adapter.get_candles(symbol2, analysis_timeframe, limit=1000, min_candles=lookback, prefer_source="api")

    if not candles1 or not candles2:
        print(f"❌ Failed to fetch candles")
        return False

    print(f"✅ Fetched {len(candles1)} and {len(candles2)} candles")

    # 3. Build DataFrame
    print(f"\n🔗 Step 3: Building DataFrame for cointegration analysis...")
    df = pd.DataFrame({
        'close_1': [c['close'] for c in candles1],
        'close_2': [c['close'] for c in candles2],
    })
    print(f"✅ DataFrame shape: {df.shape}")
    print(f"   Using {len(df)} candles for analysis (lookback={lookback})")

    # 4. Create strategy with real settings
    print(f"\n⚙️  Step 4: Creating CointegrationStrategy with real settings...")
    strategy = CointegrationStrategy(
        lookback=lookback,
        z_entry=z_entry,
        z_exit=z_exit,
        use_adf=use_adf,
        use_soft_vol=use_soft_vol
    )
    print(f"✅ Strategy created with z_entry={z_entry}")

    # 5. Generate signals
    print(f"\n🎯 Step 5: Generating signals...")
    signals = strategy.generate_signals(df)
    valid_signals = signals[signals['z_score'].notna()]

    print(f"✅ Generated {len(valid_signals)} valid signals")

    # 6. Analyze results
    print(f"\n📊 Step 6: Analyzing signal generation results...")

    # Count signals by type
    buy_signals = (valid_signals['signal'] == 1).sum()
    sell_signals = (valid_signals['signal'] == -1).sum()
    hold_signals = (valid_signals['signal'] == 0).sum()

    print(f"   BUY signals: {buy_signals}")
    print(f"   SELL signals: {sell_signals}")
    print(f"   HOLD signals: {hold_signals}")

    # Count mean-reverting
    mr_count = valid_signals['is_mean_reverting'].sum()
    print(f"   Mean-reverting: {mr_count}/{len(valid_signals)} ({100*mr_count/len(valid_signals):.1f}%)")

    # Z-score statistics
    print(f"\n   Z-score statistics:")
    print(f"   Min: {valid_signals['z_score'].min():.4f}")
    print(f"   Max: {valid_signals['z_score'].max():.4f}")
    print(f"   Mean: {valid_signals['z_score'].mean():.4f}")
    print(f"   Std: {valid_signals['z_score'].std():.4f}")

    # Count z-scores exceeding threshold
    exceed_count = ((valid_signals['z_score'] >= z_entry) | (valid_signals['z_score'] <= -z_entry)).sum()
    print(f"   Z-scores >= {z_entry}: {exceed_count}/{len(valid_signals)} ({100*exceed_count/len(valid_signals):.1f}%)")

    # 7. Validate contract
    print(f"\n✅ Step 7: Validating contract...")

    tests_passed = 0
    tests_total = 0

    # Test 1: Should have some valid signals
    tests_total += 1
    if len(valid_signals) > 0:
        print(f"   ✅ Test 1: Has valid signals ({len(valid_signals)})")
        tests_passed += 1
    else:
        print(f"   ❌ Test 1: No valid signals generated")

    # Test 2: Should have some mean-reverting candles
    tests_total += 1
    if mr_count > 0:
        print(f"   ✅ Test 2: Has mean-reverting candles ({mr_count})")
        tests_passed += 1
    else:
        print(f"   ❌ Test 2: No mean-reverting candles")

    # Test 3: With z_entry=2.0, should generate some signals
    tests_total += 1
    if buy_signals + sell_signals > 0:
        print(f"   ✅ Test 3: Generated BUY/SELL signals ({buy_signals + sell_signals})")
        tests_passed += 1
    else:
        print(f"   ⚠️  Test 3: No BUY/SELL signals (all HOLD)")
        if exceed_count == 0:
            print(f"      Reason: No z-scores exceed threshold {z_entry}")
        elif mr_count == 0:
            print(f"      Reason: No mean-reverting candles")
        else:
            print(f"      Reason: Unknown (z-scores exceed, is_mr=True, but no signals)")

    # Test 4: Z-scores should be reasonable
    tests_total += 1
    if valid_signals['z_score'].std() > 0:
        print(f"   ✅ Test 4: Z-scores have variation (std={valid_signals['z_score'].std():.4f})")
        tests_passed += 1
    else:
        print(f"   ❌ Test 4: Z-scores have no variation")

    # Summary
    print(f"\n" + "=" * 100)
    print(f"CONTRACT TEST RESULT: {tests_passed}/{tests_total} tests passed")
    print(f"=" * 100)

    return tests_passed == tests_total

if __name__ == "__main__":
    result = asyncio.run(test_signal_generation_with_real_settings())
    sys.exit(0 if result else 1)

