"""
Market Regime Detection Strategy
Based on market regime_check.py

Features:
- Higher timeframe bias detection
- Volume-validated candlestick patterns
- Market structure shift confirmation
- Liquidity zone analysis
"""
from typing import Dict, Any, List
import pandas as pd
import pandas_ta
from trading_bot.services.base_strategy import BaseStrategy

# Alias for compatibility with code using 'ta'
ta = pandas_ta

class MarketRegimeStrategy(BaseStrategy):
    """Market Regime Detection Strategy"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Set default configuration
        self.config = {
            "timeframe": config.get("timeframe", "4h"),
            "volume_threshold": config.get("volume_threshold", 1.5),
            "pattern_lookback": config.get("pattern_lookback", 10),
            "min_confidence": config.get("min_confidence", 0.7),
            "use_vwap": config.get("use_vwap", True)
        }

    def get_parameters(self) -> Dict[str, Any]:
        """Return configurable parameters for this strategy."""
        return {
            "timeframe": {
                "type": "string",
                "description": "Higher timeframe for regime detection",
                "default": "4h"
            },
            "volume_threshold": {
                "type": "number",
                "description": "Volume multiplier threshold for pattern validation",
                "default": 1.5
            },
            "pattern_lookback": {
                "type": "integer",
                "description": "Number of periods to look back for pattern detection",
                "default": 10
            },
            "min_confidence": {
                "type": "number",
                "description": "Minimum confidence threshold for signals",
                "default": 0.7
            },
            "use_vwap": {
                "type": "boolean",
                "description": "Whether to use VWAP for intraday bias",
                "default": True
            }
        }

    async def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Analyze candle data for market regime detection.

        Args:
            df: DataFrame with OHLCV data
            symbol: Trading symbol
            timeframe: Current timeframe

        Returns:
            Dictionary with analysis results
        """
        if len(df) < 10:
            return {
                "strategy": "market_regime",
                "symbol": symbol,
                "timeframe": timeframe,
                "recommendation": "HOLD",
                "confidence": 0.0,
                "signals": [],
                "reasoning": "Insufficient data for regime analysis",
                "analysis": {}
            }

        # Calculate indicators
        df = self._calculate_regime_indicators(df)

        # Perform regime analysis
        analysis_result = self._perform_regime_analysis(df, symbol, timeframe)

        return analysis_result

    def _calculate_regime_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate indicators specific to market regime detection."""
        df = df.copy()

        # Basic derived series
        df['body'] = (df['close'] - df['open']).abs()
        df['range'] = df['high'] - df['low']
        df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']

        # Volume indicators
        df['volume_avg_20'] = df['volume'].rolling(20).mean()
        df['volume_confirmed'] = df['volume'] > (self.config['volume_threshold'] * df['volume_avg_20'])

        # Trend indicators
        ema_200 = ta.ema(df['close'], length=200)
        if ema_200 is not None:
            df['ema_200'] = ema_200
            df['ht_trend_up'] = df['close'] > df['ema_200']
            df['ht_trend_dn'] = df['close'] < df['ema_200']
        else:
            df['ema_200'] = None
            df['ht_trend_up'] = False
            df['ht_trend_dn'] = False

        # VWAP for intraday bias
        if self.config['use_vwap']:
            df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
            df['price_above_vwap'] = df['close'] > df['vwap']

        # RSI for divergence detection
        df['rsi'] = ta.rsi(df['close'], length=14)

        # ATR for volatility
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)

        return df

    def _perform_regime_analysis(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        """Perform the core market regime analysis."""
        result = {
            "strategy": "market_regime",
            "symbol": symbol,
            "timeframe": timeframe,
            "recommendation": "HOLD",
            "confidence": 0.5,
            "signals": [],
            "reasoning": "",
            "analysis": {}
        }

        # 1. Higher Timeframe Bias Detection
        ht_analysis = self._detect_htf_bias(df)
        result["analysis"]["htf_bias"] = ht_analysis

        # 2. Candlestick Pattern Detection
        pattern_analysis = self._detect_candlestick_patterns(df)
        result["analysis"]["candlestick_patterns"] = pattern_analysis

        # 3. Liquidity Zone Analysis
        liquidity_analysis = self._analyze_liquidity_zones(df)
        result["analysis"]["liquidity_zones"] = liquidity_analysis

        # 4. Market Structure Shift Confirmation
        structure_analysis = self._confirm_structure_shift(df, ht_analysis)
        result["analysis"]["structure_shift"] = structure_analysis

        # 5. Signal Detection
        signals = self._detect_regime_signals(df, ht_analysis, pattern_analysis, liquidity_analysis, structure_analysis)
        result["signals"] = signals

        # 6. Determine Recommendation
        recommendation, confidence, reasoning = self._determine_regime_recommendation(
            ht_analysis, pattern_analysis, liquidity_analysis, structure_analysis, signals
        )

        result["recommendation"] = recommendation
        result["confidence"] = confidence
        result["reasoning"] = reasoning

        return result

    def _detect_htf_bias(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect higher timeframe bias."""
        current_price = df['close'].iloc[-1]
        ema_200 = df['ema_200'].iloc[-1]

        # Handle case where EMA is None (not enough data)
        if ema_200 is None or pd.isna(ema_200):
            return {
                "bias": "neutral",
                "strength": 0,
                "ema_200": None,
                "price_above_ema_200": False,
                "distance_from_ema_pct": 0
            }

        bias = "bullish" if current_price > ema_200 else "bearish" if current_price < ema_200 else "neutral"
        strength = abs(current_price - ema_200) / ema_200

        return {
            "bias": bias,
            "strength": strength,
            "ema_200": ema_200,
            "price_above_ema_200": current_price > ema_200,
            "distance_from_ema_pct": strength * 100
        }

    def _detect_candlestick_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect volume-validated candlestick patterns."""
        patterns = {
            "bullish_engulfing": [],
            "bearish_engulfing": [],
            "hammer": [],
            "shooting_star": [],
            "inside_bar": []
        }

        for i in range(1, min(len(df), self.config['pattern_lookback'] + 1)):
            idx = -i
            current = df.iloc[idx]
            prev = df.iloc[idx - 1]

            # Bullish Engulfing
            if (prev['close'] < prev['open'] and  # Previous bearish
                current['close'] > current['open'] and  # Current bullish
                current['open'] < prev['close'] and  # Opens below previous close
                current['close'] > prev['open'] and  # Closes above previous open
                current['volume_confirmed']):  # Volume confirmation
                patterns["bullish_engulfing"].append(idx)

            # Bearish Engulfing
            if (prev['close'] > prev['open'] and  # Previous bullish
                current['close'] < current['open'] and  # Current bearish
                current['open'] > prev['close'] and  # Opens above previous close
                current['close'] < prev['open'] and  # Closes below previous open
                current['volume_confirmed']):  # Volume confirmation
                patterns["bearish_engulfing"].append(idx)

            # Hammer
            if (current['body'] <= 0.3 * current['range'] and
                current['lower_shadow'] >= 2.0 * current['body'] and
                current['upper_shadow'] <= 0.2 * current['range'] and
                current['close'] > (current['low'] + 0.6 * current['range']) and
                current['volume_confirmed']):
                patterns["hammer"].append(idx)

            # Shooting Star
            if (current['body'] <= 0.3 * current['range'] and
                current['upper_shadow'] >= 2.0 * current['body'] and
                current['lower_shadow'] <= 0.2 * current['range'] and
                current['close'] < (current['high'] - 0.6 * current['range']) and
                current['volume_confirmed']):
                patterns["shooting_star"].append(idx)

            # Inside Bar
            if (current['high'] < prev['high'] and
                current['low'] > prev['low'] and
                current['volume'] < prev['volume']):
                patterns["inside_bar"].append(idx)

        return patterns

    def _analyze_liquidity_zones(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze liquidity zones (swing highs/lows)."""
        if len(df) < 20:
            return {"zones": [], "current_zone": None}

        # Find swing highs and lows
        swing_highs = []
        swing_lows = []

        for i in range(2, len(df) - 2):
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and
                df['high'].iloc[i] > df['high'].iloc[i-2] and
                df['high'].iloc[i] > df['high'].iloc[i+1] and
                df['high'].iloc[i] > df['high'].iloc[i+2]):
                swing_highs.append({
                    "index": i,
                    "price": df['high'].iloc[i],
                    "type": "resistance"
                })

            if (df['low'].iloc[i] < df['low'].iloc[i-1] and
                df['low'].iloc[i] < df['low'].iloc[i-2] and
                df['low'].iloc[i] < df['low'].iloc[i+1] and
                df['low'].iloc[i] < df['low'].iloc[i+2]):
                swing_lows.append({
                    "index": i,
                    "price": df['low'].iloc[i],
                    "type": "support"
                })

        current_price = df['close'].iloc[-1]

        # Find nearest liquidity zones
        nearest_support = None
        nearest_resistance = None

        supports = [z['price'] for z in swing_lows if z['price'] < current_price]
        resistances = [z['price'] for z in swing_highs if z['price'] > current_price]

        if supports:
            nearest_support = max(supports)
        if resistances:
            nearest_resistance = min(resistances)

        return {
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "current_price": current_price,
            "in_support_zone": nearest_support and abs(current_price - nearest_support) < (nearest_support * 0.01),
            "in_resistance_zone": nearest_resistance and abs(current_price - nearest_resistance) < (nearest_resistance * 0.01)
        }

    def _confirm_structure_shift(self, df: pd.DataFrame, ht_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Confirm market structure shifts."""
        if len(df) < 10:
            return {"shift_confirmed": False, "shift_type": None}

        # Check for break of structure
        recent_highs = df['high'].tail(5)
        recent_lows = df['low'].tail(5)

        # Bullish structure break (higher high + higher low)
        bullish_break = (
            recent_highs.iloc[-1] > recent_highs.iloc[-2] and
            recent_lows.iloc[-1] > recent_lows.iloc[-2] and
            ht_analysis['bias'] != 'bullish'
        )

        # Bearish structure break (lower high + lower low)
        bearish_break = (
            recent_highs.iloc[-1] < recent_highs.iloc[-2] and
            recent_lows.iloc[-1] < recent_lows.iloc[-2] and
            ht_analysis['bias'] != 'bearish'
        )

        return {
            "shift_confirmed": bullish_break or bearish_break,
            "shift_type": "bullish" if bullish_break else "bearish" if bearish_break else None,
            "bullish_break": bullish_break,
            "bearish_break": bearish_break
        }

    def _detect_regime_signals(self, df: pd.DataFrame, ht_analysis: Dict[str, Any],
                              patterns: Dict[str, Any], liquidity: Dict[str, Any],
                              structure: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect trading signals based on market regime."""
        signals = []
        current_price = df['close'].iloc[-1]

        # Bullish signals
        if ht_analysis['bias'] == 'bullish':
            # Bullish engulfing at support with structure confirmation
            if (patterns['bullish_engulfing'] and
                liquidity['in_support_zone'] and
                structure['shift_confirmed'] and structure['shift_type'] == 'bullish'):
                signals.append({
                    "type": "regime_bullish_breakout",
                    "signal": "LONG",
                    "location": "support_zone",
                    "price_level": liquidity['nearest_support'],
                    "strength": "strong",
                    "confidence": 0.85,
                    "pattern": "bullish_engulfing",
                    "structure_shift": "bullish"
                })

            # VWAP bounce in bullish regime
            if (self.config['use_vwap'] and
                df['price_above_vwap'].iloc[-1] and
                df['price_above_vwap'].iloc[-2] == False):
                signals.append({
                    "type": "vwap_bounce",
                    "signal": "LONG",
                    "location": "vwap",
                    "strength": "medium",
                    "confidence": 0.7,
                    "pattern": "vwap_bounce"
                })

        # Bearish signals
        if ht_analysis['bias'] == 'bearish':
            # Bearish engulfing at resistance with structure confirmation
            if (patterns['bearish_engulfing'] and
                liquidity['in_resistance_zone'] and
                structure['shift_confirmed'] and structure['shift_type'] == 'bearish'):
                signals.append({
                    "type": "regime_bearish_breakdown",
                    "signal": "SHORT",
                    "location": "resistance_zone",
                    "price_level": liquidity['nearest_resistance'],
                    "strength": "strong",
                    "confidence": 0.85,
                    "pattern": "bearish_engulfing",
                    "structure_shift": "bearish"
                })

            # VWAP rejection in bearish regime
            if (self.config['use_vwap'] and
                df['price_above_vwap'].iloc[-1] == False and
                df['price_above_vwap'].iloc[-2]):
                signals.append({
                    "type": "vwap_rejection",
                    "signal": "SHORT",
                    "location": "vwap",
                    "strength": "medium",
                    "confidence": 0.7,
                    "pattern": "vwap_rejection"
                })

        return signals

    def _determine_regime_recommendation(self, ht_analysis: Dict[str, Any], patterns: Dict[str, Any],
                                       liquidity: Dict[str, Any], structure: Dict[str, Any],
                                       signals: List[Dict[str, Any]]) -> tuple:
        """Determine final recommendation based on market regime analysis."""
        recommendation = "HOLD"
        confidence = 0.5
        reasoning_parts = []

        # Base reasoning
        reasoning_parts.append(f"HTF Bias: {ht_analysis['bias']} (strength: {ht_analysis['strength']:.3f})")

        if structure['shift_confirmed']:
            reasoning_parts.append(f"Structure Shift Confirmed: {structure['shift_type']}")

        # Pattern reasoning
        total_patterns = sum(len(v) for v in patterns.values())
        reasoning_parts.append(f"Patterns detected: {total_patterns}")

        if patterns['bullish_engulfing']:
            reasoning_parts.append(f"Bullish engulfing patterns: {len(patterns['bullish_engulfing'])}")
        if patterns['bearish_engulfing']:
            reasoning_parts.append(f"Bearish engulfing patterns: {len(patterns['bearish_engulfing'])}")

        # Liquidity zone reasoning
        if liquidity['in_support_zone']:
            reasoning_parts.append(f"Price in support zone: {liquidity['nearest_support']:.2f}")
        if liquidity['in_resistance_zone']:
            reasoning_parts.append(f"Price in resistance zone: {liquidity['nearest_resistance']:.2f}")

        # Signal-based reasoning
        if signals:
            strong_signals = [s for s in signals if s['strength'] == 'strong']
            medium_signals = [s for s in signals if s['strength'] == 'medium']

            if strong_signals:
                # Strong signals override everything
                latest_strong = strong_signals[-1]
                recommendation = latest_strong['signal']
                confidence = min(0.9, latest_strong['confidence'] + 0.05)
                reasoning_parts.append(f"Strong regime signal: {latest_strong['type']} at {latest_strong['location']}")

                if latest_strong['structure_shift']:
                    reasoning_parts.append(f"Confirmed structure shift: {latest_strong['structure_shift']}")
            elif medium_signals:
                # Medium signals follow HTF bias
                latest_medium = medium_signals[-1]
                if (latest_medium['signal'] == 'LONG' and ht_analysis['bias'] == 'bullish') or \
                   (latest_medium['signal'] == 'SHORT' and ht_analysis['bias'] == 'bearish'):
                    recommendation = latest_medium['signal']
                    confidence = latest_medium['confidence']
                    reasoning_parts.append(f"Medium regime signal aligned with HTF bias: {latest_medium['type']}")
                else:
                    reasoning_parts.append(f"Medium regime signal against HTF bias - waiting for confirmation")
        else:
            # No signals - follow HTF bias with lower confidence
            if ht_analysis['bias'] == 'bullish' and ht_analysis['strength'] > 0.02:
                recommendation = "LONG"
                confidence = 0.6
                reasoning_parts.append("Following bullish HTF bias")
            elif ht_analysis['bias'] == 'bearish' and ht_analysis['strength'] > 0.02:
                recommendation = "SHORT"
                confidence = 0.6
                reasoning_parts.append("Following bearish HTF bias")
            else:
                reasoning_parts.append("No clear regime signals, holding position")

        # Apply minimum confidence threshold
        if confidence < self.config['min_confidence']:
            recommendation = "HOLD"
            reasoning_parts.append(f"Confidence {confidence:.2f} below minimum threshold {self.config['min_confidence']}")

        return recommendation, confidence, " | ".join(reasoning_parts)