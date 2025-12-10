"""
Alex Top-Down Analysis Strategy
Based on trade_entry_strategies_E3lYZsy8nYE_HH_LL_alex_strat.md

Features:
- Top-down analysis across multiple timeframes
- Area of Interest detection (support/resistance)
- Entry signal confirmation
- Market structure analysis
"""
from typing import Dict, Any, List
import pandas as pd
import pandas_ta as ta
from trading_bot.services.base_strategy import BaseStrategy

class AlexStrategy(BaseStrategy):
    """Alex's Top-Down Analysis Strategy"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Set default configuration
        self.config = {
            "timeframes": config.get("timeframes", ["1h", "4h", "1d"]),
            "lookback_periods": config.get("lookback_periods", 20),
            "indicators": config.get("indicators", ["RSI", "MACD", "EMA"]),
            "min_confidence": config.get("min_confidence", 0.7),
            "use_volume": config.get("use_volume", True)
        }

    def get_parameters(self) -> Dict[str, Any]:
        """Return configurable parameters for this strategy."""
        return {
            "timeframes": {
                "type": "array",
                "description": "Timeframes to analyze (top-down)",
                "default": ["1h", "4h", "1d"]
            },
            "lookback_periods": {
                "type": "integer",
                "description": "Number of periods to look back for analysis",
                "default": 20
            },
            "indicators": {
                "type": "array",
                "description": "Technical indicators to use",
                "default": ["RSI", "MACD", "EMA"]
            },
            "min_confidence": {
                "type": "number",
                "description": "Minimum confidence threshold for signals",
                "default": 0.7
            },
            "use_volume": {
                "type": "boolean",
                "description": "Whether to use volume confirmation",
                "default": True
            }
        }

    async def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Analyze candle data using Alex's top-down approach.

        Args:
            df: DataFrame with OHLCV data
            symbol: Trading symbol
            timeframe: Current timeframe

        Returns:
            Dictionary with analysis results
        """
        if len(df) < 10:
            return {
                "strategy": "alex_top_down",
                "symbol": symbol,
                "timeframe": timeframe,
                "recommendation": "HOLD",
                "confidence": 0.0,
                "signals": [],
                "reasoning": "Insufficient data for analysis",
                "analysis": {}
            }

        # Calculate indicators
        df = self.calculate_indicators(df)

        # Perform top-down analysis
        analysis_result = self._perform_top_down_analysis(df, symbol, timeframe)

        return analysis_result

    def _perform_top_down_analysis(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        """Perform the core top-down analysis."""
        result = {
            "strategy": "alex_top_down",
            "symbol": symbol,
            "timeframe": timeframe,
            "recommendation": "HOLD",
            "confidence": 0.5,
            "signals": [],
            "reasoning": "",
            "analysis": {}
        }

        # 1. Trend Analysis
        trend_analysis = self.detect_trend(df)
        result["analysis"]["trend"] = trend_analysis

        # 2. Support/Resistance Analysis
        sr_analysis = self.identify_support_resistance(df, self.config["lookback_periods"])
        result["analysis"]["support_resistance"] = sr_analysis

        # 3. Market Structure Analysis
        structure_analysis = self._analyze_market_structure(df)
        result["analysis"]["market_structure"] = structure_analysis

        # 4. Entry Signal Detection
        entry_signals = self._detect_entry_signals(df, trend_analysis, sr_analysis)
        result["signals"] = entry_signals

        # 5. Determine Recommendation
        recommendation, confidence, reasoning = self._determine_recommendation(
            trend_analysis, sr_analysis, structure_analysis, entry_signals
        )

        result["recommendation"] = recommendation
        result["confidence"] = confidence
        result["reasoning"] = reasoning

        return result

    def _analyze_market_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze market structure (higher highs, lower lows, etc.)"""
        if len(df) < 5:
            return {"structure": "neutral", "shift_detected": False}

        # Find recent swing highs and lows
        highs = df['high'].rolling(window=5, center=True).max()
        lows = df['low'].rolling(window=5, center=True).min()

        # Detect market structure
        recent_highs = highs.tail(10)
        recent_lows = lows.tail(10)

        # Check for higher highs and higher lows (bullish)
        bullish_structure = (
            recent_highs.iloc[-1] > recent_highs.iloc[-2] and
            recent_lows.iloc[-1] > recent_lows.iloc[-2]
        )

        # Check for lower highs and lower lows (bearish)
        bearish_structure = (
            recent_highs.iloc[-1] < recent_highs.iloc[-2] and
            recent_lows.iloc[-1] < recent_lows.iloc[-2]
        )

        # Check for structure shift
        structure_shift = False
        if len(df) > 20:
            # Compare recent structure with older structure
            older_highs = highs.iloc[-20:-10]
            older_lows = lows.iloc[-20:-10]

            old_bullish = older_highs.iloc[-1] > older_highs.iloc[-2] and older_lows.iloc[-1] > older_lows.iloc[-2]
            old_bearish = older_highs.iloc[-1] < older_highs.iloc[-2] and older_lows.iloc[-1] < older_lows.iloc[-2]

            structure_shift = (old_bullish and bearish_structure) or (old_bearish and bullish_structure)

        return {
            "structure": "bullish" if bullish_structure else "bearish" if bearish_structure else "neutral",
            "shift_detected": structure_shift,
            "shift_type": "bullish" if (old_bearish and bullish_structure) else "bearish" if (old_bullish and bearish_structure) else None,
            "recent_highs": recent_highs.tolist(),
            "recent_lows": recent_lows.tolist()
        }

    def _detect_entry_signals(self, df: pd.DataFrame, trend: Dict[str, Any], sr: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect entry signals based on Alex's strategy."""
        signals = []
        current_price = df['close'].iloc[-1]

        # Check if price is near support/resistance
        near_support = sr['nearest_support'] and abs(current_price - sr['nearest_support']) < (sr['nearest_support'] * 0.01)
        near_resistance = sr['nearest_resistance'] and abs(current_price - sr['nearest_resistance']) < (sr['nearest_resistance'] * 0.01)

        # Bullish signals
        if trend['trend'] == 'bullish' and near_support:
            # Check for bullish reversal patterns
            if self._is_bullish_reversal(df):
                signals.append({
                    "type": "bullish_reversal",
                    "signal": "LONG",
                    "location": "support",
                    "price_level": sr['nearest_support'],
                    "strength": "strong",
                    "confidence": 0.8
                })

            # Check for continuation patterns
            if self._is_bullish_continuation(df):
                signals.append({
                    "type": "bullish_continuation",
                    "signal": "LONG",
                    "location": "trend",
                    "strength": "medium",
                    "confidence": 0.7
                })

        # Bearish signals
        if trend['trend'] == 'bearish' and near_resistance:
            # Check for bearish reversal patterns
            if self._is_bearish_reversal(df):
                signals.append({
                    "type": "bearish_reversal",
                    "signal": "SHORT",
                    "location": "resistance",
                    "price_level": sr['nearest_resistance'],
                    "strength": "strong",
                    "confidence": 0.8
                })

            # Check for continuation patterns
            if self._is_bearish_continuation(df):
                signals.append({
                    "type": "bearish_continuation",
                    "signal": "SHORT",
                    "location": "trend",
                    "strength": "medium",
                    "confidence": 0.7
                })

        return signals

    def _is_bullish_reversal(self, df: pd.DataFrame) -> bool:
        """Check for bullish reversal patterns."""
        if len(df) < 3:
            return False

        # Simple bullish engulfing pattern
        prev_candle = df.iloc[-2]
        current_candle = df.iloc[-1]

        bullish_engulfing = (
            prev_candle['close'] < prev_candle['open'] and  # Previous bearish
            current_candle['close'] > current_candle['open'] and  # Current bullish
            current_candle['open'] < prev_candle['close'] and  # Opens below previous close
            current_candle['close'] > prev_candle['open'] and  # Closes above previous open
            current_candle['volume'] > prev_candle['volume'] * 1.2  # Volume confirmation
        )

        # Hammer pattern
        hammer = (
            (current_candle['high'] - current_candle['low']) > 3 * abs(current_candle['close'] - current_candle['open']) and
            (current_candle['close'] - current_candle['low']) > 2 * (current_candle['high'] - current_candle['close']) and
            current_candle['close'] > current_candle['open']  # Bullish hammer
        )

        return bullish_engulfing or hammer

    def _is_bearish_reversal(self, df: pd.DataFrame) -> bool:
        """Check for bearish reversal patterns."""
        if len(df) < 3:
            return False

        # Simple bearish engulfing pattern
        prev_candle = df.iloc[-2]
        current_candle = df.iloc[-1]

        bearish_engulfing = (
            prev_candle['close'] > prev_candle['open'] and  # Previous bullish
            current_candle['close'] < current_candle['open'] and  # Current bearish
            current_candle['open'] > prev_candle['close'] and  # Opens above previous close
            current_candle['close'] < prev_candle['open'] and  # Closes below previous open
            current_candle['volume'] > prev_candle['volume'] * 1.2  # Volume confirmation
        )

        # Shooting star pattern
        shooting_star = (
            (current_candle['high'] - current_candle['low']) > 3 * abs(current_candle['close'] - current_candle['open']) and
            (current_candle['high'] - current_candle['close']) > 2 * (current_candle['close'] - current_candle['low']) and
            current_candle['close'] < current_candle['open']  # Bearish shooting star
        )

        return bearish_engulfing or shooting_star

    def _is_bullish_continuation(self, df: pd.DataFrame) -> bool:
        """Check for bullish continuation patterns."""
        if len(df) < 5:
            return False

        # Check if we're in an uptrend
        sma_20 = df['sma_20'].iloc[-1]
        sma_50 = df['sma_50'].iloc[-1]
        current_price = df['close'].iloc[-1]

        if current_price < sma_20 or sma_20 < sma_50:
            return False

        # Check for pullback to moving average
        pullback_to_sma = abs(current_price - sma_20) < (sma_20 * 0.01)

        # Check for bullish candle after pullback
        if pullback_to_sma:
            current_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]

            continuation = (
                current_candle['close'] > current_candle['open'] and
                current_candle['close'] > prev_candle['high'] and
                current_candle['volume'] > df['volume'].rolling(5).mean().iloc[-1]
            )

            return continuation

        return False

    def _is_bearish_continuation(self, df: pd.DataFrame) -> bool:
        """Check for bearish continuation patterns."""
        if len(df) < 5:
            return False

        # Check if we're in a downtrend
        sma_20 = df['sma_20'].iloc[-1]
        sma_50 = df['sma_50'].iloc[-1]
        current_price = df['close'].iloc[-1]

        if current_price > sma_20 or sma_20 > sma_50:
            return False

        # Check for pullback to moving average
        pullback_to_sma = abs(current_price - sma_20) < (sma_20 * 0.01)

        # Check for bearish candle after pullback
        if pullback_to_sma:
            current_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]

            continuation = (
                current_candle['close'] < current_candle['open'] and
                current_candle['close'] < prev_candle['low'] and
                current_candle['volume'] > df['volume'].rolling(5).mean().iloc[-1]
            )

            return continuation

        return False

    def _determine_recommendation(self, trend: Dict[str, Any], sr: Dict[str, Any],
                                structure: Dict[str, Any], signals: List[Dict[str, Any]]) -> tuple:
        """Determine final recommendation based on all analysis."""
        recommendation = "HOLD"
        confidence = 0.5
        reasoning_parts = []

        # Base reasoning
        reasoning_parts.append(f"Trend: {trend['trend']} (strength: {trend['strength']:.1f})")
        reasoning_parts.append(f"Market structure: {structure['structure']}")

        if structure['shift_detected']:
            reasoning_parts.append(f"Structure shift detected: {structure['shift_type']}")

        # Support/Resistance reasoning
        current_price = trend.get('last_close', 0)
        if sr['nearest_support']:
            dist_to_support = ((current_price - sr['nearest_support']) / current_price * 100)
            reasoning_parts.append(f"Nearest support: {sr['nearest_support']:.2f} ({dist_to_support:.1f}% away)")

        if sr['nearest_resistance']:
            dist_to_resistance = ((sr['nearest_resistance'] - current_price) / current_price * 100)
            reasoning_parts.append(f"Nearest resistance: {sr['nearest_resistance']:.2f} ({dist_to_resistance:.1f}% away)")

        # Signal-based reasoning
        if signals:
            strong_signals = [s for s in signals if s['strength'] == 'strong']
            medium_signals = [s for s in signals if s['strength'] == 'medium']

            if strong_signals:
                # Strong signals override trend
                latest_strong = strong_signals[-1]
                recommendation = latest_strong['signal']
                confidence = min(0.9, latest_strong['confidence'] + 0.1)
                reasoning_parts.append(f"Strong {latest_strong['type']} signal at {latest_strong['location']}")
            elif medium_signals:
                # Medium signals follow trend
                latest_medium = medium_signals[-1]
                if (latest_medium['signal'] == 'LONG' and trend['trend'] == 'bullish') or \
                   (latest_medium['signal'] == 'SHORT' and trend['trend'] == 'bearish'):
                    recommendation = latest_medium['signal']
                    confidence = latest_medium['confidence']
                    reasoning_parts.append(f"Medium {latest_medium['type']} signal aligned with trend")
                else:
                    reasoning_parts.append(f"Medium {latest_medium['type']} signal against trend - waiting for confirmation")
        else:
            # No signals - follow trend with lower confidence
            if trend['trend'] == 'bullish' and trend['strength'] > 0.7:
                recommendation = "LONG"
                confidence = 0.6
                reasoning_parts.append("Following strong bullish trend")
            elif trend['trend'] == 'bearish' and trend['strength'] > 0.7:
                recommendation = "SHORT"
                confidence = 0.6
                reasoning_parts.append("Following strong bearish trend")
            else:
                reasoning_parts.append("No clear signals, holding position")

        # Apply minimum confidence threshold
        if confidence < self.config['min_confidence']:
            recommendation = "HOLD"
            reasoning_parts.append(f"Confidence {confidence:.1f} below minimum threshold {self.config['min_confidence']}")

        return recommendation, confidence, " | ".join(reasoning_parts)