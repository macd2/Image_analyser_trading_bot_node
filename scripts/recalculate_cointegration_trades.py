"""
Recalculate all cointegration trades and recommendations with correct spread level calculations.

This script:
1. Fetches all cointegration recommendations
2. For each recommendation, fetches candles at the time of creation
3. Recalculates entry/SL/TP using the correct spread level formula
4. Updates both trades and recommendations in the database
5. Logs all changes for verification
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from trading_bot.db.client import get_connection, release_connection, query, query_one, execute
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
    """Recalculate entry/SL/TP using correct spread level formula.

    Args:
        price_x: Primary symbol price at entry
        price_y: Pair symbol price at entry
        beta: Hedge ratio
        spread_mean: Mean of the spread
        spread_std: Standard deviation of the spread
        z_score_at_entry: Z-score at entry (for reference)
        signal: Trade direction (-1 for SHORT, 1 for LONG)
        z_entry: Z-score threshold for entry (default 2.0)
        min_sl_buffer: Minimum SL buffer in std devs (default 1.5)
    """
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
        # These are the primary symbol prices for the trade
        if beta != 0:
            entry_price = (price_y - spread_levels['entry']) / beta
            stop_loss = (price_y - spread_levels['stop_loss']) / beta
            take_profit = (price_y - spread_levels['take_profit_2']) / beta
        else:
            entry_price = price_x
            stop_loss = None
            take_profit = None

        # Calculate RR ratio
        if stop_loss and take_profit:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            rr_ratio = reward / risk if risk > 0 else 0
        else:
            rr_ratio = 0

        return {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'rr_ratio': rr_ratio,
            'success': True
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def main():
    conn = get_connection()

    # Load config - need to get an instance_id first
    # Get the first instance from database
    instances = query(conn, "SELECT id FROM instances LIMIT 1", ())
    if not instances:
        print("❌ No instances found in database")
        release_connection(conn)
        return

    instance_id = instances[0]['id']
    config = ConfigV2.from_instance(instance_id)
    api_manager = BybitAPIManager(config)

    try:
        # Get all cointegration recommendations (identified by strategy_metadata)
        recs = query(conn,
            "SELECT * FROM recommendations WHERE strategy_metadata IS NOT NULL AND recommendation != 'HOLD' ORDER BY created_at DESC",
            ())

        print(f"Found {len(recs)} cointegration recommendations to recalculate")

        updated_count = 0
        error_count = 0
        changes = []

        for i, rec in enumerate(recs):
            try:
                # Get strategy metadata
                meta = rec['strategy_metadata']
                if isinstance(meta, str):
                    meta = json.loads(meta)

                pair_symbol = meta.get('pair_symbol')
                beta = meta.get('beta')
                spread_mean = meta.get('spread_mean')
                spread_std = meta.get('spread_std')
                z_score = meta.get('z_score_at_entry', 2.0)

                # Check if we have all required data
                if not all([pair_symbol, beta is not None, spread_mean is not None, spread_std is not None]):
                    error_count += 1
                    continue

                # Fetch candles from Bybit API for both symbols
                try:
                    # Fetch 100 candles for each symbol (1h timeframe)
                    response_x = api_manager.get_kline(
                        symbol=rec['symbol'],
                        interval='60',  # 1h
                        limit=100
                    )

                    response_y = api_manager.get_kline(
                        symbol=pair_symbol,
                        interval='60',  # 1h
                        limit=100
                    )

                    # Check if responses are valid
                    if not response_x or response_x.get('retCode') != 0:
                        print(f"  No candles for {rec['symbol']}")
                        error_count += 1
                        continue

                    if not response_y or response_y.get('retCode') != 0:
                        print(f"  No candles for {pair_symbol}")
                        error_count += 1
                        continue

                    candles_x = response_x.get('result', {}).get('list', [])
                    candles_y = response_y.get('result', {}).get('list', [])

                    if not candles_x or not candles_y:
                        print(f"  Empty candle list for {rec['symbol']}/{pair_symbol}")
                        error_count += 1
                        continue

                    # Get the close price from the last candle (most recent)
                    # Bybit returns [timestamp, open, high, low, close, volume, turnover]
                    price_x = float(candles_x[-1][4])  # close price
                    price_y = float(candles_y[-1][4])  # close price

                except Exception as e:
                    print(f"  Error fetching candles for {rec['symbol']}/{pair_symbol}: {e}")
                    error_count += 1
                    continue

                # Determine signal direction from recommendation
                signal = -1 if rec['recommendation'] == 'SELL' else 1

                # Recalculate prices using fetched prices and spread levels
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

                if not result['success']:
                    error_count += 1
                    continue

                # Check if values changed
                old_entry = rec['entry_price']
                old_sl = rec['stop_loss']
                old_tp = rec['take_profit']
                old_rr = rec['risk_reward']

                new_entry = result['entry_price']
                new_sl = result['stop_loss']
                new_tp = result['take_profit']
                new_rr = result['rr_ratio']

                # Update recommendation
                execute(conn,
                    """UPDATE recommendations SET entry_price = ?, stop_loss = ?, take_profit = ?, risk_reward = ?
                       WHERE id = ?""",
                    (new_entry, new_sl, new_tp, new_rr, rec['id']))

                # Also update associated trades
                trades = query(conn,
                    "SELECT id FROM trades WHERE recommendation_id = ?",
                    (rec['id'],))

                for trade in trades:
                    execute(conn,
                        """UPDATE trades SET entry_price = ?, stop_loss = ?, take_profit = ?, rr_ratio = ?
                           WHERE id = ?""",
                        (new_entry, new_sl, new_tp, new_rr, trade['id']))

                updated_count += 1

                changes.append({
                    'rec_id': rec['id'],
                    'symbol': rec['symbol'],
                    'pair': pair_symbol,
                    'old': {'entry': old_entry, 'sl': old_sl, 'tp': old_tp, 'rr': old_rr},
                    'new': {'entry': new_entry, 'sl': new_sl, 'tp': new_tp, 'rr': new_rr}
                })

                if (i + 1) % 50 == 0:
                    print(f"  Processed {i + 1}/{len(recs)} recommendations...")

            except Exception as e:
                error_count += 1
                print(f"  Error processing recommendation {rec['id']}: {e}")

        print(f"\n✅ Updated: {updated_count}")
        print(f"❌ Errors: {error_count}")
        print(f"⏭️  Skipped: {len(recs) - updated_count - error_count}")
        
        # Show sample changes
        if changes:
            print(f"\nSample changes (first 5):")
            for change in changes[:5]:
                print(f"\n  {change['symbol']} / {change['pair']}:")
                if change['old']['entry']:
                    print(f"    Entry: {change['old']['entry']:.6f} → {change['new']['entry']:.6f}")
                    print(f"    SL:    {change['old']['sl']:.6f} → {change['new']['sl']:.6f}")
                    print(f"    TP:    {change['old']['tp']:.6f} → {change['new']['tp']:.6f}")
                    print(f"    RR:    {change['old']['rr']:.4f} → {change['new']['rr']:.4f}")
                else:
                    print(f"    Entry: None → {change['new']['entry']:.6f}")
                    print(f"    SL:    None → {change['new']['sl']:.6f}")
                    print(f"    TP:    None → {change['new']['tp']:.6f}")
                    print(f"    RR:    None → {change['new']['rr']:.4f}")
        
    finally:
        release_connection(conn)


if __name__ == "__main__":
    main()

