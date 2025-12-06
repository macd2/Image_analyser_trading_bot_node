import pandas as pd
import logging
from typing import Dict, List, Any, Optional
from trading_bot.core.common_types import PositionInfo  # Import PositionInfo for type hinting
from trading_bot.core.utils import get_server_synchronized_timestamp  # Import directly from utils


# --- ADX Calculation Functions ---
def calculate_true_range(high, low, prev_close):
    """Calculates True Range (TR)."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))

def calculate_directional_movement(high, low, prev_high, prev_low):
    """Calculates Positive and Negative Directional Movement."""
    plus_dm = high - prev_high
    minus_dm = prev_low - low

    if plus_dm > minus_dm and plus_dm > 0:
        return plus_dm, 0
    elif minus_dm > plus_dm and minus_dm > 0:
        return 0, minus_dm
    else:
        return 0, 0

def calculate_adx_components(candles, period=14):
    """
    Calculates ADX, +DI, and -DI components.
    Assumes candles is a list of dicts or DataFrame with 'high', 'low', 'close'.
    """
    if isinstance(candles, list):
        df = pd.DataFrame(candles)
    elif isinstance(candles, pd.DataFrame):
        df = candles.copy()
    else:
        raise ValueError("Candles must be a list of dicts or a pandas DataFrame")

    if len(df) < period * 2: # Need enough data for initial ATR and subsequent ADX
        logging.warning(f"Insufficient data ({len(df)}) for ADX calculation (needs at least {period * 2}).")
        return None, None, None

    df = df.sort_index()
    
    # Ensure numeric types
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    df['close'] = pd.to_numeric(df['close'])

    tr_list = [0.0] * len(df)
    plus_dm_list = [0.0] * len(df)
    minus_dm_list = [0.0] * len(df)

    for i in range(1, len(df)):
        tr_list[i] = calculate_true_range(df['high'].iloc[i], df['low'].iloc[i], df['close'].iloc[i-1])
        plus_dm, minus_dm = calculate_directional_movement(
            df['high'].iloc[i], df['low'].iloc[i],
            df['high'].iloc[i-1], df['low'].iloc[i-1]
        )
        plus_dm_list[i] = plus_dm
        minus_dm_list[i] = minus_dm

    # Calculate Smoothed True Range (ATR-like smoothing)
    atr_initial = sum(tr_list[1:period+1]) / period
    atr_values = [0.0] * len(df)
    atr_values[period] = atr_initial
    for i in range(period + 1, len(df)):
        atr_values[i] = (atr_values[i-1] * (period - 1) + tr_list[i]) / period

    # Calculate Smoothed +DM and -DM
    plus_dm_initial = sum(plus_dm_list[1:period+1]) / period
    minus_dm_initial = sum(minus_dm_list[1:period+1]) / period

    plus_dm_smoothed = [0.0] * len(df)
    minus_dm_smoothed = [0.0] * len(df)
    plus_dm_smoothed[period] = plus_dm_initial
    minus_dm_smoothed[period] = minus_dm_initial

    for i in range(period + 1, len(df)):
        plus_dm_smoothed[i] = (plus_dm_smoothed[i-1] * (period - 1) + plus_dm_list[i]) / period
        minus_dm_smoothed[i] = (minus_dm_smoothed[i-1] * (period - 1) + minus_dm_list[i]) / period

    # Calculate +DI and -DI
    plus_di = [0.0] * len(df)
    minus_di = [0.0] * len(df)

    for i in range(period, len(df)):
        if atr_values[i] != 0:
            plus_di[i] = (plus_dm_smoothed[i] / atr_values[i]) * 100
            minus_di[i] = (minus_dm_smoothed[i] / atr_values[i]) * 100
        else:
            plus_di[i] = 0
            minus_di[i] = 0

    # Calculate DX
    dx = [0.0] * len(df)
    for i in range(period, len(df)):
        di_sum = plus_di[i] + minus_di[i]
        if di_sum != 0:
            dx[i] = (abs(plus_di[i] - minus_di[i]) / di_sum) * 100
        else:
            dx[i] = 0

    # Calculate ADX (smoothed DX)
    adx_values = [0.0] * len(df)
    # ADX calculation needs to start after 2*period, so ensure enough data
    if len(dx) < period * 2:
        return None, None, None # Not enough data for ADX
    
    adx_initial = sum(dx[period:period*2]) / period # Initial ADX is SMA of DX
    adx_values[period*2 -1] = adx_initial # ADX starts after 2*period

    for i in range(period*2, len(df)):
        adx_values[i] = (adx_values[i-1] * (period - 1) + dx[i]) / period

    return adx_values[-1], plus_di[-1], minus_di[-1] # Return latest values

def determine_trend_direction_strength(adx, di_plus, di_minus, adx_threshold=25):
    """
    Determines trend direction and strength based on ADX, +DI, and -DI.
    """
    trend_direction = "sideways"
    if di_plus > di_minus:
        trend_direction = "up"
    elif di_minus > di_plus:
        trend_direction = "down"

    trend_strength = "weak"
    if adx > adx_threshold:
        trend_strength = "strong"
    elif adx > 20: # Often 20-25 is considered developing/moderate
        trend_strength = "developing"

    return trend_direction, trend_strength

def calculate_atr(candles, period=14):
    """
    Calculates the Average True Range (ATR) over a given period.
    Assumes candles is a list of dicts or DataFrame with 'high', 'low', 'close'.

    Args:
        candles (list or pd.DataFrame): OHLC candle data.
        period (int): The period for ATR calculation.

    Returns:
        float or None: The latest ATR value, or None if insufficient data.
    """
    if isinstance(candles, list):
        df = pd.DataFrame(candles)
    elif isinstance(candles, pd.DataFrame):
        df = candles.copy()
    else:
        raise ValueError("Candles must be a list of dicts or a pandas DataFrame")

    if len(df) < period + 1:
        logging.warning(f"Insufficient data ({len(df)}) for ATR calculation (needs {period + 1}).")
        return None

    df = df.sort_index()
    
    # Ensure numeric types
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    df['close'] = pd.to_numeric(df['close'])

    tr_list = [0.0] * len(df)

    for i in range(1, len(df)):
        tr_list[i] = calculate_true_range(df['high'].iloc[i], df['low'].iloc[i], df['close'].iloc[i-1])

    # Simple Moving Average for initial ATR
    atr_list = [0.0] * len(df)
    atr_list[period] = sum(tr_list[1:period+1]) / period

    # Wilder's Smoothing for subsequent ATR values
    for i in range(period + 1, len(df)):
        atr_list[i] = (atr_list[i-1] * (period - 1) + tr_list[i]) / period

    return atr_list[-1] # Return the latest ATR

class ADXStopTightener:
    """
    Implements ADX/ATR based stop loss tightening logic.
    Operates independently of the existing RR tightening.
    """
    def __init__(self, trader, config, position_monitor, logger=None):
        self.trader = trader
        self.config = config
        self.position_monitor = position_monitor # Reference to the PositionMonitor instance
        self.logger = logger or logging.getLogger(__name__)
        
        # Master switch for all position tightening features
        self.enable_position_tightening = getattr(config.trading, 'enable_position_tightening')

        self.enable_adx_tightening = getattr(config.trading, 'enable_adx_tightening')
        self.adx_period = getattr(config.trading, 'adx_period')
        self.atr_period = getattr(config.trading, 'atr_period')
        self.adx_strength_threshold = getattr(config.trading, 'adx_strength_threshold')
        self.base_atr_multiplier = getattr(config.trading, 'base_atr_multiplier')
        self.target_profit_usd = getattr(config.trading, 'adx_target_profit_usd') # New config for ADX target profit

        self.logger.info(f"ADX Stop Tightener initialized - Master tightening: {self.enable_position_tightening}, ADX tightening: {self.enable_adx_tightening}")

    async def _get_candles_for_indicator(self, symbol: str, lookback_needed: int) -> Optional[List[Dict[str, Any]]]:
        """
        Fetches historical klines for indicator calculation using trader session.
        """
        try:
            # Use the trader's session to get kline
            # Use position_monitor's methods for recv_window and timestamp
            response = self.trader.api_manager.get_kline(
                category="linear",
                symbol=symbol,
                interval="60",  # 1 hour candles, consistent with position_monitor's ATR
                limit=lookback_needed,
                recv_window=self.position_monitor._get_recv_window(),
                timestamp=get_server_synchronized_timestamp(self.trader.api_manager)
            )
            
            if not response or response.get("retCode") != 0 or not response.get("result", {}).get("list"):
                self.logger.warning(f"Could not get klines for ADX/ATR calculation for {symbol}")
                return None
            
            klines = response["result"]["list"]
            
            # Convert klines to the expected dict format for pandas DataFrame
            # kline format: [timestamp, open, high, low, close, volume, turnover]
            formatted_candles = []
            for kline in klines:
                formatted_candles.append({
                    'timestamp': int(kline[0]), # Add timestamp for sorting
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5])
                })
            
            # Ensure candles are sorted by timestamp ascending
            formatted_candles.sort(key=lambda x: x['timestamp']) 
            
            return formatted_candles
            
        except Exception as e:
            self.logger.error(f"Error fetching candles for {symbol}: {e}")
            return None

    def _calculate_total_realtime_pnl(self, open_positions: List[PositionInfo]) -> float:
        """
        Calculates total real-time PnL from open positions using unrealized_pnl.
        """
        total_pnl = sum(pos.unrealized_pnl for pos in open_positions)
        return total_pnl

    async def check_and_tighten_adx_stop(self, open_positions: List[PositionInfo]) -> List[Dict[str, Any]]:
        """
        Checks if total PnL has reached target_profit.
        If so, tightens stop-losses for open positions based on volatility (ATR)
        and trend (ADX), aiming to lock in profit while managing risk.

        Args:
            open_positions (list): List of PositionInfo objects representing open positions.

        Returns:
            list: List of update instructions for the trading platform.
        """
        if not self.enable_position_tightening:
            self.logger.debug("ADX Tightener: All position tightening disabled (master switch)")
            return []

        if not self.enable_adx_tightening:
            return []

        update_instructions = []

        # 1. Calculate Total Real-time PnL
        total_pnl = self._calculate_total_realtime_pnl(open_positions)

        # 2. Check if Target Profit is Reached
        if total_pnl >= self.target_profit_usd:
            self.logger.info(f"ADX Tightener: Target profit ${self.target_profit_usd:.2f} reached (Current PnL: ${total_pnl:.2f}). Tightening stops...")

            # 3. Iterate through Open Positions
            for position in open_positions:
                symbol = position.symbol
                side = position.side.lower()
                current_price = position.current_price
                current_stop = position.current_stop_loss
                
                if current_stop is None:
                    self.logger.debug(f"  ADX Tightener: No stop loss set for position {symbol}. Skipping.")
                    continue
                if current_price is None:
                    self.logger.warning(f"  ADX Tightener: Current price missing for {symbol}. Skipping.")
                    continue

                # Fetch enough data for both ADX and ATR calculations
                # ADX needs 2*period, ATR needs period+1. Take max and add buffer.
                lookback_needed = max(self.adx_period * 2, self.atr_period) + 5 
                candles = await self._get_candles_for_indicator(symbol, lookback_needed)
                
                if not candles or len(candles) < max(self.adx_period * 2, self.atr_period) + 1:
                    self.logger.warning(f"  ADX Tightener: Insufficient candle data for {symbol}. Skipping.")
                    continue

                # 5. Calculate Volatility (ATR)
                atr_value = calculate_atr(candles, period=self.atr_period)
                if atr_value is None or atr_value <= 0:
                    self.logger.warning(f"  ADX Tightener: Could not calculate ATR for {symbol}. Skipping.")
                    continue
                self.logger.debug(f"  ADX Tightener: {symbol}: ATR = {atr_value:.2f}")

                # 6. Determine Market Trend (using ADX)
                adx, di_plus, di_minus = calculate_adx_components(candles, period=self.adx_period)
                if adx is None or di_plus is None or di_minus is None:
                    self.logger.warning(f"  ADX Tightener: Could not calculate ADX components for {symbol}. Skipping.")
                    continue
                trend_direction, trend_strength = determine_trend_direction_strength(
                    adx, di_plus, di_minus, adx_threshold=self.adx_strength_threshold
                )
                self.logger.debug(f"  ADX Tightener: {symbol}: ADX = {adx:.2f}, +DI = {di_plus:.2f}, -DI = {di_minus:.2f} -> Trend: {trend_direction} ({trend_strength})")

                # 7. Calculate New Stop Level based on ATR and Trend
                new_stop = None
                volatility_buffer = self.base_atr_multiplier * atr_value

                adjusted_multiplier = self.base_atr_multiplier
                if trend_strength == 'strong':
                    adjusted_multiplier *= 1.2 
                    self.logger.debug(f"    ADX Tightener: Strong trend detected, adjusting ATR multiplier to {adjusted_multiplier:.2f}")
                
                adjusted_volatility_buffer = adjusted_multiplier * atr_value

                # --- Core Stop Tightening Logic ---
                if side == 'buy': # Long
                    potential_new_stop = current_price - adjusted_volatility_buffer
                    
                    if potential_new_stop > current_stop:
                        new_stop = potential_new_stop
                        self.logger.info(f"    ADX Tightener: Long {symbol}: Potential new stop {new_stop:.2f} (tighter than {current_stop:.2f})")

                elif side == 'sell': # Short
                    potential_new_stop = current_price + adjusted_volatility_buffer

                    if potential_new_stop < current_stop:
                        new_stop = potential_new_stop
                        self.logger.info(f"    ADX Tightener: Short {symbol}: Potential new stop {new_stop:.2f} (tighter than {current_stop:.2f})")

                # 8. Apply the New Stop (if calculated and improved)
                if new_stop is not None:
                    # Use the position_monitor's _update_stop_loss method
                    update_result = await self.position_monitor._update_stop_loss(position, new_stop)
                    
                    if update_result.get("success"):
                        # Check if this was actually a tightening or if SL was already at target
                        if update_result.get("warning") and "already at target value" in update_result.get("warning", ""):
                            self.logger.info(f"  >>> ADX Tightener: Stop loss for {symbol} already at target value: {new_stop:.2f} - No adjustment needed")
                            update_instructions.append({
                                'symbol': symbol,
                                'status': 'already_at_target',
                                'old_stop_loss': current_stop,
                                'new_stop_loss': new_stop,
                                'reason': 'ADX_ATR_Tightening',
                                'message': 'No adjustment needed - already at target'
                            })
                        else:
                            # Store detailed reasoning in alteration_details
                            reasoning_data = {
                                'tightening_type': 'ADX_ATR_Tightening',
                                'reason': f'Portfolio PnL target (${self.target_profit_usd:.2f}) reached (${total_pnl:.2f})',
                                'adx_value': round(adx, 2) if adx else None,
                                'di_plus': round(di_plus, 2) if di_plus else None,
                                'di_minus': round(di_minus, 2) if di_minus else None,
                                'trend_direction': trend_direction,
                                'trend_strength': trend_strength,
                                'atr_value': round(atr_value, 2) if atr_value else None,
                                'volatility_buffer': round(adjusted_volatility_buffer, 2),
                                'base_atr_multiplier': self.base_atr_multiplier,
                                'adjusted_multiplier': round(adjusted_multiplier, 2)
                            }
                            
                            update_instructions.append({
                                'symbol': symbol,
                                'status': 'tightened',
                                'old_stop_loss': current_stop,
                                'new_stop_loss': new_stop,
                                'reason': 'ADX_ATR_Tightening',
                                'reasoning': reasoning_data
                            })
                            self.logger.info(f"  >>> ADX Tightener: Tightened stop for {symbol} ({side}) from {current_stop:.2f} to {new_stop:.2f}")
                    else:
                        self.logger.error(f"  ADX Tightener: Failed to update stop for {symbol}: {update_result.get('error')}")
                        update_instructions.append({
                            'symbol': symbol,
                            'status': 'failed',
                            'error': update_result.get('error')
                        })

            if not update_instructions:
                self.logger.info("  ADX Tightener: No stop updates were necessary for any position.")
        else:
            self.logger.debug(f"ADX Tightener: Target profit not reached yet. Current PnL: ${total_pnl:.2f} (Target: ${self.target_profit_usd:.2f})")

        return update_instructions
