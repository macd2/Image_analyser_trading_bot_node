"""
Dry run for cointegration trade recalculation - shows what would be updated without making changes.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from trading_bot.db.client import get_connection, release_connection, query
from trading_bot.strategies.cointegration.price_levels import calculate_levels
from trading_bot.core.bybit_api_manager import BybitAPIManager
from trading_bot.config.settings_v2 import ConfigV2


def recalculate_cointegration_prices(
    price_x: float,
    price_y: float,
    beta: float,
    spread_mean: float,
    spread_std: float,
    z_score_at_entry: float,
    signal: int = -1,
    z_entry: float = 2.0,
    min_sl_buffer: float = 1.5
) -> dict:
    """Recalculate entry/SL/TP using correct spread level formula."""
    try:
        levels = calculate_levels(
            price_x=price_x,
            price_y=price_y,
            beta=beta,
            spread_mean=spread_mean,
            spread_std=spread_std,
            z_entry=z_entry,
            signal=signal,
            min_sl_buffer=min_sl_buffer
        )
        
        spread_levels = levels['spread_levels']
        
        # Convert spread levels to X prices: X = (Y - spread) / beta
        if beta != 0:
            entry_price = (price_y - spread_levels['entry']) / beta
            stop_loss = (price_y - spread_levels['stop_loss']) / beta
            take_profit = (price_y - spread_levels['take_profit_2']) / beta
        else:
            entry_price = price_x
            stop_loss = None
            take_profit = None
        
        # Calculate RR ratio
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        return {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rr_ratio': rr_ratio,
            'spread_levels': spread_levels,
            'success': True
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def main():
    conn = get_connection()
    
    # Load config
    instances = query(conn, "SELECT id FROM instances LIMIT 1", ())
    if not instances:
        print("❌ No instances found")
        release_connection(conn)
        return
    
    instance_id = instances[0]['id']
    config = ConfigV2.from_instance(instance_id)
    api_manager = BybitAPIManager(config)
    
    try:
        # Get first 3 cointegration recommendations for dry run
        recs = query(conn,
            "SELECT * FROM recommendations WHERE strategy_metadata IS NOT NULL AND recommendation != 'HOLD' LIMIT 3",
            ())
        
        print(f"DRY RUN: Analyzing {len(recs)} cointegration recommendations\n")
        
        for i, rec in enumerate(recs):
            print(f"\n{'='*80}")
            print(f"Recommendation {i+1}: {rec['symbol']}")
            print(f"{'='*80}")
            
            meta = rec['strategy_metadata']
            if isinstance(meta, str):
                meta = json.loads(meta)
            
            pair_symbol = meta.get('pair_symbol')
            beta = meta.get('beta')
            spread_mean = meta.get('spread_mean')
            spread_std = meta.get('spread_std')
            z_score = meta.get('z_score_at_entry', 2.0)
            
            print(f"Pair: {pair_symbol}")
            print(f"Beta: {beta:.6f}")
            print(f"Spread Mean: {spread_mean:.6f}")
            print(f"Spread Std: {spread_std:.6f}")
            print(f"Z-Score at Entry: {z_score:.6f}")
            print(f"Recommendation: {rec['recommendation']}")
            
            # Fetch candles at the time the signal was created
            try:
                # Convert created_at to milliseconds for Bybit API
                from datetime import datetime
                created_time = rec['created_at']
                if isinstance(created_time, str):
                    created_time = datetime.fromisoformat(created_time.replace('Z', '+00:00'))

                end_ts = int(created_time.timestamp() * 1000)

                print(f"\nFetching candles at signal creation time: {created_time}")

                response_x = api_manager.get_kline(symbol=rec['symbol'], interval='60', limit=100, end=end_ts)
                response_y = api_manager.get_kline(symbol=pair_symbol, interval='60', limit=100, end=end_ts)

                candles_x = response_x.get('result', {}).get('list', [])
                candles_y = response_y.get('result', {}).get('list', [])

                if not candles_x or not candles_y:
                    print("❌ No candles fetched at signal time")
                    continue

                # Get the close price from the last candle (most recent at that time)
                price_x = float(candles_x[-1][4])
                price_y = float(candles_y[-1][4])

                print(f"\nPrices at Signal Creation Time:")
                print(f"  {rec['symbol']}: {price_x:.6f}")
                print(f"  {pair_symbol}: {price_y:.6f}")
                
                # Calculate spread
                current_spread = price_y - beta * price_x
                z_current = (current_spread - spread_mean) / spread_std if spread_std > 0 else 0
                
                print(f"\nSpread Analysis:")
                print(f"  Current Spread: {current_spread:.6f}")
                print(f"  Current Z-Score: {z_current:.6f}")
                
                signal = -1 if rec['recommendation'] == 'SELL' else 1
                
                result = recalculate_cointegration_prices(
                    price_x=price_x,
                    price_y=price_y,
                    beta=beta,
                    spread_mean=spread_mean,
                    spread_std=spread_std,
                    z_score_at_entry=z_score,
                    signal=signal,
                    z_entry=abs(z_score)
                )
                
                if result['success']:
                    sl = result['spread_levels']

                    print(f"\nSpread Levels (in spread space):")
                    print(f"  Entry:  {sl['entry']:.6f}")
                    print(f"  SL:     {sl['stop_loss']:.6f}")
                    print(f"  TP:     {sl['take_profit_2']:.6f}")

                    # Convert to Y prices: Y = spread + beta * X
                    entry_y = sl['entry'] + beta * price_x
                    sl_y = sl['stop_loss'] + beta * price_x
                    tp_y = sl['take_profit_2'] + beta * price_x

                    print(f"\nConverted to Y prices (pair symbol): Y = spread + beta * X")
                    print(f"  Entry: {entry_y:.6f}")
                    print(f"  SL:    {sl_y:.6f}")
                    print(f"  TP:    {tp_y:.6f}")

                    # Convert to X prices: X = (Y - spread) / beta
                    entry_x = (price_y - sl['entry']) / beta if beta != 0 else 0
                    sl_x = (price_y - sl['stop_loss']) / beta if beta != 0 else 0
                    tp_x = (price_y - sl['take_profit_2']) / beta if beta != 0 else 0

                    print(f"\nConverted to X prices (primary symbol): X = (Y - spread) / beta")
                    print(f"  Entry: {entry_x:.6f}")
                    print(f"  SL:    {sl_x:.6f}")
                    print(f"  TP:    {tp_x:.6f}")

                    # Calculate RR for X prices
                    risk_x = abs(entry_x - sl_x)
                    reward_x = abs(tp_x - entry_x)
                    rr_x = reward_x / risk_x if risk_x > 0 else 0

                    print(f"\nRisk-Reward Ratio (X prices): {rr_x:.4f}")
                else:
                    print(f"❌ Calculation error: {result['error']}")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
    
    finally:
        release_connection(conn)


if __name__ == "__main__":
    main()

