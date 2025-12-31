#!/usr/bin/env python3
"""
Analyze z-score values across all candles for a trade to understand why it's not exiting.

This script shows:
1. Z-score at each candle
2. When z-score crosses the exit threshold
3. Why the exit condition is not being triggered

Usage:
  python3 analyze_z_scores.py --trade-id TRADE_ID
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.db.client import get_connection, query, query_one, release_connection


def analyze_trade_z_scores(trade_id: str) -> int:
    """Analyze z-scores for a specific trade."""
    conn = get_connection()
    try:
        # Fetch trade
        trade = query_one(conn, """
            SELECT id, symbol, side, entry_price, stop_loss, take_profit,
                   strategy_metadata, filled_at, created_at
            FROM trades
            WHERE id = ?
        """, (trade_id,))
        
        if not trade:
            print(f"❌ Trade not found: {trade_id}")
            return 1
        
        # Parse metadata
        metadata = trade.get('strategy_metadata', {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        print(f"\n{'='*100}")
        print(f"TRADE: {trade['symbol']} | Side: {trade['side']}")
        print(f"Entry: {trade['entry_price']} | SL: {trade['stop_loss']} | TP: {trade['take_profit']}")
        print(f"Filled at: {trade['filled_at']}")
        print(f"{'='*100}\n")
        
        # Get metadata values
        beta = metadata.get('beta')
        spread_mean = metadata.get('spread_mean')
        spread_std = metadata.get('spread_std')
        z_exit_threshold = metadata.get('z_exit_threshold')
        pair_symbol = metadata.get('pair_symbol')
        
        if not all(v is not None for v in [beta, spread_mean, spread_std, z_exit_threshold]):
            print("❌ Missing metadata values!")
            return 1
        
        print(f"Metadata:")
        print(f"  Pair: {pair_symbol}")
        print(f"  Beta: {beta:.6f}")
        print(f"  Spread mean: {spread_mean:.6f}")
        print(f"  Spread std: {spread_std:.6f}")
        print(f"  Z-exit threshold: {z_exit_threshold:.6f}")
        print(f"  Max spread deviation: {metadata.get('max_spread_deviation', 'N/A')}\n")
        
        # Fetch candles
        candles = query(conn, """
            SELECT start_time as timestamp, close_price as close
            FROM klines
            WHERE symbol = ? AND timeframe = '1h'
            ORDER BY start_time ASC
        """, (trade['symbol'],))
        
        pair_candles = query(conn, """
            SELECT start_time as timestamp, close_price as close
            FROM klines
            WHERE symbol = ? AND timeframe = '1h'
            ORDER BY start_time ASC
        """, (pair_symbol,))
        
        if not candles or not pair_candles:
            print("❌ No candles found!")
            return 1
        
        # Align candles by timestamp
        candle_dict = {c['timestamp']: c['close'] for c in candles}
        pair_dict = {c['timestamp']: c['close'] for c in pair_candles}
        common_ts = sorted(set(candle_dict.keys()) & set(pair_dict.keys()))
        
        if not common_ts:
            print("❌ No common timestamps between main and pair candles!")
            return 1
        
        print(f"Candles: {len(candles)} | Pair candles: {len(pair_candles)} | Common: {len(common_ts)}\n")
        print(f"{'Candle':<8} {'Timestamp':<20} {'Main':<12} {'Pair':<12} {'Spread':<12} {'Z-Score':<12} {'Exit?':<8}")
        print(f"{'-'*100}")
        
        exit_found = False
        for i, ts in enumerate(common_ts):
            main_price = candle_dict[ts]
            pair_price = pair_dict[ts]
            spread = pair_price - beta * main_price
            z_score = (spread - spread_mean) / spread_std if spread_std > 0 else 0
            threshold_crossed = abs(z_score) <= z_exit_threshold
            
            dt = datetime.fromtimestamp(ts / 1000).isoformat()
            exit_str = "✅ EXIT" if threshold_crossed else ""
            
            print(f"{i:<8} {dt:<20} {main_price:<12.6f} {pair_price:<12.6f} {spread:<12.6f} {z_score:<12.6f} {exit_str:<8}")
            
            if threshold_crossed and not exit_found:
                exit_found = True
                print(f"  >>> FIRST EXIT SIGNAL AT CANDLE {i}")
        
        if not exit_found:
            print(f"\n⚠️  NO EXIT SIGNAL FOUND in {len(common_ts)} candles!")
            print(f"   Z-exit threshold: {z_exit_threshold}")
            print(f"   Min |Z-score|: {min(abs(z) for z in [(pair_dict[ts] - beta * candle_dict[ts] - spread_mean) / spread_std for ts in common_ts]):.6f}")
        
        return 0
        
    finally:
        release_connection(conn)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--trade-id', required=True, help='Trade ID to analyze')
    args = parser.parse_args()
    
    return analyze_trade_z_scores(args.trade_id)


if __name__ == "__main__":
    sys.exit(main())

