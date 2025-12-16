#!/usr/bin/env python3
"""
Test script for pair screener.

Filters available Bybit symbols and screens for cointegrated pairs.

Usage:
    source venv/bin/activate
    python test_pair_screener.py
"""

import asyncio
import sys
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python'))

from prompt_performance.core.bybit_symbols import get_bybit_symbols_cached
from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.strategies.cointegration.pair_screener import PairScreener
import numpy as np
import pandas as pd


def fetch_ticker(symbol: str) -> tuple:
    """Fetch ticker for a single symbol. Returns (symbol, turnover24h)."""
    try:
        url = "https://api.bybit.com/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get("retCode") == 0:
            items = data.get("result", {}).get("list", [])
            if items:
                turnover = float(items[0].get("turnover24h", 0))
                return (symbol, turnover)
    except Exception:
        pass

    return (symbol, 0)


def fetch_tickers_for_volume(symbols: list, max_workers: int = 10) -> dict:
    """Fetch tickers concurrently to get 24h volume for all symbols."""
    print(f"Fetching tickers for {len(symbols)} symbols (concurrent, max_workers={max_workers})...")

    symbol_volumes = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_ticker, symbol): symbol for symbol in symbols}

        for future in as_completed(futures):
            completed += 1
            if completed % 50 == 0:
                print(f"  Progress: {completed}/{len(symbols)}")

            symbol, turnover = future.result()
            symbol_volumes[symbol] = turnover

    return symbol_volumes


async def test_screener():
    """Test pair screener with real data."""
    
    # Step 1: Get available symbols
    print("=" * 70)
    print("STEP 1: Fetching available symbols from Bybit")
    print("=" * 70)
    
    all_symbols = get_bybit_symbols_cached(category="linear")
    print(f"Total available symbols: {len(all_symbols)}\n")
    
    # Step 2: Filter symbols (USDT only, no futures, no stablecoins, no meme coins)
    print("=" * 70)
    print("STEP 2: Filtering symbols (USDT only, no futures, no stablecoins, no meme coins)")
    print("=" * 70)

    # Stablecoins to exclude
    stablecoins = {'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'FRAX', 'LUSD'}

    filtered = []
    for s in all_symbols:
        # Must end with USDT
        if not s.endswith('USDT'):
            continue

        # Remove futures with dates (e.g., BTCUSDT-26DEC25)
        if '-' in s:
            continue

        # Extract base coin (everything before USDT)
        base_coin = s.replace('USDT', '')

        # Skip stablecoins
        if base_coin in stablecoins:
            continue

        # Skip meme coins (those starting with numbers like 1000PEPE, 10000SHIB)
        if base_coin and base_coin[0].isdigit():
            continue

        filtered.append(s)

    print(f"After basic filters: {len(filtered)} symbols")

    # Step 3: Fetch tickers and filter by volume
    print("\n" + "=" * 70)
    print("STEP 3: Fetching tickers and filtering by volume ($50M minimum)")
    print("=" * 70)

    symbol_volumes = fetch_tickers_for_volume(filtered)

    min_volume_usd = 50_000_000  # $50M
    filtered_by_volume = [
        s for s in filtered
        if symbol_volumes.get(s, 0) >= min_volume_usd
    ]

    print(f"After volume filter: {len(filtered_by_volume)} symbols (>= ${min_volume_usd/1e6:.0f}M)\n")

    # Step 4: Select a subset for testing (top 20 by volume/popularity)
    # For now, use a curated list of liquid pairs
    # Use filtered symbols (already filtered by volume)
    test_symbols = filtered_by_volume[:30]
    print(f"Testing with {len(test_symbols)} symbols: {test_symbols}\n")
    
    # Step 5: Fetch candles for all symbols
    print("=" * 70)
    print("STEP 5: Fetching candles for all symbols")
    print("=" * 70)

    adapter = CandleAdapter()
    symbol_candles = {}

    for symbol in test_symbols:
        try:
            # Check if symbol exists first
            exists = await adapter.symbol_exists(symbol)
            if not exists:
                print(f"⊘ {symbol:12} - Not available on Bybit")
                continue

            candles = await adapter.get_candles(
                symbol,
                timeframe='1h',
                limit=500,
                min_candles=120,
                cache_to_db=False,
                prefer_source="api"  # Prefer fresh API data for screener
            )

            if candles:
                symbol_candles[symbol] = candles
                print(f"✅ {symbol:12} - {len(candles)} candles")
            else:
                print(f"❌ {symbol:12} - No candles")
        except Exception as e:
            print(f"❌ {symbol:12} - Error: {str(e)[:50]}")

    print(f"\nSuccessfully fetched {len(symbol_candles)} symbols\n")

    if len(symbol_candles) < 2:
        print("❌ Not enough symbols with data")
        return False

    # Step 6: Run screener
    print("=" * 70)
    print("STEP 6: Screening for cointegrated pairs")
    print("=" * 70)

    screener = PairScreener(lookback_days=120, min_data_points=100)
    results = screener.screen_pairs(
        symbol_candles=symbol_candles,
        min_volume_usd=1_000_000,
        max_pairs=20
    )
    
    if results.empty:
        print("❌ No cointegrated pairs found")
        return False

    print(f"\n✅ Found {len(results)} cointegrated pairs (before filtering):\n")
    print(results.to_string(index=False))

    # Step 7: Filter out correlated pairs (keep only best if same symbol appears multiple times)
    print("\n" + "=" * 70)
    print("STEP 7: Filtering correlated pairs (keep best confidence per symbol)")
    print("=" * 70)

    # Track which symbols are already used
    used_symbols = set()
    filtered_results = []

    for _, row in results.iterrows():
        sym1 = row['symbol1']
        sym2 = row['symbol2']

        # Skip if either symbol is already used in a higher-confidence pair
        if sym1 in used_symbols or sym2 in used_symbols:
            print(f"⊘ Skipping {row['pair']:20} - symbol already used in higher confidence pair")
            continue

        # Keep this pair
        used_symbols.add(sym1)
        used_symbols.add(sym2)
        filtered_results.append(row)
        print(f"✅ Keeping {row['pair']:20} - confidence: {row['confidence_score']:.4f}")

    if not filtered_results:
        print("❌ No independent pairs found after filtering")
        return False

    final_results = pd.DataFrame(filtered_results)
    print(f"\n✅ Final {len(final_results)} independent pairs:\n")
    print(final_results.to_string(index=False))

    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_screener())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

