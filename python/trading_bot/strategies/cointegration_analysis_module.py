"""
CointegrationAnalysisModule - Spread Trading Strategy

Cointegration-based strategy for trading correlated pairs.
Completely independent from chart-based strategies.

Features:
- Pair-based analysis (symbol + pair_symbol)
- Cointegration detection
- Z-score based entry/exit signals
- Mean reversion trading
"""

from typing import Dict, Any, List, Optional, Callable
import numpy as np
import pandas as pd
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.spread_trading_cointegrated import CointegrationStrategy
from trading_bot.core.utils import normalize_symbol_for_bybit


class CointegrationAnalysisModule(BaseAnalysisModule):
    """Cointegration-based spread trading strategy."""

    # Strategy-specific configuration (ready to move to instances.settings.strategy_config)
    # Later: This will be read from instances.settings.strategy_config in database
    STRATEGY_CONFIG = {
        # Analysis timeframe (NOT the cycle timeframe)
        "analysis_timeframe": "1h",

        # Pair mappings: symbol -> pair_symbol
        "pairs": {
            "RENDER": "AKT",
            "FIL": "AR",
            "LINK": "API3",
            "AAVE": "COMP",
            "OP": "ARB",
        },

        # Cointegration parameters (strategy-specific)
        "lookback": 120,           # Lookback period for cointegration analysis
        "z_entry": 2.0,            # Z-score entry threshold for cointegration
        "z_exit": 0.5,             # Z-score exit threshold for cointegration
        "use_soft_vol": False,      # Use soft volatility adjustment for cointegration
    }

    DEFAULT_CONFIG = STRATEGY_CONFIG  # Use STRATEGY_CONFIG as default

    # Note: Price levels (entry, SL, TP) are calculated from the cointegration signal
    # Confidence is calculated from z-score
    # These are returned in the output, not configured here

    def __init__(
        self,
        config: 'Config',
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        heartbeat_callback: Optional[Callable] = None,
    ):
        """Initialize cointegration strategy."""
        super().__init__(config, instance_id, run_id, strategy_config, heartbeat_callback)

    async def run_analysis_cycle(
        self,
        symbols: List[str],
        timeframe: str,
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Analyze symbols using cointegration strategy.

        Each strategy is COMPLETELY INDEPENDENT:
        - Gets symbols from config (NOT from caller/watchlist)
        - For each symbol, gets its pair from config
        - Fetches candles (NOT chart images)
        - Runs cointegration analysis
        - Returns same output format

        Note: symbols and timeframe parameters are IGNORED
        Note: Uses analysis_timeframe and pairs from config only
        """
        results = []

        # Get configuration (will be read from instance settings later)
        pairs = self.get_config_value('pairs', {})
        analysis_timeframe = self.get_config_value('analysis_timeframe', '1h')

        # Cointegration strategy analyzes ONLY symbols in pairs config
        # Completely independent - doesn't use symbols parameter or watchlist
        symbols_to_analyze = list(pairs.keys())

        self._heartbeat(f"Starting cointegration analysis for {len(symbols_to_analyze)} symbols (timeframe: {analysis_timeframe})")

        for symbol in symbols_to_analyze:
            try:
                self._heartbeat(f"Analyzing {symbol}")

                # Get pair symbol from config
                pair_symbol = pairs.get(symbol)
                if not pair_symbol:
                    self._heartbeat(f"No pair configured for {symbol}")
                    results.append({
                        "symbol": symbol,
                        "recommendation": "HOLD",
                        "confidence": 0.0,
                        "entry_price": None,
                        "stop_loss": None,
                        "take_profit": None,
                        "risk_reward": 0,
                        "setup_quality": 0.0,
                        "market_environment": 0.5,
                        "analysis": {"error": f"No pair configured for {symbol}"},
                        "chart_path": "",
                        "timeframe": analysis_timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": "No pair configured",
                    })
                    continue

                # Normalize symbols for Bybit API
                normalized_symbol = normalize_symbol_for_bybit(symbol)
                normalized_pair = normalize_symbol_for_bybit(pair_symbol)

                # Check if symbols exist on Bybit before fetching
                symbol_exists = await self.candle_adapter.symbol_exists(normalized_symbol)
                pair_exists = await self.candle_adapter.symbol_exists(normalized_pair)

                if not symbol_exists or not pair_exists:
                    missing = []
                    if not symbol_exists:
                        missing.append(normalized_symbol)
                    if not pair_exists:
                        missing.append(normalized_pair)
                    self._heartbeat(f"Symbol(s) not available on Bybit: {', '.join(missing)}")
                    results.append({
                        "symbol": symbol,
                        "recommendation": "HOLD",
                        "confidence": 0.0,
                        "entry_price": None,
                        "stop_loss": None,
                        "take_profit": None,
                        "risk_reward": 0.0,
                        "setup_quality": 0.0,
                        "market_environment": None,
                        "analysis": f"Symbol not available on Bybit: {', '.join(missing)}",
                        "chart_path": None,
                        "timeframe": analysis_timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": f"Symbol not available: {', '.join(missing)}",
                    })
                    continue

                # Fetch candles for both symbols using analysis_timeframe from config
                # Use higher limit to ensure we get enough candles even if some are missing
                lookback = self.get_config_value('lookback', 120)
                min_candles_needed = max(lookback + 10, 50)  # Need at least lookback + buffer
                self._heartbeat(f"Fetching candles for {symbol} and {pair_symbol}")
                candles1 = await self.candle_adapter.get_candles(
                    normalized_symbol,
                    analysis_timeframe,
                    limit=500,  # Request more candles to ensure we have enough
                    min_candles=min_candles_needed,
                    cache_to_db=False  # Skip caching for faster test execution
                )
                candles2 = await self.candle_adapter.get_candles(
                    normalized_pair,
                    analysis_timeframe,
                    limit=500,  # Request more candles to ensure we have enough
                    min_candles=min_candles_needed,
                    cache_to_db=False  # Skip caching for faster test execution
                )

                if not candles1 or not candles2:
                    self._heartbeat(f"Failed to fetch candles for {symbol}/{pair_symbol} (got {len(candles1) if candles1 else 0} and {len(candles2) if candles2 else 0})")
                    results.append({
                        "symbol": symbol,
                        "recommendation": "HOLD",
                        "confidence": 0.0,
                        "entry_price": None,
                        "stop_loss": None,
                        "take_profit": None,
                        "risk_reward": 0,
                        "setup_quality": 0.0,
                        "market_environment": 0.5,
                        "analysis": {"error": "Failed to fetch candles"},
                        "chart_path": "",
                        "timeframe": timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": "Insufficient candle data",
                    })
                    continue

                # Merge candles into DataFrame
                # candles1 and candles2 are List[Dict[str, Any]] from CandleAdapter
                # Align by timestamp to handle different lengths
                df1 = pd.DataFrame({
                    'timestamp': [c['timestamp'] for c in candles1],
                    'close_1': [c['close'] for c in candles1]
                })
                df2 = pd.DataFrame({
                    'timestamp': [c['timestamp'] for c in candles2],
                    'close_2': [c['close'] for c in candles2]
                })

                # Merge on timestamp to align candles
                df = pd.merge(df1, df2, on='timestamp', how='inner')
                self._heartbeat(f"Aligned {len(df)} candles for {symbol}/{pair_symbol} (from {len(df1)} and {len(df2)})")

                # Check if we have enough aligned candles
                if len(df) < 10:
                    self._heartbeat(f"Insufficient aligned candles for {symbol}/{pair_symbol} (got {len(df)})")
                    results.append({
                        "symbol": symbol,
                        "recommendation": "HOLD",
                        "confidence": 0.0,
                        "entry_price": None,
                        "stop_loss": None,
                        "take_profit": None,
                        "risk_reward": 0,
                        "setup_quality": 0.0,
                        "market_environment": 0.5,
                        "analysis": {"error": f"Insufficient aligned candles ({len(df)})"},
                        "chart_path": "",
                        "timeframe": analysis_timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": "Insufficient aligned candles",
                    })
                    continue

                # Run cointegration strategy with config values
                self._heartbeat(f"Running cointegration analysis for {symbol}")
                strategy = CointegrationStrategy(
                    lookback=self.get_config_value('lookback', 120),
                    z_entry=self.get_config_value('z_entry', 2.0),
                    z_exit=self.get_config_value('z_exit', 0.5),
                    use_soft_vol=self.get_config_value('use_soft_vol', False)
                )

                signals = strategy.generate_signals(df)

                # Get the last valid signal (skip NaN z_scores)
                valid_signals = signals[signals['z_score'].notna()]
                if valid_signals.empty:
                    self._heartbeat(f"No valid signals for {symbol}/{pair_symbol}")
                    results.append({
                        "symbol": symbol,
                        "recommendation": "HOLD",
                        "confidence": 0.0,
                        "entry_price": None,
                        "stop_loss": None,
                        "take_profit": None,
                        "risk_reward": 0,
                        "setup_quality": 0.0,
                        "market_environment": 0.5,
                        "analysis": {"error": "No valid signals generated"},
                        "chart_path": "",
                        "timeframe": analysis_timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": "No valid signals",
                    })
                    continue

                latest_signal = valid_signals.iloc[-1]

                # Compute confidence using the strategy's method
                # Use aligned data from df, not original candles which may have different lengths
                close_1 = np.array(df['close_1'].values, dtype=float)
                close_2 = np.array(df['close_2'].values, dtype=float)
                beta = strategy._compute_beta(close_1, close_2)
                spread = close_2 - beta * close_1
                z_score = latest_signal['z_score']
                confidence = strategy.compute_confidence(spread, z_score)

                # Convert to analyzer format with config values
                recommendation = self._convert_signal_to_recommendation(
                    symbol=symbol,
                    signal=latest_signal,
                    candles=candles1,
                    cycle_id=cycle_id,
                    analysis_timeframe=analysis_timeframe,
                    confidence=confidence
                )

                self._validate_output(recommendation)
                results.append(recommendation)
                self._heartbeat(f"Completed {symbol}: {recommendation['recommendation']}")

            except Exception as e:
                self.logger.error(f"Error analyzing {symbol}: {e}")
                self._heartbeat(f"Error analyzing {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "error": str(e),
                    "timeframe": timeframe,
                    "cycle_id": cycle_id,
                })

        self._heartbeat("Cointegration analysis cycle complete")
        return results

    def _convert_signal_to_recommendation(
        self,
        symbol: str,
        signal: pd.Series,
        candles: List[Dict[str, Any]],
        cycle_id: str,
        analysis_timeframe: str,
        confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Convert cointegration signal to analyzer format."""
        z_score = signal['z_score']
        signal_val = signal['signal']
        current_price = candles[-1]['close']  # Get latest candle's close price

        # Use provided confidence or fallback to z-score based calculation
        if confidence is None:
            # Map z-score to confidence (0-1 range)
            # Higher z-score = stronger signal = higher confidence
            confidence = min(0.95, 0.5 + abs(z_score) * 0.15)

        # Map signal to recommendation
        if signal_val == 1:
            recommendation = "BUY"
        elif signal_val == -1:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"

        # Calculate price levels from current price
        # These are just initial estimates - position sizer will adjust based on risk_percentage
        entry_price = current_price
        if recommendation == "BUY":
            stop_loss = current_price * 0.98  # 2% below entry
            take_profit = current_price * 1.04  # 4% above entry
        elif recommendation == "SELL":
            stop_loss = current_price * 1.02  # 2% above entry
            take_profit = current_price * 0.96  # 4% below entry
        else:
            stop_loss = None
            take_profit = None

        # Calculate risk-reward
        if stop_loss and take_profit:
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)
            risk_reward = reward / risk if risk > 0 else 0
        else:
            risk_reward = 0

        return {
            "symbol": symbol,
            "recommendation": recommendation,
            "confidence": confidence,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": risk_reward,
            "setup_quality": signal.get('size_multiplier', 0.5),
            "market_environment": 0.5,
            "analysis": {
                "strategy": "cointegration",
                "z_score": float(z_score),
                "is_mean_reverting": bool(signal.get('is_mean_reverting', False)),
                "size_multiplier": float(signal.get('size_multiplier', 1.0)),
            },
            "chart_path": "",
            "timeframe": analysis_timeframe,
            "cycle_id": cycle_id,
        }

