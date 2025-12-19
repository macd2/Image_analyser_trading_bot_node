"""
Debug test to understand why we're getting HOLD signals instead of BUY/SELL.

Tests the signal generation logic with actual database settings.
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

# Add python directory to path
sys.path.insert(0, 'python')

import numpy as np
import pandas as pd
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy
from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.db import get_connection, query_one, release_connection
from trading_bot.db.client import DB_TYPE

async def test_signal_generation():
    """Test signal generation with real data from database."""
    print(f"Using {DB_TYPE} database\n")
    
    # Get TestingInstance settings
    conn = get_connection()
    row = query_one(conn, "SELECT id, name, settings FROM instances WHERE name = ?", ("TestingInstance",))
    release_connection(conn)
    
    if not row:
        print("❌ TestingInstance not found")
        return
    
    # Parse settings
    if isinstance(row['settings'], str):
        settings = json.loads(row['settings'])
    else:
        settings = row['settings']
    
    # Extract cointegration settings
    strategy_config = settings.get('strategy_config', {})
    z_entry = float(strategy_config.get('z_entry', 2.0))
    z_exit = float(strategy_config.get('z_exit', 0.5))
    lookback = int(strategy_config.get('lookback', 120))
    use_adf = strategy_config.get('use_adf', True)
    use_soft_vol = strategy_config.get('use_soft_vol', False)
    
    print(f"📊 Strategy Settings:")
    print(f"  z_entry: {z_entry}")
    print(f"  z_exit: {z_exit}")
    print(f"  lookback: {lookback}")
    print(f"  use_adf: {use_adf}")
    print(f"  use_soft_vol: {use_soft_vol}\n")
    
    # Create strategy
    strategy = CointegrationStrategy(
        lookback=lookback,
        z_entry=z_entry,
        z_exit=z_exit,
        use_adf=use_adf,
        use_soft_vol=use_soft_vol
    )
    
    # Fetch candles for a test pair
    adapter = CandleAdapter()
    print("📈 Fetching candles for BTCUSDT and ETHUSDT...")
    candles1 = await adapter.get_candles('BTCUSDT', '1h', limit=200, min_candles=120)
    candles2 = await adapter.get_candles('ETHUSDT', '1h', limit=200, min_candles=120)
    
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
    print(f"\n📊 Signal Analysis:")
    print(f"  Total rows: {len(signals)}")
    print(f"  Valid z_scores: {len(valid_signals)}")
    
    # Check mean-reversion
    mr_count = valid_signals['is_mean_reverting'].sum()
    print(f"  Mean-reverting: {mr_count}/{len(valid_signals)} ({100*mr_count/len(valid_signals):.1f}%)")
    
    # Check signals
    buy_signals = (valid_signals['signal'] == 1).sum()
    sell_signals = (valid_signals['signal'] == -1).sum()
    print(f"  BUY signals: {buy_signals}")
    print(f"  SELL signals: {sell_signals}")
    
    # Show last 10 rows
    print(f"\n📋 Last 10 rows:")
    print(valid_signals[['z_score', 'is_mean_reverting', 'signal']].tail(10).to_string())
    
    # Check z-score distribution
    print(f"\n📈 Z-score statistics:")
    print(f"  Min: {valid_signals['z_score'].min():.2f}")
    print(f"  Max: {valid_signals['z_score'].max():.2f}")
    print(f"  Mean: {valid_signals['z_score'].mean():.2f}")
    print(f"  Std: {valid_signals['z_score'].std():.2f}")
    
    # Count how many z-scores exceed threshold
    exceed_count = ((valid_signals['z_score'] >= z_entry) | (valid_signals['z_score'] <= -z_entry)).sum()
    print(f"  Exceed z_entry ({z_entry}): {exceed_count}/{len(valid_signals)} ({100*exceed_count/len(valid_signals):.1f}%)")

if __name__ == "__main__":
    asyncio.run(test_signal_generation())

