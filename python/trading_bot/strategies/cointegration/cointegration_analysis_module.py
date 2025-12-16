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
import logging
import numpy as np
import pandas as pd
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy
from trading_bot.strategies.cointegration.price_levels import calculate_levels
from trading_bot.core.utils import normalize_symbol_for_bybit

logger = logging.getLogger(__name__)


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

        logger.info(f"🔗 Cointegration Strategy: Starting analysis cycle for {len(symbols_to_analyze)} symbols (timeframe: {analysis_timeframe})", extra={"cycle_id": cycle_id})
        self._heartbeat(f"Starting cointegration analysis for {len(symbols_to_analyze)} symbols (timeframe: {analysis_timeframe})")

        for symbol in symbols_to_analyze:
            try:
                logger.info(f"🔗 Analyzing {symbol} for cointegration", extra={"symbol": symbol, "cycle_id": cycle_id})
                self._heartbeat(f"Analyzing {symbol}")

                # Get pair symbol from config
                pair_symbol = pairs.get(symbol)
                if not pair_symbol:
                    logger.warning(f"🔗 No pair configured for {symbol}", extra={"symbol": symbol})
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
                # Use maximum API limit (1000) to ensure we get enough candles for analysis
                lookback = self.get_config_value('lookback', 120)
                min_candles_needed = max(lookback + 10, 50)  # Need at least lookback + buffer
                self._heartbeat(f"Fetching candles for {symbol} and {pair_symbol}")
                candles1 = await self.candle_adapter.get_candles(
                    normalized_symbol,
                    analysis_timeframe,
                    limit=1000,  # Request maximum API limit for better analysis
                    min_candles=min_candles_needed,
                    prefer_source="api",  # Always fetch fresh data from API
                    cache_to_db=False  # Skip caching for faster test execution
                )
                candles2 = await self.candle_adapter.get_candles(
                    normalized_pair,
                    analysis_timeframe,
                    limit=1000,  # Request maximum API limit for better analysis
                    min_candles=min_candles_needed,
                    prefer_source="api",  # Always fetch fresh data from API
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
                logger.info(f"🔗 Running cointegration analysis for {symbol}/{pair_symbol}", extra={"symbol": symbol, "pair": pair_symbol})
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
                    logger.warning(f"🔗 No valid signals for {symbol}/{pair_symbol}", extra={"symbol": symbol, "pair": pair_symbol})
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
                logger.debug(f"🔗 Latest signal for {symbol}: {latest_signal.to_dict()}", extra={"symbol": symbol})

                # Compute confidence using the strategy's method
                # Use aligned data from df, not original candles which may have different lengths
                close_1 = np.array(df['close_1'].values, dtype=float)
                close_2 = np.array(df['close_2'].values, dtype=float)
                beta = float(strategy._compute_beta(close_1, close_2))
                spread = close_2 - beta * close_1
                spread_mean = float(np.mean(spread))
                spread_std = float(np.std(spread))
                z_score = latest_signal['z_score']
                confidence = strategy.compute_confidence(spread, z_score)

                # Convert to analyzer format with config values
                recommendation = self._convert_signal_to_recommendation(
                    symbol=symbol,
                    signal=latest_signal,
                    candles=candles1,
                    cycle_id=cycle_id,
                    analysis_timeframe=analysis_timeframe,
                    confidence=confidence,
                    pair_candles=candles2,
                    beta=beta,
                    spread_mean=spread_mean,
                    spread_std=spread_std
                )

                self._validate_output(recommendation)
                logger.info(
                    f"🔗 {symbol} cointegration result: {recommendation['recommendation']} (confidence: {recommendation['confidence']:.2f})",
                    extra={"symbol": symbol, "recommendation": recommendation['recommendation'], "confidence": recommendation['confidence']}
                )
                results.append(recommendation)
                self._heartbeat(f"Completed {symbol}: {recommendation['recommendation']}")

            except Exception as e:
                logger.error(f"🔗 Error analyzing {symbol}: {e}", exc_info=True, extra={"symbol": symbol})
                self.logger.error(f"Error analyzing {symbol}: {e}")
                self._heartbeat(f"Error analyzing {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "error": str(e),
                    "timeframe": timeframe,
                    "cycle_id": cycle_id,
                })

        logger.info(f"🔗 Cointegration analysis cycle complete: {len(results)} results", extra={"cycle_id": cycle_id, "result_count": len(results)})
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
        pair_candles: Optional[List[Dict[str, Any]]] = None,
        beta: Optional[float] = None,
        spread_mean: Optional[float] = None,
        spread_std: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Convert cointegration signal to analyzer format with calculated price levels."""
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
            signal_direction = 1  # Long spread
        elif signal_val == -1:
            recommendation = "SELL"
            signal_direction = -1  # Short spread
        else:
            recommendation = "HOLD"
            signal_direction = 0

        # Calculate price levels using cointegration statistics
        entry_price = current_price
        stop_loss = None
        take_profit = None
        risk_reward = 0

        if (signal_direction != 0 and pair_candles and beta is not None and
            spread_mean is not None and spread_std is not None):
            try:
                pair_price = pair_candles[-1]['close']
                z_entry = self.get_config_value('z_entry', 2.0)

                # Calculate levels using cointegration formula
                levels = calculate_levels(
                    price_x=current_price,
                    price_y=pair_price,
                    beta=beta,
                    spread_mean=spread_mean,
                    spread_std=spread_std,
                    z_entry=z_entry,
                    signal=signal_direction
                )

                # Extract price levels for the primary symbol
                entry_price = levels['entry']['x']
                stop_loss = levels['stop_loss']['x']
                take_profit = levels['take_profit_2']['x']  # Use full reversion target

                # Calculate risk-reward
                if stop_loss and take_profit:
                    risk = abs(entry_price - stop_loss)
                    reward = abs(take_profit - entry_price)
                    risk_reward = reward / risk if risk > 0 else 0
            except Exception as e:
                self.logger.warning(f"Failed to calculate levels for {symbol}: {e}")
                # Fallback to simple percentage-based levels
                entry_price = current_price
                if recommendation == "BUY":
                    stop_loss = current_price * 0.98
                    take_profit = current_price * 1.04
                elif recommendation == "SELL":
                    stop_loss = current_price * 1.02
                    take_profit = current_price * 0.96
        else:
            # Fallback to simple percentage-based levels
            if recommendation == "BUY":
                stop_loss = current_price * 0.98
                take_profit = current_price * 1.04
            elif recommendation == "SELL":
                stop_loss = current_price * 1.02
                take_profit = current_price * 0.96

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

