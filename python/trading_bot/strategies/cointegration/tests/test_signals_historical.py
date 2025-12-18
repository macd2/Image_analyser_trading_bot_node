"""
Test script to generate signals from historical data for cointegrated pairs.
This helps debug signal generation without relying on real-time API data.
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy
from trading_bot.strategies.cointegration.price_levels import calculate_levels
import pandas as pd
import numpy as np


async def test_pair_signals(symbol1: str, symbol2: str, timeframe: str = "1h", lookback_days: int = 30):
    """Test signal generation for a pair using historical data."""
    
    print(f"\n{'='*70}")
    print(f"Testing pair: {symbol1} ↔ {symbol2}")
    print(f"Timeframe: {timeframe}, Lookback: {lookback_days} days")
    print(f"{'='*70}")
    
    # Initialize candle adapter
    adapter = CandleAdapter(instance_id="test")
    
    # Fetch historical candles
    print(f"\n[1] Fetching {lookback_days} days of {timeframe} candles...")
    
    # Calculate limit based on timeframe
    timeframe_hours = {"1m": 1/60, "5m": 5/60, "15m": 15/60, "30m": 0.5, "1h": 1, "4h": 4, "1d": 24}
    hours_needed = lookback_days * 24
    limit = int(hours_needed / timeframe_hours.get(timeframe, 1)) + 100
    limit = min(limit, 1000)  # API max
    
    candles1 = await adapter.get_candles(
        symbol1,
        timeframe,
        limit=limit,
        prefer_source="api",
        cache_to_db=False
    )
    
    candles2 = await adapter.get_candles(
        symbol2,
        timeframe,
        limit=limit,
        prefer_source="api",
        cache_to_db=False
    )
    
    if not candles1 or not candles2:
        print(f"❌ Failed to fetch candles")
        return
    
    print(f"✅ Got {len(candles1)} candles for {symbol1}")
    print(f"✅ Got {len(candles2)} candles for {symbol2}")
    
    # Align candles by timestamp
    print(f"\n[2] Aligning candles by timestamp...")
    df1 = pd.DataFrame(candles1).set_index('timestamp')
    df2 = pd.DataFrame(candles2).set_index('timestamp')
    
    # Inner join to get common timestamps
    df = pd.DataFrame({
        'close_1': df1['close'],
        'close_2': df2['close']
    }).dropna()
    
    print(f"✅ Aligned to {len(df)} common candles")
    
    if len(df) < 50:
        print(f"❌ Not enough aligned candles ({len(df)} < 50)")
        return
    
    # Generate signals
    print(f"\n[3] Generating signals with CointegrationStrategy...")
    strategy = CointegrationStrategy(
        lookback=120,
        z_entry=2.0,
        z_exit=0.5,
        use_adf=True
    )
    
    signals_df = strategy.generate_signals(df)
    
    # Find valid signals
    valid_signals = signals_df[signals_df['signal'] != 0]
    
    print(f"✅ Generated {len(signals_df)} signal rows")
    print(f"✅ Found {len(valid_signals)} valid signals (BUY/SELL)")
    
    if len(valid_signals) == 0:
        print(f"\n⚠️  No signals generated. Analyzing why...")
        
        # Check mean reversion
        mr_count = signals_df['is_mean_reverting'].sum()
        print(f"   - Mean reverting bars: {mr_count}/{len(signals_df)}")
        
        # Check z-scores
        z_scores = signals_df['z_score'].dropna()
        if len(z_scores) > 0:
            print(f"   - Z-score range: {z_scores.min():.2f} to {z_scores.max():.2f}")
            print(f"   - Z-score mean: {z_scores.mean():.2f}")
            extreme_z = z_scores[abs(z_scores) >= 2.0]
            print(f"   - Extreme z-scores (|z| >= 2.0): {len(extreme_z)}")
        
        return
    
    # Display signals with TP/SL and execution logic
    print(f"\n[4] Signal Details:")
    print(f"{'Timestamp':<20} {'Signal':<25} {'Z-Score':<10} {'MR':<3} {'Risk×':<6} {symbol1:<12} {symbol2:<12} {'Entry':<12} {'SL':<12} {'TP1':<12} {'TP2':<12} {'Spread Entry':<14} {'Spread SL':<14} {'Spread TP1':<14} {'Spread TP2':<14}")
    print("-" * 220)

    for idx, row in valid_signals.iterrows():
        # Determine action based on signal
        # Long spread (z <= -2.0): Buy Asset2, Sell β × Asset1
        # Short spread (z >= +2.0): Sell Asset2, Buy β × Asset1
        if row['signal'] == 1:  # Long spread
            signal_str = f"LONG (Buy {symbol2})"
        else:  # Short spread
            signal_str = f"SHORT (Sell {symbol2})"

        mr_str = "✓" if row['is_mean_reverting'] else "✗"

        # Get the last price for symbol1 at this timestamp
        last_price: float | None = None
        pair_price: float | None = None

        try:
            # Find position in df
            df_idx_raw = df.index.get_loc(idx)
            if isinstance(df_idx_raw, slice):
                df_idx_raw = df_idx_raw.start
            df_idx: int = int(df_idx_raw)  # type: ignore

            last_price = float(df.iloc[df_idx]['close_1'])
            pair_price = float(df.iloc[df_idx]['close_2'])
        except (KeyError, TypeError, ValueError):
            pass

        # Calculate TP/SL using cointegration statistics
        entry_price: float | None = last_price
        stop_loss: float | None = None
        take_profit_1: float | None = None
        take_profit_2: float | None = None

        if last_price and pair_price:
            try:
                # Compute beta and spread for this window
                df_idx_raw = df.index.get_loc(idx)
                if isinstance(df_idx_raw, slice):
                    df_idx_raw = df_idx_raw.start
                df_idx = int(df_idx_raw)  # type: ignore

                window_start: int = max(0, df_idx - 120)
                window_end: int = df_idx + 1
                window_df = df.iloc[window_start:window_end]

                close_1 = np.array(window_df['close_1'].values, dtype=float)
                close_2 = np.array(window_df['close_2'].values, dtype=float)

                beta = float(strategy._compute_beta(close_1, close_2))
                spread = close_2 - beta * close_1
                spread_mean = float(np.mean(spread))
                spread_std = float(np.std(spread))

                if spread_std > 0:
                    signal_direction = 1 if row['signal'] == 1 else -1

                    # Build z_history from ALL available data (not just 120-bar window)
                    # This gives us a better empirical tail distribution
                    all_close_1 = np.array(df['close_1'].values[:df_idx+1], dtype=float)
                    all_close_2 = np.array(df['close_2'].values[:df_idx+1], dtype=float)

                    all_beta = float(strategy._compute_beta(all_close_1, all_close_2))
                    all_spread = all_close_2 - all_beta * all_close_1
                    all_spread_mean = float(np.mean(all_spread))
                    all_spread_std = float(np.std(all_spread))

                    if all_spread_std > 0:
                        z_values = (all_spread - all_spread_mean) / all_spread_std
                        z_history = list(np.abs(z_values))  # Use absolute z-scores
                    else:
                        z_history = []



                    levels = calculate_levels(
                        price_x=last_price,
                        price_y=pair_price,
                        beta=beta,
                        spread_mean=spread_mean,
                        spread_std=spread_std,
                        z_entry=2.0,
                        signal=signal_direction,
                        z_history=z_history,
                        min_sl_buffer=1.2
                    )

                    # Extract spread levels and convert to Y prices
                    spread_levels = levels['spread_levels']
                    beta_val = levels['beta']

                    # Convert spread to Y price: y = spread + beta * x
                    entry_price = spread_levels['entry'] + beta_val * last_price
                    stop_loss = spread_levels['stop_loss'] + beta_val * last_price
                    take_profit_1 = spread_levels['take_profit_1'] + beta_val * last_price
                    take_profit_2 = spread_levels['take_profit_2'] + beta_val * last_price
            except Exception:
                pass  # Use None values if calculation fails

        # Format prices
        x_price_str = f"{last_price:.6f}" if last_price else "N/A"
        y_price_str = f"{entry_price:.6f}" if entry_price else "N/A"
        risk_mult = row.get('size_multiplier', 1.0)
        risk_str = f"{risk_mult:.2f}x"

        # Format spread values
        spread_entry_str = f"{spread_levels['entry']:.6f}" if spread_levels else "N/A"
        spread_sl_str = f"{spread_levels['stop_loss']:.6f}" if spread_levels else "N/A"
        spread_tp1_str = f"{spread_levels['take_profit_1']:.6f}" if spread_levels else "N/A"
        spread_tp2_str = f"{spread_levels['take_profit_2']:.6f}" if spread_levels else "N/A"

        print(f"{str(idx):<20} {signal_str:<25} {row['z_score']:>9.2f} {mr_str:<3} {risk_str:<6} {x_price_str:<12} {y_price_str:<12} {entry_price:>11.6f} {stop_loss:>11.6f} {take_profit_1:>11.6f} {take_profit_2:>11.6f} {spread_entry_str:<14} {spread_sl_str:<14} {spread_tp1_str:<14} {spread_tp2_str:<14}")

    print(f"\n✅ Test complete!")


async def main():
    """Test all pairs from screener results."""

    # Load screener results
    screener_file = Path(__file__).parent / "screener_results.json"

    if not screener_file.exists():
        print(f"❌ Screener results not found at {screener_file}")
        return

    with open(screener_file) as f:
        results = json.load(f)

    # Get timeframe from screener results (single source of truth)
    timeframe = results.get('timeframe', '1h')
    pairs = results.get('pairs', [])

    print(f"\n🔍 Testing {len(pairs)} pairs from screener results")
    print(f"   Timeframe: {timeframe}")

    for pair_data in pairs:
        # Symbols in screener results already have USDT suffix
        symbol1 = pair_data['symbol1']
        symbol2 = pair_data['symbol2']

        await test_pair_signals(
            symbol1=symbol1,
            symbol2=symbol2,
            timeframe=timeframe,
            lookback_days=30
        )


if __name__ == "__main__":
    asyncio.run(main())

