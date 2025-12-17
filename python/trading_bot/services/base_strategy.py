"""
Base strategy interface for TA-based advisory system.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import pandas as pd
import pandas_ta

# Alias for compatibility with code using 'ta'
ta = pandas_ta


class BaseStrategy(ABC):
    """Base class for all TA strategies."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Strategy configuration dictionary
        """
        self.config = config
        self.name = self.__class__.__name__
        self.version = "1.0.0"
        
    @abstractmethod
    async def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Analyze candle data and return signals.
        
        Args:
            df: DataFrame with OHLCV data (open, high, low, close, volume)
            symbol: Trading symbol
            timeframe: Timeframe of the data
            
        Returns:
            Dictionary with analysis results including signals, confidence, etc.
        """
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """
        Return configurable parameters for this strategy.
        
        Returns:
            Dictionary with parameter definitions
        """
        pass
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate strategy configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            True if configuration is valid
        """
        required_params = self.get_parameters().keys()
        return all(param in config for param in required_params)
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate common technical indicators.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
        """
        # Make a copy to avoid modifying original
        result_df = df.copy()
        
        # Calculate common indicators
        # RSI
        result_df['rsi'] = ta.rsi(result_df['close'], length=14)
        
        # MACD
        macd = ta.macd(result_df['close'])
        if macd is not None:
            result_df['macd'] = macd['MACD_12_26_9']
            result_df['macd_signal'] = macd['MACDs_12_26_9']
            result_df['macd_hist'] = macd['MACDh_12_26_9']
        
        # Bollinger Bands
        bb = ta.bbands(result_df['close'], length=20)
        if bb is not None:
            # Handle different column naming conventions in pandas_ta
            # New format: BBL_20_2.0_2.0, BBM_20_2.0_2.0, BBU_20_2.0_2.0
            # Old format: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
            # Try new format first, then old format
            bb_upper_col = None
            bb_middle_col = None
            bb_lower_col = None

            for col in bb.columns:
                if col.startswith('BBU_'):
                    bb_upper_col = col
                elif col.startswith('BBM_'):
                    bb_middle_col = col
                elif col.startswith('BBL_'):
                    bb_lower_col = col

            if bb_upper_col and bb_middle_col and bb_lower_col:
                result_df['bb_upper'] = bb[bb_upper_col]
                result_df['bb_middle'] = bb[bb_middle_col]
                result_df['bb_lower'] = bb[bb_lower_col]
            else:
                print(f"Warning: Could not find expected Bollinger Bands columns in: {bb.columns.tolist()}")
        
        # ATR for volatility
        result_df['atr'] = ta.atr(result_df['high'], result_df['low'], result_df['close'], length=14)
        
        # Volume indicators
        result_df['volume_sma'] = ta.sma(result_df['volume'], length=20)
        result_df['volume_ratio'] = result_df['volume'] / result_df['volume_sma']
        
        # Moving averages
        sma_20 = ta.sma(result_df['close'], length=20)
        sma_50 = ta.sma(result_df['close'], length=50)
        sma_200 = ta.sma(result_df['close'], length=200)
        ema_12 = ta.ema(result_df['close'], length=12)
        ema_26 = ta.ema(result_df['close'], length=26)

        if sma_20 is not None:
            result_df['sma_20'] = sma_20
        if sma_50 is not None:
            result_df['sma_50'] = sma_50
        if sma_200 is not None:
            result_df['sma_200'] = sma_200
        if ema_12 is not None:
            result_df['ema_12'] = ema_12
        if ema_26 is not None:
            result_df['ema_26'] = ema_26
        
        return result_df
    
    def detect_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Detect market trend from multiple timeframes perspective.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Dictionary with trend information
        """
        if len(df) < 50:
            return {"trend": "neutral", "strength": 0, "direction": "sideways"}

        # Simple trend detection based on moving averages
        last_close = df['close'].iloc[-1]

        # Check if moving averages are available
        sma_20 = df['sma_20'].iloc[-1] if 'sma_20' in df.columns else None
        sma_50 = df['sma_50'].iloc[-1] if 'sma_50' in df.columns else None
        sma_200 = df['sma_200'].iloc[-1] if 'sma_200' in df.columns else None

        # If we don't have enough data for trend analysis, return neutral
        if sma_20 is None or sma_50 is None or sma_200 is None:
            return {"trend": "neutral", "strength": 0, "direction": "sideways"}

        # Check alignment of moving averages
        bullish_alignment = last_close > sma_20 > sma_50 > sma_200
        bearish_alignment = last_close < sma_20 < sma_50 < sma_200
        
        if bullish_alignment:
            trend = "bullish"
            strength = 1.0
        elif bearish_alignment:
            trend = "bearish"
            strength = 1.0
        else:
            # Check short-term trend
            if last_close > sma_20 and sma_20 > sma_50:
                trend = "bullish"
                strength = 0.7
            elif last_close < sma_20 and sma_20 < sma_50:
                trend = "bearish"
                strength = 0.7
            else:
                trend = "neutral"
                strength = 0.3
        
        # Determine direction
        if trend == "bullish":
            direction = "up"
        elif trend == "bearish":
            direction = "down"
        else:
            direction = "sideways"
        
        return {
            "trend": trend,
            "strength": strength,
            "direction": direction,
            "price_above_sma_20": last_close > sma_20,
            "price_above_sma_50": last_close > sma_50,
            "price_above_sma_200": last_close > sma_200,
            "sma_20_above_sma_50": sma_20 > sma_50,
            "sma_50_above_sma_200": sma_50 > sma_200,
        }
    
    def identify_support_resistance(self, df: pd.DataFrame, lookback_periods: int = 100) -> Dict[str, Any]:
        """
        Identify key support and resistance levels.
        
        Args:
            df: DataFrame with OHLCV data
            lookback_periods: Number of periods to look back
            
        Returns:
            Dictionary with support and resistance levels
        """
        if len(df) < lookback_periods:
            lookback_periods = len(df)
        
        recent_data = df.tail(lookback_periods)
        
        # Find swing highs and lows
        highs = recent_data['high']
        lows = recent_data['low']
        
        # Simple pivot point detection
        resistance_levels = []
        support_levels = []
        
        # Look for local maxima and minima
        for i in range(2, len(recent_data) - 2):
            if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and \
               highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
                resistance_levels.append(highs.iloc[i])
            
            if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and \
               lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
                support_levels.append(lows.iloc[i])
        
        # Get current price
        current_price = df['close'].iloc[-1]
        
        # Find nearest support and resistance
        nearest_support = max([s for s in support_levels if s < current_price], default=None)
        nearest_resistance = min([r for r in resistance_levels if r > current_price], default=None)
        
        return {
            "support_levels": sorted(support_levels),
            "resistance_levels": sorted(resistance_levels),
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "distance_to_support_pct": ((current_price - nearest_support) / current_price * 100) if nearest_support else None,
            "distance_to_resistance_pct": ((nearest_resistance - current_price) / current_price * 100) if nearest_resistance else None,
        }