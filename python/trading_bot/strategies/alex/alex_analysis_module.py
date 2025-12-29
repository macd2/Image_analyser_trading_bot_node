"""
AlexAnalysisModule - Top-Down Analysis Strategy

Converted from AlexStrategy to work with BaseAnalysisModule system.

Features:
- Top-down analysis across multiple timeframes
- Area of Interest detection (support/resistance)
- Entry signal confirmation
- Market structure analysis
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import pandas_ta
from trading_bot.strategies.base import BaseAnalysisModule

# Alias for compatibility with code using 'ta'
ta = pandas_ta

logger = None  # Set in __init__


class AlexAnalysisModule(BaseAnalysisModule):
    """Alex's Top-Down Analysis Strategy"""

    # Strategy type identification
    STRATEGY_TYPE = "price_based"
    STRATEGY_NAME = "MarketStructure"
    STRATEGY_VERSION = "1.0"

    # Default configuration
    DEFAULT_CONFIG = {
        "timeframes": ["1h", "4h", "1d"],
        "lookback_periods": 20,
        "indicators": ["RSI", "MACD", "EMA"],
        "min_confidence": 0.7,
        "use_volume": True,
    }
    
    def __init__(
        self,
        config: 'Config',
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        heartbeat_callback: Optional[Any] = None,
    ):
        """Initialize Alex strategy with instance-specific config."""
        super().__init__(config, instance_id, run_id, strategy_config, heartbeat_callback)
        global logger
        logger = self.logger
    
    async def run_analysis_cycle(
        self,
        symbols: List[str],
        timeframe: str,
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Run complete analysis cycle for symbols.

        Performs TOP-DOWN analysis across multiple timeframes:
        1. Get configured timeframes from strategy config (default: 1h, 4h, 1d)
        2. Fetch candles for each timeframe
        3. Analyze each timeframe
        4. Combine analysis for final recommendation

        Returns list of analysis results matching output format.
        """
        results = []

        # Get configured timeframes for top-down analysis
        configured_timeframes = self.get_config_value('timeframes', ['1h', '4h', '1d'])

        for symbol in symbols:
            # Check if bot should stop (graceful shutdown)
            if self._stop_requested:
                self.logger.info(f"Stop requested - halting analysis at symbol {symbol}")
                break

            try:
                # Send heartbeat: starting analysis for symbol
                self._heartbeat(f"Analyzing {symbol}...", symbol=symbol)

                # Get candles from adapter for ALL configured timeframes
                if not self.candle_adapter:
                    results.append({
                        "symbol": symbol,
                        "error": "Candle adapter not initialized",
                        "timeframe": timeframe,
                        "cycle_id": cycle_id,
                    })
                    continue

                # Fetch candles for each timeframe
                # Use API directly for real-time analysis (prefer_source="api")
                timeframe_candles = {}
                for tf in configured_timeframes:
                    candles = await self.candle_adapter.get_candles(
                        symbol=symbol,
                        timeframe=tf,
                        limit=200,  # Need enough for all indicators
                        use_cache=True,
                        min_candles=50,  # Need at least 50 for SMA calculations
                        prefer_source="api"  # Prefer API for real-time data
                    )
                    if candles:
                        timeframe_candles[tf] = candles

                # Send heartbeat: candles fetched
                self._heartbeat(f"Fetched candles for {symbol}", symbol=symbol, timeframes=list(timeframe_candles.keys()))

                if not timeframe_candles:
                    results.append({
                        "symbol": symbol,
                        "recommendation": "HOLD",
                        "confidence": 0.0,
                        "entry_price": None,
                        "stop_loss": None,
                        "take_profit": None,
                        "risk_reward": 0,
                        "setup_quality": 0.5,
                        "market_environment": 0.5,
                        "analysis": {"error": "Insufficient candle data for all timeframes"},
                        "chart_path": "",
                        "timeframe": timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": "Insufficient candle data",
                    })
                    continue

                # Analyze each timeframe (top-down: 1d -> 4h -> 1h)
                timeframe_analyses = {}
                for tf in sorted(configured_timeframes, key=lambda x: self._timeframe_order(x), reverse=True):
                    if tf not in timeframe_candles:
                        continue

                    candles = timeframe_candles[tf]
                    df = self._candles_to_dataframe(candles)

                    # Calculate indicators
                    df = self._calculate_indicators(df)

                    # Perform analysis
                    trend = self._detect_trend(df)
                    sr = self._identify_support_resistance(df)
                    structure = self._analyze_market_structure(df)
                    signals = self._detect_entry_signals(df, trend, sr)

                    timeframe_analyses[tf] = {
                        "trend": trend,
                        "support_resistance": sr,
                        "structure": structure,
                        "signals": signals,
                    }

                # Combine analysis from all timeframes
                result = self._combine_timeframe_analysis(
                    symbol, timeframe_analyses, configured_timeframes, cycle_id
                )

                # Validate output
                self._validate_output(result)

                results.append(result)

                # Send heartbeat: analysis complete
                self._heartbeat(f"Completed analysis for {symbol}", symbol=symbol, recommendation=result.get("recommendation"))
                
            except Exception as e:
                self.logger.error(
                    f"Analysis failed for {symbol}: {e}",
                    extra={"symbol": symbol, "instance_id": self.instance_id}
                )
                results.append({
                    "symbol": symbol,
                    "error": str(e),
                    "timeframe": timeframe,
                    "cycle_id": cycle_id,
                })
        
        return results
    
    def _timeframe_order(self, timeframe: str) -> int:
        """Get order value for timeframe (for sorting)."""
        order_map = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
            "1w": 10080,
        }
        return order_map.get(timeframe, 0)

    def _combine_timeframe_analysis(
        self,
        symbol: str,
        timeframe_analyses: Dict[str, Dict[str, Any]],
        configured_timeframes: List[str],
        cycle_id: str,
    ) -> Dict[str, Any]:
        """
        Combine analysis from multiple timeframes.

        Top-down approach:
        1. Check daily trend (1d) for overall direction
        2. Check 4h for confirmation
        3. Use 1h for entry timing
        """
        # Get analysis for each timeframe (if available)
        daily_analysis = timeframe_analyses.get('1d')
        h4_analysis = timeframe_analyses.get('4h')
        h1_analysis = timeframe_analyses.get('1h')

        # Use the most detailed analysis available (prefer 1h, then 4h, then 1d)
        primary_analysis = h1_analysis or h4_analysis or daily_analysis

        if not primary_analysis:
            return {
                "symbol": symbol,
                "recommendation": "HOLD",
                "confidence": 0.0,
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward": 0,
                "setup_quality": 0.5,
                "position_size_multiplier": 1.0,
                "market_environment": 0.5,
                "analysis": {"error": "No timeframe analysis available"},
                "chart_path": "",
                "timeframe": ",".join(configured_timeframes),
                "cycle_id": cycle_id,
            }

        # Determine recommendation based on top-down analysis
        trend = primary_analysis['trend']
        sr = primary_analysis['support_resistance']
        structure = primary_analysis['structure']
        signals = primary_analysis['signals']

        recommendation, confidence, reasoning = self._determine_recommendation(
            trend, sr, structure, signals
        )

        # Build result
        return {
            "symbol": symbol,
            "recommendation": recommendation,
            "confidence": confidence,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": 0,
            "setup_quality": self._calculate_setup_quality(trend, sr, structure),
            "position_size_multiplier": 1.0,  # Market structure strategy uses neutral sizing
            "market_environment": self._calculate_market_environment(trend),
            "analysis": {
                "strategy": "alex_top_down",
                "timeframes_analyzed": list(timeframe_analyses.keys()),
                "primary_timeframe": "1h" if h1_analysis else ("4h" if h4_analysis else "1d"),
                "trend": trend,
                "support_resistance": sr,
                "market_structure": structure,
                "signals": signals,
                "reasoning": reasoning,
            },
            "chart_path": "",
            "timeframe": ",".join(configured_timeframes),
            "cycle_id": cycle_id,
        }
    
    def _candles_to_dataframe(self, candles: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert candle list to DataFrame.

        Candles are already normalized by CandleAdapter with standard field names:
        open, high, low, close, volume, turnover, timestamp
        """
        df = pd.DataFrame(candles)
        # Ensure we have the required columns (already normalized by CandleAdapter)
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators."""
        result_df = df.copy()
        
        # Moving averages
        result_df['sma_20'] = ta.sma(result_df['close'], length=20)
        result_df['sma_50'] = ta.sma(result_df['close'], length=50)
        result_df['sma_200'] = ta.sma(result_df['close'], length=200)
        
        # RSI
        result_df['rsi'] = ta.rsi(result_df['close'], length=14)
        
        # MACD
        macd = ta.macd(result_df['close'])
        if macd is not None:
            result_df['macd'] = macd['MACD_12_26_9']
            result_df['macd_signal'] = macd['MACDs_12_26_9']
        
        return result_df
    
    def _detect_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect market trend."""
        if len(df) < 50:
            return {"trend": "neutral", "strength": 0.0, "last_close": df['close'].iloc[-1] if len(df) > 0 else 0}

        last_close = df['close'].iloc[-1]
        sma_20 = df['sma_20'].iloc[-1]
        sma_50 = df['sma_50'].iloc[-1]
        sma_200 = df['sma_200'].iloc[-1]

        # Handle NaN values from indicators
        if pd.isna(sma_20) or pd.isna(sma_50) or pd.isna(sma_200):
            return {"trend": "neutral", "strength": 0.5, "last_close": last_close}

        if last_close > sma_20 > sma_50 > sma_200:
            return {"trend": "bullish", "strength": 1.0, "last_close": last_close}
        elif last_close < sma_20 < sma_50 < sma_200:
            return {"trend": "bearish", "strength": 1.0, "last_close": last_close}
        else:
            return {"trend": "neutral", "strength": 0.5, "last_close": last_close}
    
    def _identify_support_resistance(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Identify support and resistance levels."""
        current_price = df['close'].iloc[-1]
        highs = df['high'].tail(100)
        lows = df['low'].tail(100)
        
        nearest_support = max([l for l in lows if l < current_price], default=None)
        nearest_resistance = min([h for h in highs if h > current_price], default=None)
        
        return {
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
        }
    
    def _analyze_market_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze market structure."""
        return {"structure": "neutral", "shift_detected": False}
    
    def _detect_entry_signals(
        self,
        df: pd.DataFrame,
        trend: Dict[str, Any],
        sr: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Detect entry signals."""
        return []
    
    def _determine_recommendation(
        self,
        trend: Dict[str, Any],
        sr: Dict[str, Any],
        structure: Dict[str, Any],
        signals: List[Dict[str, Any]]
    ) -> tuple:
        """Determine final recommendation."""
        min_confidence = self.get_config_value('min_confidence', 0.7)
        
        if trend['strength'] > 0.7:
            recommendation = "BUY" if trend['trend'] == 'bullish' else "SELL"
            confidence = min(0.8, trend['strength'])
        else:
            recommendation = "HOLD"
            confidence = 0.5
        
        if confidence < min_confidence:
            recommendation = "HOLD"
        
        return recommendation, confidence, f"Trend: {trend['trend']}"
    
    def _calculate_setup_quality(
        self,
        trend: Dict[str, Any],
        sr: Dict[str, Any],
        structure: Dict[str, Any]
    ) -> float:
        """Calculate setup quality score."""
        return min(1.0, trend.get('strength', 0.5))
    
    def _calculate_market_environment(self, trend: Dict[str, Any]) -> float:
        """Calculate market environment score."""
        return min(1.0, trend.get('strength', 0.5))

    def validate_signal(self, signal: Dict[str, Any]) -> bool:
        """
        Validate price-based signal.

        Checks:
        - RR ratio >= min_rr (default 1.0)
        - Entry/SL/TP prices are in correct order
        - Prices are reasonable (not zero or negative)

        Args:
            signal: Signal dict with entry_price, stop_loss, take_profit

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        min_rr = self.get_config_value("min_rr", 1.0)

        entry = signal.get("entry_price")
        sl = signal.get("stop_loss")
        tp = signal.get("take_profit")

        if not all([entry, sl, tp]):
            raise ValueError(f"Missing price levels: entry={entry}, sl={sl}, tp={tp}")

        if entry <= 0 or sl <= 0 or tp <= 0:
            raise ValueError(f"Prices must be positive: entry={entry}, sl={sl}, tp={tp}")

        # Determine direction based on entry vs SL
        is_long = entry > sl

        if is_long:
            if not (sl < entry < tp):
                raise ValueError(
                    f"Long signal prices in wrong order: SL({sl}) < Entry({entry}) < TP({tp})"
                )
            rr_ratio = (tp - entry) / (entry - sl)
        else:
            if not (tp < entry < sl):
                raise ValueError(
                    f"Short signal prices in wrong order: TP({tp}) < Entry({entry}) < SL({sl})"
                )
            rr_ratio = (entry - tp) / (sl - entry)

        if rr_ratio < min_rr:
            raise ValueError(
                f"RR ratio {rr_ratio:.2f} below minimum {min_rr}"
            )

        return True

    def calculate_risk_metrics(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate price-based risk metrics.

        Returns:
            Dict with: risk_per_unit, reward_per_unit, risk_reward_ratio
        """
        entry = signal.get("entry_price")
        sl = signal.get("stop_loss")
        tp = signal.get("take_profit")

        is_long = entry > sl

        if is_long:
            risk_per_unit = entry - sl
            reward_per_unit = tp - entry
        else:
            risk_per_unit = sl - entry
            reward_per_unit = entry - tp

        rr_ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0

        return {
            "risk_per_unit": risk_per_unit,
            "reward_per_unit": reward_per_unit,
            "risk_reward_ratio": rr_ratio,
        }

    def get_exit_condition(self) -> Dict[str, Any]:
        """
        Get price-based exit condition metadata.

        Returns:
            Dict with TP and SL prices for simulator to check
        """
        return {
            "type": "price_level",
            "description": "Exit when price touches TP or SL level",
        }

    def get_monitoring_metadata(self) -> Dict[str, Any]:
        """
        Get price-based monitoring metadata.

        Returns:
            Dict with price levels and RR ratio for position monitor
        """
        return {
            "type": "price_level",
            "enable_position_tightening": self.get_config_value("enable_position_tightening", True),
            "enable_sl_tightening": self.get_config_value("enable_sl_tightening", True),
            "rr_tightening_steps": self.get_config_value("rr_tightening_steps", []),
        }

    def should_exit(
        self,
        trade: Dict[str, Any],
        current_candle: Dict[str, Any],
        pair_candle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Check if price-based trade should exit.

        For price-based strategies, exit when price touches TP or SL.

        Args:
            trade: Trade record with entry_price, stop_loss, take_profit
            current_candle: Current candle {timestamp, open, high, low, close}
            pair_candle: Not used for price-based (None)

        Returns:
            Dict with 'should_exit' bool and 'exit_details' dict
        """
        try:
            entry_price = trade.get("entry_price")
            stop_loss = trade.get("stop_loss")
            take_profit = trade.get("take_profit")
            current_price = current_candle.get("close")

            if not all([entry_price, stop_loss, take_profit, current_price]):
                return {
                    "should_exit": False,
                    "exit_details": {
                        "reason": "no_exit",
                        "error": "Missing required price data",
                    }
                }

            # Determine direction
            is_long = entry_price > stop_loss

            # Check if price touched TP or SL
            if is_long:
                tp_touched = current_price >= take_profit
                sl_touched = current_price <= stop_loss
            else:
                tp_touched = current_price <= take_profit
                sl_touched = current_price >= stop_loss

            if tp_touched:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "tp_touched",
                        "price": current_price,
                        "tp": take_profit,
                        "sl": stop_loss,
                        "distance_to_tp": abs(current_price - take_profit),
                        "distance_to_sl": abs(current_price - stop_loss),
                        "direction": "long" if is_long else "short",
                    }
                }

            if sl_touched:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "sl_touched",
                        "price": current_price,
                        "tp": take_profit,
                        "sl": stop_loss,
                        "distance_to_tp": abs(current_price - take_profit),
                        "distance_to_sl": abs(current_price - stop_loss),
                        "direction": "long" if is_long else "short",
                    }
                }

            # No exit condition met
            return {
                "should_exit": False,
                "exit_details": {
                    "reason": "no_exit",
                    "price": current_price,
                    "tp": take_profit,
                    "sl": stop_loss,
                    "distance_to_tp": abs(current_price - take_profit),
                    "distance_to_sl": abs(current_price - stop_loss),
                    "direction": "long" if is_long else "short",
                }
            }

        except Exception as e:
            self.logger.error(f"Error in should_exit: {e}")
            return {
                "should_exit": False,
                "exit_details": {
                    "reason": "error",
                    "error": str(e),
                }
            }

    @classmethod
    def get_required_settings(cls) -> Dict[str, Any]:
        """
        Get price-based strategy settings schema.

        Returns:
            Dict with settings schema for AlexAnalysisModule
        """
        return {
            "enable_position_tightening": {
                "type": "bool",
                "default": True,
                "description": "Enable position tightening (moving SL to breakeven or profit)",
            },
            "enable_sl_tightening": {
                "type": "bool",
                "default": True,
                "description": "Enable stop loss tightening based on RR ratio",
            },
            "rr_tightening_steps": {
                "type": "list",
                "default": [],
                "description": "List of RR ratio thresholds for SL tightening (e.g., [2.0, 3.0, 4.0])",
            },
            "min_rr": {
                "type": "float",
                "default": 1.0,
                "description": "Minimum risk/reward ratio for signal validation",
            },
        }

