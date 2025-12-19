"""
Test to check z-score distribution with SpreadTrader settings.

SpreadTrader uses z_entry=3.0, which is very strict.
This test checks if z-scores actually reach 3.0 in real data.
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
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy
from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.db import get_connection, query_one, release_connection

async def test_z_score_distribution():
    """Test z-score distribution with SpreadTrader settings."""
    
    # Get SpreadTrader settings
    conn = get_connection()
    row = query_one(conn, "SELECT settings FROM instances WHERE name = ?", ("SpreadTrader",))
    release_connection(conn)
    
    if not row:
        print("❌ SpreadTrader not found")
        return
    
    if isinstance(row['settings'], str):
        settings = json.loads(row['settings'])
    else:
        settings = row['settings']
    
    strategy_config = settings.get('strategy_config', {})
    z_entry = float(strategy_config.get('z_entry', 3.0))
    z_exit = float(strategy_config.get('z_exit', 0.5))
    lookback = int(strategy_config.get('lookback', 120))
    use_adf = strategy_config.get('use_adf', True)
    
    print(f"📊 SpreadTrader Settings:")
    print(f"  z_entry: {z_entry} (VERY STRICT!)")
    print(f"  z_exit: {z_exit}")
    print(f"  lookback: {lookback}")
    print(f"  use_adf: {use_adf}\n")
    
    # Create strategy
    strategy = CointegrationStrategy(
        lookback=lookback,
        z_entry=z_entry,
        z_exit=z_exit,
        use_adf=use_adf,
        use_soft_vol=False
    )
    
    # Fetch candles for test pairs
    adapter = CandleAdapter()
    print("📈 Fetching candles for BTCUSDT and ETHUSDT (4h timeframe)...")
    
    candles1 = await adapter.get_candles('BTCUSDT', '4h', limit=200, min_candles=120)
    candles2 = await adapter.get_candles('ETHUSDT', '4h', limit=200, min_candles=120)
    
    if not candles1 or not candles2:
        print("❌ Failed to fetch candles")
        return
    
    print(f"✅ Got {len(candles1)} and {len(candles2)} candles\n")
    
    # Build DataFrame
    df = pd.DataFrame({
        'close_1': [c['close'] for c in candles1],
        'close_2': [c['close'] for c in candles2],
    })
    
    # Generate signals
    print("🔗 Generating signals...")
    signals = strategy.generate_signals(df)
    
    # Analyze results
    valid_signals = signals[signals['z_score'].notna()]
    
    print(f"\n📊 Z-Score Analysis:")
    print(f"  Total rows: {len(signals)}")
    print(f"  Valid z_scores: {len(valid_signals)}")
    print(f"  Min z_score: {valid_signals['z_score'].min():.2f}")
    print(f"  Max z_score: {valid_signals['z_score'].max():.2f}")
    print(f"  Mean z_score: {valid_signals['z_score'].mean():.2f}")
    print(f"  Std z_score: {valid_signals['z_score'].std():.2f}")
    
    # Count how many exceed threshold
    exceed_count = ((valid_signals['z_score'] >= z_entry) | (valid_signals['z_score'] <= -z_entry)).sum()
    print(f"\n⚠️  Z-scores exceeding z_entry ({z_entry}): {exceed_count}/{len(valid_signals)} ({100*exceed_count/len(valid_signals):.1f}%)")
    
    # Count mean-reverting
    mr_count = valid_signals['is_mean_reverting'].sum()
    print(f"  Mean-reverting: {mr_count}/{len(valid_signals)} ({100*mr_count/len(valid_signals):.1f}%)")
    
    # Count actual signals
    buy_signals = (valid_signals['signal'] == 1).sum()
    sell_signals = (valid_signals['signal'] == -1).sum()
    print(f"\n🎯 Actual Signals Generated:")
    print(f"  BUY signals: {buy_signals}")
    print(f"  SELL signals: {sell_signals}")
    print(f"  HOLD signals: {len(valid_signals) - buy_signals - sell_signals}")
    
    # Recommendation
    print(f"\n💡 Analysis:")
    if exceed_count == 0:
        print(f"  ❌ NO z-scores reach {z_entry}!")
        print(f"  → z_entry={z_entry} is TOO STRICT for this pair")
        print(f"  → Consider lowering z_entry to 2.0-2.5")
    elif exceed_count < len(valid_signals) * 0.1:
        print(f"  ⚠️  Only {100*exceed_count/len(valid_signals):.1f}% of z-scores reach {z_entry}")
        print(f"  → z_entry={z_entry} might be too strict")
        print(f"  → Consider lowering to 2.0-2.5")
    else:
        print(f"  ✅ z_entry={z_entry} is reasonable")

if __name__ == "__main__":
    asyncio.run(test_z_score_distribution())

