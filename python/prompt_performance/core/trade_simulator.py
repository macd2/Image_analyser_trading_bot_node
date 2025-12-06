import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .utils import generate_prompt_hash

logger = logging.getLogger(__name__)

class TradeSimulator:
    """Simulates trades based on analysis recommendations and historical candles."""

    def __init__(self):
        pass

    def _extract_prompt_version(self, record: Dict[str, Any]) -> str:
        """Extract prompt version from record data."""
        analysis_data = record.get('analysis_data', {})

        # Try nested analysis data first (this is where prompt_version is stored)
        nested_analysis = analysis_data.get('analysis', {})
        if nested_analysis.get('prompt_version'):
            return nested_analysis['prompt_version']

        # Try direct prompt_version
        if analysis_data.get('prompt_version'):
            return analysis_data['prompt_version']

        # Fallback to model_id if prompt_version not found
        if nested_analysis.get('model_id'):
            return nested_analysis['model_id']

        # Try to extract from analysis_prompt
        analysis_prompt = nested_analysis.get('analysis_prompt', '')
        if analysis_prompt:
            # Create a simple hash-based version from the prompt
            import hashlib
            prompt_hash = hashlib.md5(analysis_prompt[:200].encode()).hexdigest()[:8]
            return f"prompt_{prompt_hash}"

        # Fallback
        return 'unknown'

    def _extract_prompt_hash(self, record: Dict[str, Any]) -> str:
        """Extract prompt hash from dedicated analysis_prompt column."""
        # Check if hash was already generated during data loading
        if 'prompt_hash' in record:
            return record['prompt_hash']

        # Fallback: generate hash from dedicated column
        analysis_prompt = record.get('analysis_prompt', '')
        if analysis_prompt and analysis_prompt.strip():
            return generate_prompt_hash(analysis_prompt)

        # Final fallback
        return 'empty'

    def _find_entry_candle_index(self, record: Dict[str, Any], candles: List[Dict[str, Any]]) -> Optional[int]:
        """Find the index of the candle that corresponds to the entry timestamp."""
        if not candles:
            return None

        record_timestamp = record.get('timestamp')
        if record_timestamp is None:
            # No timestamp provided (e.g., unit tests) -> start from the first candle
            return 0

        # Convert record timestamp to milliseconds for comparison
        if isinstance(record_timestamp, str):
            try:
                # Handle ISO format strings
                if 'T' in record_timestamp:
                    dt = datetime.fromisoformat(record_timestamp.replace('Z', '+00:00'))
                else:
                    dt = datetime.fromisoformat(record_timestamp)
                record_ms = int(dt.timestamp() * 1000)
            except ValueError:
                return None
        elif isinstance(record_timestamp, (int, float)):
            # Assume already in ms if > 1e10, otherwise convert from seconds
            if record_timestamp > 1e10:
                record_ms = int(record_timestamp)
            else:
                record_ms = int(record_timestamp * 1000)
        else:
            return None

        # Find the closest candle to the record timestamp
        min_diff = float('inf')
        closest_index = None

        for i, candle in enumerate(candles):
            candle_timestamp = candle.get('start_time', 0)

            # Ensure candle timestamp is in milliseconds
            if candle_timestamp < 1e10:  # If in seconds, convert to ms
                candle_timestamp = int(candle_timestamp * 1000)

            diff = abs(candle_timestamp - record_ms)
            if diff < min_diff:
                min_diff = diff
                closest_index = i

        return closest_index

    def simulate_trade(self, record: Dict[str, Any], candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Simulate a trade for a single analysis record using historical candles.

        Args:
            record: Analysis record with recommendation, prices, etc.
            candles: List of candles sorted by start_time ASC

        Returns:
            Simulation result with outcome, duration, etc.
        """
        if not candles:
            return {
                'outcome': 'no_data',
                'duration_candles': 0,
                'achieved_rr': 0.0,
                'exit_price': None,
                'exit_candle_index': None,
                'entry_candle_index': None,
                'realized_pnl_price': None,
                'realized_pnl_percent': None
            }

        # Find the entry candle index based on the record timestamp
        entry_candle_index = self._find_entry_candle_index(record, candles)

        if entry_candle_index is None:
            return {
                'outcome': 'entry_candle_not_found',
                'duration_candles': 0,
                'achieved_rr': 0.0,
                'exit_price': None,
                'exit_candle_index': None,
                'entry_candle_index': None,
                'realized_pnl_price': None,
                'realized_pnl_percent': None
            }

        recommendation = record['recommendation'].lower()
        entry_price = record['entry_price']
        stop_loss = record['stop_loss']
        take_profit = record['take_profit']

        # Simulate based on recommendation, starting from the entry candle
        if recommendation == 'buy':
            return self._simulate_buy_trade_touch(entry_price, stop_loss, take_profit, candles, entry_candle_index)
        elif recommendation == 'sell':
            return self._simulate_sell_trade_touch(entry_price, stop_loss, take_profit, candles, entry_candle_index)
        else:
            return {
                'outcome': 'invalid_recommendation',
                'duration_candles': 0,
                'achieved_rr': 0.0,
                'exit_price': None,
                'exit_candle_index': None,
                'entry_candle_index': entry_candle_index,
                'realized_pnl_price': None,
                'realized_pnl_percent': None
            }

    def _simulate_buy_trade(self, entry_price: float, stop_loss: float, take_profit: float,
                           candles: List[Dict[str, Any]], entry_candle_index: int) -> Dict[str, Any]:
        """Simulate a buy trade (long position) starting from the entry candle."""
        # Track extremes from entry to exit to compute MFE/MAE
        max_high = entry_price
        min_low = entry_price
        R = abs(entry_price - stop_loss) if stop_loss is not None else None

        # Start simulation from the entry candle
        for i in range(entry_candle_index, len(candles)):
            candle = candles[i]
            high = candle['high_price']
            low = candle['low_price']

            # Update extremes
            if high is not None:
                max_high = max(max_high, high)
            if low is not None:
                min_low = min(min_low, low)

            # Check stop loss first (lower price hits SL)
            if low <= stop_loss:
                achieved_rr = (stop_loss - entry_price) / (take_profit - entry_price)
                mfe_price = max(0.0, max_high - entry_price)
                mae_price = max(0.0, entry_price - min_low)
                mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                mfe_r = (mfe_price / R) if R not in (None, 0) else None
                mae_r = (mae_price / R) if R not in (None, 0) else None
                realized_pnl_price = stop_loss - entry_price
                realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                return {
                    'outcome': 'loss',
                    'duration_candles': i - entry_candle_index + 1,
                    'achieved_rr': achieved_rr,
                    'exit_price': stop_loss,
                    'exit_candle_index': i,  # Absolute index in the full candles array
                    'entry_candle_index': entry_candle_index,
                    'mfe_price': mfe_price, 'mae_price': mae_price,
                    'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                    'mfe_r': mfe_r, 'mae_r': mae_r,
                    'realized_pnl_price': realized_pnl_price,
                    'realized_pnl_percent': realized_pnl_percent
                }

            # Check take profit (higher price hits TP)
            if high >= take_profit:
                achieved_rr = (take_profit - entry_price) / (take_profit - entry_price)
                mfe_price = max(0.0, max_high - entry_price)
                mae_price = max(0.0, entry_price - min_low)
                mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                mfe_r = (mfe_price / R) if R not in (None, 0) else None
                mae_r = (mae_price / R) if R not in (None, 0) else None
                realized_pnl_price = take_profit - entry_price
                realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                return {
                    'outcome': 'win',
                    'duration_candles': i - entry_candle_index + 1,
                    'achieved_rr': achieved_rr,
                    'exit_price': take_profit,
                    'exit_candle_index': i,  # Absolute index in the full candles array
                    'entry_candle_index': entry_candle_index,
                    'mfe_price': mfe_price, 'mae_price': mae_price,
                    'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                    'mfe_r': mfe_r, 'mae_r': mae_r,
                    'realized_pnl_price': realized_pnl_price,
                    'realized_pnl_percent': realized_pnl_percent
                }

        # If we reach here, neither SL nor TP was hit within available candles
        mfe_price = max(0.0, max_high - entry_price)
        mae_price = max(0.0, entry_price - min_low)
        mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
        mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
        mfe_r = (mfe_price / R) if R not in (None, 0) else None
        mae_r = (mae_price / R) if R not in (None, 0) else None
        exit_price = candles[-1]['close_price'] if candles else None
        realized_pnl_price = (exit_price - entry_price) if (exit_price is not None and entry_price is not None) else None
        realized_pnl_percent = ((realized_pnl_price / entry_price) * 100.0) if (realized_pnl_price is not None and entry_price) else None
        return {
            'outcome': 'expired',
            'duration_candles': len(candles) - entry_candle_index,
            'achieved_rr': 0.0,
            'exit_price': exit_price,
            'exit_candle_index': len(candles) - 1 if candles else None,
            'entry_candle_index': entry_candle_index,
            'mfe_price': mfe_price, 'mae_price': mae_price,
            'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
            'mfe_r': mfe_r, 'mae_r': mae_r,
            'realized_pnl_price': realized_pnl_price,
            'realized_pnl_percent': realized_pnl_percent
        }

    def _simulate_buy_trade_touch(self, entry_price: float, stop_loss: float, take_profit: float,
                           candles: List[Dict[str, Any]], entry_candle_index: int) -> Dict[str, Any]:
        """Simulate a buy (long) trade that only activates after the entry price is touched."""
        entered = False
        entry_index = None
        max_high = entry_price
        min_low = entry_price
        R = abs(entry_price - stop_loss) if stop_loss is not None else None

        for i in range(entry_candle_index, len(candles)):
            candle = candles[i]
            high = candle['high_price']
            low = candle['low_price']

            if not entered:
                # Wait until the candle range includes the entry price
                if low is not None and high is not None and low <= entry_price <= high:
                    entered = True
                    entry_index = i
                    # Extremes for this candle
                    max_high = max(max_high, high)
                    min_low = min(min_low, low)
                    # Same-candle exit logic after entry: SL first, then TP
                    if low <= stop_loss:
                        achieved_rr = (stop_loss - entry_price) / (take_profit - entry_price)
                        realized_pnl_price = stop_loss - entry_price
                        realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                        mfe_price = max(0.0, max_high - entry_price)
                        mae_price = max(0.0, entry_price - min_low)
                        mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                        mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                        mfe_r = (mfe_price / R) if R not in (None, 0) else None
                        mae_r = (mae_price / R) if R not in (None, 0) else None
                        return {
                            'outcome': 'loss', 'duration_candles': 1, 'achieved_rr': achieved_rr,
                            'exit_price': stop_loss, 'exit_candle_index': i, 'entry_candle_index': entry_index,
                            'mfe_price': mfe_price, 'mae_price': mae_price,
                            'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                            'mfe_r': mfe_r, 'mae_r': mae_r,
                            'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
                        }
                    if high >= take_profit:
                        achieved_rr = (take_profit - entry_price) / (take_profit - entry_price)
                        realized_pnl_price = take_profit - entry_price
                        realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                        mfe_price = max(0.0, max_high - entry_price)
                        mae_price = max(0.0, entry_price - min_low)
                        mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                        mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                        mfe_r = (mfe_price / R) if R not in (None, 0) else None
                        mae_r = (mae_price / R) if R not in (None, 0) else None
                        return {
                            'outcome': 'win', 'duration_candles': 1, 'achieved_rr': achieved_rr,
                            'exit_price': take_profit, 'exit_candle_index': i, 'entry_candle_index': entry_index,
                            'mfe_price': mfe_price, 'mae_price': mae_price,
                            'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                            'mfe_r': mfe_r, 'mae_r': mae_r,
                            'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
                        }
                continue

            # Once entered, track extremes and check exits in subsequent candles
            if high is not None:
                max_high = max(max_high, high)
            if low is not None:
                min_low = min(min_low, low)

            if low <= stop_loss:
                achieved_rr = (stop_loss - entry_price) / (take_profit - entry_price)
                mfe_price = max(0.0, max_high - entry_price)
                mae_price = max(0.0, entry_price - min_low)
                mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                mfe_r = (mfe_price / R) if R not in (None, 0) else None
                mae_r = (mae_price / R) if R not in (None, 0) else None
                realized_pnl_price = stop_loss - entry_price
                realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                idx_for_duration = entry_index if isinstance(entry_index, int) else entry_candle_index if isinstance(entry_candle_index, int) else i
                return {
                    'outcome': 'loss', 'duration_candles': i - idx_for_duration + 1, 'achieved_rr': achieved_rr,
                    'exit_price': stop_loss, 'exit_candle_index': i, 'entry_candle_index': entry_index,
                    'mfe_price': mfe_price, 'mae_price': mae_price,
                    'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                    'mfe_r': mfe_r, 'mae_r': mae_r,
                    'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
                }

            if high >= take_profit:
                achieved_rr = (take_profit - entry_price) / (take_profit - entry_price)
                mfe_price = max(0.0, max_high - entry_price)
                mae_price = max(0.0, entry_price - min_low)
                mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                mfe_r = (mfe_price / R) if R not in (None, 0) else None
                mae_r = (mae_price / R) if R not in (None, 0) else None
                realized_pnl_price = take_profit - entry_price
                realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                idx_for_duration = entry_index if isinstance(entry_index, int) else entry_candle_index if isinstance(entry_candle_index, int) else i
                return {
                    'outcome': 'win', 'duration_candles': i - idx_for_duration + 1, 'achieved_rr': achieved_rr,
                    'exit_price': take_profit, 'exit_candle_index': i, 'entry_candle_index': entry_index,
                    'mfe_price': mfe_price, 'mae_price': mae_price,
                    'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                    'mfe_r': mfe_r, 'mae_r': mae_r,
                    'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
                }

            # continue scanning next candles

        # Never entered
        if not entered:
            return {
                'outcome': 'expired', 'duration_candles': 0, 'achieved_rr': 0.0,
                'exit_price': None, 'exit_candle_index': None, 'entry_candle_index': None,
                'mfe_price': 0.0, 'mae_price': 0.0,
                'mfe_percent': 0.0, 'mae_percent': 0.0,
                'mfe_r': None, 'mae_r': None,
                'realized_pnl_price': None, 'realized_pnl_percent': None
            }

        # Entered but no exit
        mfe_price = max(0.0, max_high - entry_price)
        mae_price = max(0.0, entry_price - min_low)
        mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
        mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
        mfe_r = (mfe_price / R) if R not in (None, 0) else None
        mae_r = (mae_price / R) if R not in (None, 0) else None
        exit_price = candles[-1]['close_price'] if candles else None
        realized_pnl_price = (exit_price - entry_price) if (exit_price is not None and entry_price is not None) else None
        realized_pnl_percent = ((realized_pnl_price / entry_price) * 100.0) if (realized_pnl_price is not None and entry_price) else None
        return {
            'outcome': 'expired', 'duration_candles': len(candles) - (entry_index or entry_candle_index), 'achieved_rr': 0.0,
            'exit_price': exit_price, 'exit_candle_index': len(candles) - 1 if candles else None,
            'entry_candle_index': entry_index,
            'mfe_price': mfe_price, 'mae_price': mae_price,
            'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
            'mfe_r': mfe_r, 'mae_r': mae_r,
            'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
        }

    def _simulate_sell_trade_touch(self, entry_price: float, stop_loss: float, take_profit: float,
                           candles: List[Dict[str, Any]], entry_candle_index: int) -> Dict[str, Any]:
        """Simulate a sell (short) trade that only activates after the entry price is touched."""
        entered = False
        entry_index = None
        max_high = entry_price
        min_low = entry_price
        R = abs(entry_price - stop_loss) if stop_loss is not None else None

        for i in range(entry_candle_index, len(candles)):
            candle = candles[i]
            high = candle['high_price']
            low = candle['low_price']

            if not entered:
                if low is not None and high is not None and low <= entry_price <= high:
                    entered = True
                    entry_index = i
                    max_high = max(max_high, high)
                    min_low = min(min_low, low)
                    # Same-candle exit after entry: SL first (for shorts, SL is above), then TP
                    if high >= stop_loss:
                        achieved_rr = (entry_price - stop_loss) / (entry_price - take_profit)
                        realized_pnl_price = entry_price - stop_loss
                        realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                        mfe_price = max(0.0, entry_price - min_low)
                        mae_price = max(0.0, max_high - entry_price)
                        mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                        mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                        mfe_r = (mfe_price / R) if R not in (None, 0) else None
                        mae_r = (mae_price / R) if R not in (None, 0) else None
                        return {
                            'outcome': 'loss', 'duration_candles': 1, 'achieved_rr': achieved_rr,
                            'exit_price': stop_loss, 'exit_candle_index': i, 'entry_candle_index': entry_index,
                            'mfe_price': mfe_price, 'mae_price': mae_price,
                            'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                            'mfe_r': mfe_r, 'mae_r': mae_r,
                            'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
                        }
                    if low <= take_profit:
                        achieved_rr = (entry_price - take_profit) / (entry_price - take_profit)
                        realized_pnl_price = entry_price - take_profit
                        realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                        mfe_price = max(0.0, entry_price - min_low)
                        mae_price = max(0.0, max_high - entry_price)
                        mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                        mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                        mfe_r = (mfe_price / R) if R not in (None, 0) else None
                        mae_r = (mae_price / R) if R not in (None, 0) else None
                        return {
                            'outcome': 'win', 'duration_candles': 1, 'achieved_rr': achieved_rr,
                            'exit_price': take_profit, 'exit_candle_index': i, 'entry_candle_index': entry_index,
                            'mfe_price': mfe_price, 'mae_price': mae_price,
                            'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                            'mfe_r': mfe_r, 'mae_r': mae_r,
                            'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
                        }
                continue

            # After entered
            if high is not None:
                max_high = max(max_high, high)
            if low is not None:
                min_low = min(min_low, low)

            if high >= stop_loss:
                achieved_rr = (entry_price - stop_loss) / (entry_price - take_profit)
                mfe_price = max(0.0, entry_price - min_low)
                mae_price = max(0.0, max_high - entry_price)
                mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                mfe_r = (mfe_price / R) if R not in (None, 0) else None
                mae_r = (mae_price / R) if R not in (None, 0) else None
                realized_pnl_price = entry_price - stop_loss
                realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                idx_for_duration = entry_index if isinstance(entry_index, int) else entry_candle_index if isinstance(entry_candle_index, int) else i
                return {
                    'outcome': 'loss', 'duration_candles': i - idx_for_duration + 1, 'achieved_rr': achieved_rr,
                    'exit_price': stop_loss, 'exit_candle_index': i, 'entry_candle_index': entry_index,
                    'mfe_price': mfe_price, 'mae_price': mae_price,
                    'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                    'mfe_r': mfe_r, 'mae_r': mae_r,
                    'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
                }

            if low <= take_profit:
                achieved_rr = (entry_price - take_profit) / (entry_price - take_profit)
                mfe_price = max(0.0, entry_price - min_low)
                mae_price = max(0.0, max_high - entry_price)
                mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                mfe_r = (mfe_price / R) if R not in (None, 0) else None
                mae_r = (mae_price / R) if R not in (None, 0) else None
                realized_pnl_price = entry_price - take_profit
                realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                idx_for_duration = entry_index if isinstance(entry_index, int) else entry_candle_index if isinstance(entry_candle_index, int) else i
                return {
                    'outcome': 'win', 'duration_candles': i - idx_for_duration + 1, 'achieved_rr': achieved_rr,
                    'exit_price': take_profit, 'exit_candle_index': i, 'entry_candle_index': entry_index,
                    'mfe_price': mfe_price, 'mae_price': mae_price,
                    'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                    'mfe_r': mfe_r, 'mae_r': mae_r,
                    'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
                }

        if not entered:
            return {
                'outcome': 'expired', 'duration_candles': 0, 'achieved_rr': 0.0,
                'exit_price': None, 'exit_candle_index': None, 'entry_candle_index': None,
                'mfe_price': 0.0, 'mae_price': 0.0,
                'mfe_percent': 0.0, 'mae_percent': 0.0,
                'mfe_r': None, 'mae_r': None,
                'realized_pnl_price': None, 'realized_pnl_percent': None
            }

        # Entered but no exit
        mfe_price = max(0.0, entry_price - min_low)
        mae_price = max(0.0, max_high - entry_price)
        mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
        mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
        mfe_r = (mfe_price / R) if R not in (None, 0) else None
        mae_r = (mae_price / R) if R not in (None, 0) else None
        exit_price = candles[-1]['close_price'] if candles else None
        realized_pnl_price = (entry_price - exit_price) if (exit_price is not None and entry_price is not None) else None
        realized_pnl_percent = ((realized_pnl_price / entry_price) * 100.0) if (realized_pnl_price is not None and entry_price) else None
        return {
            'outcome': 'expired', 'duration_candles': len(candles) - (entry_index or entry_candle_index), 'achieved_rr': 0.0,
            'exit_price': exit_price, 'exit_candle_index': len(candles) - 1 if candles else None,
            'entry_candle_index': entry_index,
            'mfe_price': mfe_price, 'mae_price': mae_price,
            'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
            'mfe_r': mfe_r, 'mae_r': mae_r,
            'realized_pnl_price': realized_pnl_price, 'realized_pnl_percent': realized_pnl_percent
        }



    def _simulate_sell_trade(self, entry_price: float, stop_loss: float, take_profit: float,
                           candles: List[Dict[str, Any]], entry_candle_index: int) -> Dict[str, Any]:
        """Simulate a sell trade (short position) starting from the entry candle."""
        # Track extremes from entry to exit to compute MFE/MAE
        max_high = entry_price
        min_low = entry_price
        R = abs(entry_price - stop_loss) if stop_loss is not None else None

        # Start simulation from the entry candle
        for i in range(entry_candle_index, len(candles)):
            candle = candles[i]
            high = candle['high_price']
            low = candle['low_price']

            # Update extremes
            if high is not None:
                max_high = max(max_high, high)
            if low is not None:
                min_low = min(min_low, low)

            # Check stop loss first (higher price hits SL for shorts)
            if high >= stop_loss:
                achieved_rr = (entry_price - stop_loss) / (entry_price - take_profit)
                mfe_price = max(0.0, entry_price - min_low)
                mae_price = max(0.0, max_high - entry_price)
                mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                mfe_r = (mfe_price / R) if R not in (None, 0) else None
                mae_r = (mae_price / R) if R not in (None, 0) else None
                realized_pnl_price = entry_price - stop_loss
                realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                return {
                    'outcome': 'loss',
                    'duration_candles': i - entry_candle_index + 1,
                    'achieved_rr': achieved_rr,
                    'exit_price': stop_loss,
                    'exit_candle_index': i,  # Absolute index in the full candles array
                    'entry_candle_index': entry_candle_index,
                    'mfe_price': mfe_price, 'mae_price': mae_price,
                    'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                    'mfe_r': mfe_r, 'mae_r': mae_r,
                    'realized_pnl_price': realized_pnl_price,
                    'realized_pnl_percent': realized_pnl_percent
                }

            # Check take profit (lower price hits TP for shorts)
            if low <= take_profit:
                achieved_rr = (entry_price - take_profit) / (entry_price - take_profit)
                mfe_price = max(0.0, entry_price - min_low)
                mae_price = max(0.0, max_high - entry_price)
                mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
                mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
                mfe_r = (mfe_price / R) if R not in (None, 0) else None
                mae_r = (mae_price / R) if R not in (None, 0) else None
                realized_pnl_price = entry_price - take_profit
                realized_pnl_percent = (realized_pnl_price / entry_price * 100.0) if entry_price else None
                return {
                    'outcome': 'win',
                    'duration_candles': i - entry_candle_index + 1,
                    'achieved_rr': achieved_rr,
                    'exit_price': take_profit,
                    'exit_candle_index': i,  # Absolute index in the full candles array
                    'entry_candle_index': entry_candle_index,
                    'mfe_price': mfe_price, 'mae_price': mae_price,
                    'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
                    'mfe_r': mfe_r, 'mae_r': mae_r,
                    'realized_pnl_price': realized_pnl_price,
                    'realized_pnl_percent': realized_pnl_percent
                }

        # If we reach here, neither SL nor TP was hit within available candles
        mfe_price = max(0.0, entry_price - min_low)
        mae_price = max(0.0, max_high - entry_price)
        mfe_percent = (mfe_price / entry_price * 100.0) if entry_price else None
        mae_percent = (mae_price / entry_price * 100.0) if entry_price else None
        mfe_r = (mfe_price / R) if R not in (None, 0) else None
        mae_r = (mae_price / R) if R not in (None, 0) else None
        exit_price = candles[-1]['close_price'] if candles else None
        realized_pnl_price = (entry_price - exit_price) if (exit_price is not None and entry_price is not None) else None
        realized_pnl_percent = ((realized_pnl_price / entry_price) * 100.0) if (realized_pnl_price is not None and entry_price) else None
        return {
            'outcome': 'expired',
            'duration_candles': len(candles) - entry_candle_index,
            'achieved_rr': 0.0,
            'exit_price': exit_price,
            'exit_candle_index': len(candles) - 1 if candles else None,
            'entry_candle_index': entry_candle_index,
            'mfe_price': mfe_price, 'mae_price': mae_price,
            'mfe_percent': mfe_percent, 'mae_percent': mae_percent,
            'mfe_r': mfe_r, 'mae_r': mae_r,
            'realized_pnl_price': realized_pnl_price,
            'realized_pnl_percent': realized_pnl_percent
        }

    def simulate_multiple_trades(self, records: List[Dict[str, Any]], candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Simulate trades for multiple records."""
        results = []

        for record in records:
            try:
                simulation_result = self.simulate_trade(record, candles)

                # Extract prompt version from available data
                prompt_version = self._extract_prompt_version(record)

                # Combine record data with simulation result
                trade_result = {
                    'prompt_version': prompt_version,
                    'symbol': record['symbol'],
                    'timeframe': record['normalized_timeframe'],
                    'timestamp': record['timestamp'],
                    'direction': record['recommendation'],
                    'entry_price': record['entry_price'],
                    'stop_loss': record['stop_loss'],
                    'take_profit': record['take_profit'],
                    'confidence': record.get('confidence', 0.0),
                    **simulation_result
                }

                results.append(trade_result)

            except Exception as e:
                logger.error(f"Error simulating trade for record {record.get('id', 'unknown')}: {e}")
                # Extract prompt version from available data
                prompt_version = self._extract_prompt_version(record)

                # Add error result
                results.append({
                    'prompt_version': prompt_version,
                    'symbol': record['symbol'],
                    'timeframe': record['normalized_timeframe'],
                    'timestamp': record['timestamp'],
                    'direction': record['recommendation'],
                    'entry_price': record['entry_price'],
                    'stop_loss': record['stop_loss'],
                    'take_profit': record['take_profit'],
                    'confidence': record.get('confidence', 0.0),
                    'outcome': 'error',
                    'duration_candles': 0,
                    'achieved_rr': 0.0,
                    'exit_price': None,
                    'exit_candle_index': None
                })

        return results

    def simulate_multiple_trades_with_prompt_hash(self, records: List[Dict[str, Any]], candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Simulate trades for multiple records using prompt hash instead of prompt version."""
        results = []

        for record in records:
            try:
                simulation_result = self.simulate_trade(record, candles)

                # Extract prompt hash from dedicated column
                prompt_hash = self._extract_prompt_hash(record)

                # Combine record data with simulation result
                trade_result = {
                    'prompt_hash': prompt_hash,
                    'symbol': record['symbol'],
                    'timeframe': record['normalized_timeframe'],
                    'timestamp': record['timestamp'],
                    'direction': record['recommendation'],
                    'entry_price': record['entry_price'],
                    'stop_loss': record['stop_loss'],
                    'take_profit': record['take_profit'],
                    'confidence': record.get('confidence', 0.0),
                    **simulation_result
                }

                results.append(trade_result)

            except Exception as e:
                logger.error(f"Error simulating trade for record {record.get('id', 'unknown')}: {e}")
                # Extract prompt hash from available data
                prompt_hash = self._extract_prompt_hash(record)

                # Add error result
                results.append({
                    'prompt_hash': prompt_hash,
                    'symbol': record['symbol'],
                    'timeframe': record['normalized_timeframe'],
                    'timestamp': record['timestamp'],
                    'direction': record['recommendation'],
                    'entry_price': record['entry_price'],
                    'stop_loss': record['stop_loss'],
                    'take_profit': record['take_profit'],
                    'confidence': record.get('confidence', 0.0),
                    'outcome': 'error',
                    'duration_candles': 0,
                    'achieved_rr': 0.0,
                    'exit_price': None,
                    'exit_candle_index': None
                })

        return results
