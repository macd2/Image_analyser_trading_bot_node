#!/usr/bin/env python3
"""
Full Pair Screener - Screen all 500+ symbols for cointegrated pairs.

Fetches candles in parallel, screens all pairs, filters correlated pairs,
and saves results as JSON.

Usage:
    source venv/bin/activate
    cd python/trading_bot/strategies/cointegration
    python run_full_screener.py

Or from project root:
    PYTHONPATH=python python python/trading_bot/strategies/cointegration/run_full_screener.py
"""

import asyncio
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add python folder to path if not already there
python_path = os.path.join(os.path.dirname(__file__), '..', '..', '..')
if python_path not in sys.path:
    sys.path.insert(0, python_path)

from prompt_performance.core.bybit_symbols import get_bybit_symbols_cached
from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.strategies.cointegration.pair_screener import PairScreener
import pandas as pd

# Setup logger
logger = logging.getLogger(__name__)


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


async def fetch_all_candles(symbols: list, batch_size: int = 10, candle_limit: int = 1000) -> dict:
    """Fetch candles for all symbols in parallel batches.

    Args:
        symbols: List of symbols to fetch candles for
        batch_size: Number of symbols per batch (default: 10)
        candle_limit: Number of candles to fetch per symbol (default: 500)
    """
    adapter = CandleAdapter()
    symbol_candles = {}

    logger.info(f"📊 [SCREENER] Fetching candles for {len(symbols)} symbols (batch_size={batch_size}, limit={candle_limit})")
    print(f"Fetching candles for {len(symbols)} symbols (batch_size={batch_size}, limit={candle_limit})...")

    for batch_num, i in enumerate(range(0, len(symbols), batch_size), 1):
        batch = symbols[i:i + batch_size]
        tasks = []

        for symbol in batch:
            task = adapter.get_candles(
                symbol,
                timeframe='1h',
                limit=candle_limit,
                min_candles=120,
                cache_to_db=False,
                prefer_source="api"  # Prefer fresh API data for screener
            )
            tasks.append((symbol, task))

        # Fetch batch in parallel
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

        # Collect batch summary
        batch_summary = []
        for (symbol, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                batch_summary.append(f"❌ {symbol}")
                logger.warning(f"⚠️  [SCREENER] {symbol} - Error: {str(result)[:50]}")
            elif result:
                symbol_candles[symbol] = result
                batch_summary.append(f"✅ {symbol} - 1h - {len(result)} candles - api")
            else:
                batch_summary.append(f"⊘ {symbol}")
                logger.warning(f"⚠️  [SCREENER] {symbol} - No candles")

        # Log batch summary
        batch_info = f"📦 [SCREENER] Batch {batch_num}: {', '.join(batch_summary)}"
        logger.info(batch_info)
        print(batch_info)

    return symbol_candles


def filter_correlated_pairs(results: pd.DataFrame) -> pd.DataFrame:
    """Keep only best confidence pair per symbol."""
    used_symbols = set()
    filtered = []
    
    for _, row in results.iterrows():
        sym1, sym2 = row['symbol1'], row['symbol2']
        if sym1 not in used_symbols and sym2 not in used_symbols:
            used_symbols.add(sym1)
            used_symbols.add(sym2)
            filtered.append(row)
    
    return pd.DataFrame(filtered)


async def run_screener(
    timeframe: str = "1h",
    instance_id: str = "default",
    min_volume_usd: int = 1_000_000,
    batch_size: int = 15,
    candle_limit: int = 500,
    verbose: bool = True,
) -> Dict[str, str]:
    """
    Run full screener and return discovered pairs.

    Args:
        timeframe: Analysis timeframe (e.g., "1h", "4h", "1d")
        instance_id: Instance ID for cache file naming (default: "default")
        min_volume_usd: Minimum 24h volume in USD for filtering (default: 1M)
        batch_size: Number of symbols per batch for parallel fetching (default: 15)
        candle_limit: Number of candles to fetch per symbol (default: 500)
        verbose: Print progress messages (default: True)

    Returns:
        Dictionary mapping symbol1 -> symbol2 for discovered pairs
    """
    logger.info(f"🔍 [SCREENER] Starting full pair screener (timeframe: {timeframe}, min_volume: ${min_volume_usd/1e6:.1f}M)")

    if verbose:
        print("=" * 70)
        print("FULL PAIR SCREENER")
        print(f"Timeframe: {timeframe}")
        print(f"Instance ID: {instance_id}")
        print(f"Min Volume: ${min_volume_usd/1e6:.1f}M")
        print(f"Batch Size: {batch_size}")
        print("=" * 70)

    # Step 1: Get all symbols
    logger.info(f"📋 [SCREENER] STEP 1: Fetching available symbols...")
    print("\nSTEP 1: Fetching available symbols...")
    all_symbols = get_bybit_symbols_cached(category="linear")
    logger.info(f"📋 [SCREENER] Found {len(all_symbols)} total symbols")
    print(f"Total symbols: {len(all_symbols)}")

    # Step 2: Filter symbols (basic filters)
    logger.info(f"🔎 [SCREENER] STEP 2: Filtering symbols (USDT, no futures, no stablecoins, no meme coins)...")
    print("\nSTEP 2: Filtering symbols (USDT, no futures, no stablecoins, no meme coins)...")
    stablecoins = {'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'FRAX', 'LUSD'}

    filtered = []
    for s in all_symbols:
        if not s.endswith('USDT') or '-' in s:
            continue
        base_coin = s.replace('USDT', '')
        if base_coin in stablecoins or (base_coin and base_coin[0].isdigit()):
            continue
        filtered.append(s)

    logger.info(f"🔎 [SCREENER] After basic filters: {len(filtered)} symbols")
    print(f"After basic filters: {len(filtered)} symbols")

    # Step 3: Fetch tickers and filter by volume
    logger.info(f"💰 [SCREENER] STEP 3: Fetching tickers and filtering by volume (${min_volume_usd/1e6:.1f}M minimum)...")
    print(f"\nSTEP 3: Fetching tickers and filtering by volume (${min_volume_usd/1e6:.1f}M minimum)...")
    symbol_volumes = fetch_tickers_for_volume(filtered)

    filtered_by_volume = [
        s for s in filtered
        if symbol_volumes.get(s, 0) >= min_volume_usd
    ]

    logger.info(f"💰 [SCREENER] After volume filter: {len(filtered_by_volume)} symbols (>= ${min_volume_usd/1e6:.1f}M)")
    print(f"After volume filter: {len(filtered_by_volume)} symbols (>= ${min_volume_usd/1e6:.1f}M)")

    # Step 4: Fetch candles in parallel
    logger.info(f"📊 [SCREENER] STEP 4: Fetching candles in parallel (batch_size: {batch_size}, limit: {candle_limit})...")
    print("\nSTEP 4: Fetching candles in parallel...")
    symbol_candles = await fetch_all_candles(filtered_by_volume, batch_size=batch_size, candle_limit=candle_limit)
    logger.info(f"📊 [SCREENER] Successfully fetched {len(symbol_candles)} symbols with candles")
    print(f"\nSuccessfully fetched {len(symbol_candles)} symbols")

    if len(symbol_candles) < 2:
        logger.warning(f"⚠️  [SCREENER] Not enough symbols ({len(symbol_candles)}) for pair screening")
        print("❌ Not enough symbols")
        return False

    # Step 5: Screen pairs
    logger.info(f"🔗 [SCREENER] STEP 5: Screening pairs for cointegration...")
    print("\nSTEP 5: Screening pairs...")
    screener = PairScreener(lookback_days=120, min_data_points=100)
    results = screener.screen_pairs(
        symbol_candles=symbol_candles,
        min_volume_usd=min_volume_usd
    )

    if results.empty:
        logger.warning(f"⚠️  [SCREENER] No cointegrated pairs found")
        print("❌ No cointegrated pairs found")
        return False

    logger.info(f"🔗 [SCREENER] Found {len(results)} cointegrated pairs")
    print(f"Found {len(results)} cointegrated pairs")

    # Step 6: Filter correlated pairs
    logger.info(f"🔗 [SCREENER] STEP 6: Filtering correlated pairs...")
    print("\nSTEP 6: Filtering correlated pairs...")
    final_results = filter_correlated_pairs(results)
    logger.info(f"🔗 [SCREENER] Final {len(final_results)} independent pairs after correlation filtering")
    print(f"Final {len(final_results)} independent pairs")

    # Step 7: Save results
    logger.info(f"💾 [SCREENER] STEP 7: Saving results to cache...")
    print("\nSTEP 7: Saving results...")
    cache_dir = Path(__file__).parent / "screener_cache"
    cache_dir.mkdir(exist_ok=True)
    output_file = cache_dir / f"{instance_id}_{timeframe}.json"

    # Convert to JSON-serializable format
    results_dict = {
        'timestamp': datetime.now().isoformat(),
        'timeframe': timeframe,
        'total_symbols_screened': len(symbol_candles),
        'total_pairs_found': len(results),
        'independent_pairs': len(final_results),
        'pairs': final_results.to_dict('records')
    }

    with open(output_file, 'w') as f:
        json.dump(results_dict, f, indent=2)

    logger.info(f"✅ [SCREENER] Results saved: {len(final_results)} independent pairs (instance={instance_id}, timeframe={timeframe})")
    print(f"✅ Results saved to {output_file} (instance={instance_id}, timeframe={timeframe})")
    
    # Display results
    if verbose:
        print("\n" + "=" * 70)
        print("FINAL INDEPENDENT PAIRS")
        print("=" * 70)
        print(final_results[['pair', 'adf_p', 'hurst', 'half_life', 'cv', 'confidence_score']].to_string(index=False))

    # Convert pairs to dictionary format (symbol1 -> symbol2)
    pairs_dict = {}
    for _, row in final_results.iterrows():
        pair = row['pair']
        if '|' in pair:
            symbol1, symbol2 = pair.split('|')
            pairs_dict[symbol1] = symbol2

    logger.info(f"✅ [SCREENER] Screener complete: {len(pairs_dict)} pairs ready for trading")
    return pairs_dict


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Screen all symbols for cointegrated pairs"
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1h",
        choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
        help="Analysis timeframe (default: 1h)"
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        default="default",
        help="Instance ID for cache file naming (default: default)"
    )
    parser.add_argument(
        "--min-volume-usd",
        type=int,
        default=1_000_000,
        help="Minimum 24h volume in USD for filtering (default: 1000000)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=15,
        help="Number of symbols per batch for parallel fetching (default: 15)"
    )
    parser.add_argument(
        "--candle-limit",
        type=int,
        default=1000,
        help="Number of candles to fetch per symbol (default: 500)"
    )

    args = parser.parse_args()

    try:
        pairs = asyncio.run(run_screener(
            timeframe=args.timeframe,
            instance_id=args.instance_id,
            min_volume_usd=args.min_volume_usd,
            batch_size=args.batch_size,
            candle_limit=args.candle_limit,
            verbose=True
        ))
        sys.exit(0 if pairs else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

