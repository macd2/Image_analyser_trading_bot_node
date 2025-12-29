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
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy, calculate_dynamic_position
from trading_bot.strategies.cointegration.price_levels import calculate_levels
from trading_bot.strategies.cointegration.run_full_screener import run_screener
from trading_bot.core.utils import normalize_symbol_for_bybit

logger = logging.getLogger(__name__)


class CointegrationAnalysisModule(BaseAnalysisModule):
    """Cointegration-based spread trading strategy."""

    # Strategy type identification
    STRATEGY_TYPE = "spread_based"
    STRATEGY_NAME = "CointegrationSpreadTrader"
    STRATEGY_VERSION = "1.0"

    # Strategy-specific configuration (ready to move to instances.settings.strategy_config)
    # Later: This will be read from instances.settings.strategy_config in database
    STRATEGY_CONFIG = {
        # Pair discovery mode: "static" (use pairs from config) or "auto_screen" (discover pairs dynamically)
        "pair_discovery_mode": "static",

        # Analysis timeframe (NOT the cycle timeframe)
        "analysis_timeframe": "1h",

        # Pair mappings: symbol -> pair_symbol (used only if pair_discovery_mode="static")
        "pairs": {
            "RENDER": "AKT",
            "FIL": "AR",
            "LINK": "API3",
            "AAVE": "COMP",
            "OP": "ARB",
        },

        # Screener settings (used only if pair_discovery_mode="auto_screen")
        "screener_cache_hours": 24,
        "min_volume_usd": 1_000_000,
        "batch_size": 15,
        "candle_limit": 1000,       # Number of candles to fetch per symbol in screener

        # Cointegration parameters (strategy-specific)
        "lookback": 90,           # Lookback period for cointegration analysis
        "z_entry": 2.0,            # Z-score entry threshold for cointegration
        "z_exit": 0.5,             # Z-score exit threshold for cointegration
        "use_adf": True,            # Use ADF test for mean reversion detection (True) or Hurst exponent (False)
        "use_soft_vol": False,      # Use soft volatility adjustment for cointegration
        "min_sl_buffer": 1.5,       # Minimum z-distance from entry to stop loss
        "enable_dynamic_sizing": True,  # Enable dynamic position sizing based on edge and volatility
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

    def _get_strategy_type_prefix(self) -> str:
        """
        Override to return the correct strategy type prefix for cointegration.

        Returns:
            "cointegration" - the prefix used in strategy_specific.cointegration.* settings
        """
        return "cointegration"

    def _get_screener_cache_path(self, timeframe: str) -> Path:
        """Get the path to the screener cache file for this instance and timeframe."""
        cache_dir = Path(__file__).parent / "screener_cache"
        cache_dir.mkdir(exist_ok=True)

        # Use instance_id if available, otherwise use a default name
        instance_name = self.instance_id or "default"
        filename = f"{instance_name}_{timeframe}.json"
        return cache_dir / filename

    def _load_screener_cache(self, timeframe: str) -> Optional[Dict[str, Any]]:
        """Load screener results from cache file if it exists and is fresh."""
        cache_path = self._get_screener_cache_path(timeframe)

        if not cache_path.exists():
            logger.info(f"📊 [CACHE] No screener cache found at {cache_path}")
            return None

        try:
            logger.info(f"📊 [CACHE] Loading screener cache from {cache_path}")
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)

            # Check if cache is fresh
            cache_hours = self.get_config_value('screener_cache_hours', 24)
            screened_at = datetime.fromisoformat(cache_data.get('timestamp', ''))
            cache_age = datetime.now() - screened_at
            cache_age_hours = cache_age.total_seconds() / 3600

            if cache_age > timedelta(hours=cache_hours):
                logger.info(f"📊 [CACHE] Cache is {cache_age_hours:.1f}h old (max: {cache_hours}h), will refresh")
                return None

            # Verify timeframe matches
            cached_timeframe = cache_data.get('timeframe')
            if cached_timeframe != timeframe:
                logger.info(f"📊 [CACHE] Cache has different timeframe ({cached_timeframe} vs {timeframe}), will refresh")
                return None

            num_pairs = len(cache_data.get('pairs', []))
            logger.info(f"✅ [CACHE] Using cached screener results: {num_pairs} pairs, age={cache_age_hours:.1f}h, timeframe={timeframe}")
            return cache_data
        except Exception as e:
            logger.warning(f"⚠️  [CACHE] Failed to load screener cache: {e}")
            return None

    def _save_screener_cache(self, timeframe: str, screener_data: Dict[str, Any]) -> bool:
        """Save screener results to cache file."""
        cache_path = self._get_screener_cache_path(timeframe)

        try:
            num_pairs = len(screener_data.get('pairs', []))
            logger.info(f"📊 [CACHE] Saving screener cache to {cache_path}")
            with open(cache_path, 'w') as f:
                json.dump(screener_data, f, indent=2)
            logger.info(f"✅ [CACHE] Screener cache saved: {num_pairs} pairs, timeframe={timeframe}, file={cache_path}")
            return True
        except Exception as e:
            logger.error(f"❌ [CACHE] Failed to save screener cache: {e}")
            return False

    async def _get_or_refresh_screener_results(self, timeframe: str) -> Dict[str, str]:
        """
        Get screener results from cache or run screener if cache is stale.
        Returns a dict mapping symbol1 -> symbol2 (pairs).
        """
        # Try to load from cache
        cache_data = self._load_screener_cache(timeframe)

        if cache_data:
            # Convert pairs array to dict format
            pairs_dict = {}
            for pair_info in cache_data.get('pairs', []):
                symbol1 = pair_info.get('symbol1')
                symbol2 = pair_info.get('symbol2')
                if symbol1 and symbol2:
                    pairs_dict[symbol1] = symbol2
            return pairs_dict

        # Cache is stale or doesn't exist, run screener
        instance_name = self.instance_id or "default"
        min_volume_usd = self.get_config_value('min_volume_usd')
        batch_size = self.get_config_value('batch_size', 20)
        candle_limit = self.get_config_value('candle_limit', 1000)

        logger.info(f"🔍 [SCREENER] Starting auto-screening for {instance_name}")
        logger.info(f"   Timeframe: {timeframe}")
        logger.info(f"   Min Volume: ${min_volume_usd/1e6:.1f}M")
        logger.info(f"   Batch Size: {batch_size}")
        logger.info(f"   Candle Limit: {candle_limit}")
        self._heartbeat(f"Running screener for timeframe {timeframe}")

        try:
            # Call screener directly (not via subprocess)
            logger.info(f"📊 [SCREENER] Executing pair discovery...")
            pairs_dict = await run_screener(
                timeframe=timeframe,
                instance_id=instance_name,
                min_volume_usd=min_volume_usd,
                batch_size=batch_size,
                candle_limit=candle_limit,
                verbose=False  # Suppress screener's own logging
            )

            if not pairs_dict:
                logger.warning(f"⚠️  [SCREENER] No cointegrated pairs found for {timeframe}")
                self._heartbeat(f"No pairs found for timeframe {timeframe}")
                return {}

            logger.info(f"✅ [SCREENER] Found {len(pairs_dict)} independent pairs:")
            for symbol1, symbol2 in pairs_dict.items():
                logger.info(f"   • {symbol1} <-> {symbol2}")

            self._heartbeat(f"Found {len(pairs_dict)} pairs for timeframe {timeframe}")
            return pairs_dict

        except Exception as e:
            logger.error(f"❌ [SCREENER] Error running screener: {e}", exc_info=True)
            self._heartbeat(f"Error running screener: {e}")
            return {}

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

        # Get configuration
        analysis_timeframe = self.get_config_value('analysis_timeframe', '1h')
        pair_discovery_mode = self.get_config_value('pair_discovery_mode', 'static')

        # Get pairs based on discovery mode
        if pair_discovery_mode == 'auto_screen':
            logger.info(f"🔗 [PAIR DISCOVERY] Mode: AUTO_SCREEN (timeframe: {analysis_timeframe})")
            self._heartbeat(f"Auto-screening for pairs (timeframe: {analysis_timeframe})")
            pairs = await self._get_or_refresh_screener_results(analysis_timeframe)
            logger.info(f"🔗 [PAIR DISCOVERY] Screener returned {len(pairs)} pairs")
        else:
            logger.info(f"🔗 [PAIR DISCOVERY] Mode: STATIC (predefined pairs)")
            pairs = self.get_config_value('pairs', {})
            logger.info(f"🔗 [PAIR DISCOVERY] Using {len(pairs)} static pairs")

        # Cointegration strategy analyzes ONLY symbols in pairs config
        # Completely independent - doesn't use symbols parameter or watchlist
        symbols_to_analyze = list(pairs.keys())

        logger.info(f"🔗 Cointegration Strategy: Starting analysis cycle for {len(symbols_to_analyze)} symbols (timeframe: {analysis_timeframe})", extra={"cycle_id": cycle_id})
        self._heartbeat(f"Starting cointegration analysis for {len(symbols_to_analyze)} symbols (timeframe: {analysis_timeframe})")

        for idx, symbol in enumerate(symbols_to_analyze, 1):
            # Check if bot should stop (graceful shutdown)
            if hasattr(self, '_stop_requested') and self._stop_requested:
                logger.info(f"🔗 Stop requested - halting analysis at symbol {idx}/{len(symbols_to_analyze)}")
                break

            try:
                logger.info(f"🔗 [{idx}/{len(symbols_to_analyze)}] Analyzing {symbol} for cointegration", extra={"symbol": symbol, "cycle_id": cycle_id})
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
                        "analysis": {"error": f"Symbol not available on Bybit: {', '.join(missing)}"},
                        "chart_path": None,
                        "timeframe": analysis_timeframe,
                        "cycle_id": cycle_id,
                        "skipped": True,
                        "skip_reason": f"Symbol not available: {', '.join(missing)}",
                    })
                    continue

                # Fetch candles for both symbols using analysis_timeframe from config
                # Use maximum API limit (1000) to ensure we get enough candles for analysis
                lookback = self.get_config_value('lookback', 90)
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
                logger.info(f"🔗 Analyzing {symbol}/{pair_symbol}", extra={"symbol": symbol, "pair": pair_symbol})
                self._heartbeat(f"Running cointegration analysis for {symbol}")
                strategy = CointegrationStrategy(
                    lookback=self.get_config_value('lookback', 90),
                    z_entry=self.get_config_value('z_entry', 2.0),
                    z_exit=self.get_config_value('z_exit', 0.5),
                    use_adf=self.get_config_value('use_adf', True),
                    use_soft_vol=self.get_config_value('use_soft_vol', False),
                    enable_dynamic_sizing=self.get_config_value('enable_dynamic_sizing', True)
                )

                signals = strategy.generate_signals(df)

                # Get the last valid signal (skip NaN z_scores)
                valid_signals = signals[signals['z_score'].notna()]

                # DEBUG: Log signal generation details
                if not valid_signals.empty:
                    latest = valid_signals.iloc[-1]
                    logger.debug(
                        f"🔗 Signal details for {symbol}/{pair_symbol}: "
                        f"z_score={latest['z_score']:.4f}, "
                        f"is_mr={latest['is_mean_reverting']}, "
                        f"signal={latest['signal']}, "
                        f"z_entry={strategy.z_entry}",
                        extra={"symbol": symbol, "pair": pair_symbol}
                    )

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

                # Compute z_history for adaptive SL calculation
                z_history = [abs((s - spread_mean) / spread_std) for s in spread] if spread_std > 0 else []

                # Convert aligned dataframe back to candle format for price level calculation
                # This ensures we use prices at the same timestamp as the signal
                aligned_candles_1 = [
                    {'timestamp': ts, 'close': close}
                    for ts, close in zip(df['timestamp'], df['close_1'])
                ]
                aligned_candles_2 = [
                    {'timestamp': ts, 'close': close}
                    for ts, close in zip(df['timestamp'], df['close_2'])
                ]

                # Convert to analyzer format with config values
                recommendation = self._convert_signal_to_recommendation(
                    symbol=symbol,
                    signal=latest_signal,
                    candles=aligned_candles_1,
                    cycle_id=cycle_id,
                    analysis_timeframe=analysis_timeframe,
                    confidence=confidence,
                    pair_candles=aligned_candles_2,
                    pair_symbol=pair_symbol,
                    beta=beta,
                    spread_mean=spread_mean,
                    spread_std=spread_std,
                    z_history=z_history
                )

                self._validate_output(recommendation)

                # Log analysis result with verbose format
                analysis = recommendation.get('analysis', {})
                log_message = (
                    f"🔗 {symbol}/{pair_symbol}\n"
                    f"   candles:\n"
                    f"     {symbol}: {len(candles1)}\n"
                    f"     {pair_symbol}: {len(candles2)}\n"
                    f"   z_score: {z_score:.4f}\n"
                    f"   signal: {recommendation['recommendation']}\n"
                    f"   confidence: {recommendation['confidence']:.2f}\n"
                    f"   risk_reward: {recommendation.get('rr_ratio', 0):.2f}"
                )
                logger.info(
                    log_message,
                    extra={"symbol": symbol, "pair": pair_symbol, "recommendation": recommendation['recommendation'], "confidence": recommendation['confidence']}
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
        pair_symbol: Optional[str] = None,
        beta: Optional[float] = None,
        spread_mean: Optional[float] = None,
        spread_std: Optional[float] = None,
        z_history: Optional[List[float]] = None,
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

        # Get z_entry config value early (needed for adaptive SL calculation later)
        z_entry = self.get_config_value('z_entry', 2.0)

        if (signal_direction != 0 and pair_candles and beta is not None and
            spread_mean is not None and spread_std is not None):
            try:
                pair_price = pair_candles[-1]['close']
                min_sl_buffer = self.get_config_value('min_sl_buffer', 1.5)

                # Calculate levels using cointegration formula
                levels = calculate_levels(
                    price_x=current_price,
                    price_y=pair_price,
                    beta=beta,
                    spread_mean=spread_mean,
                    spread_std=spread_std,
                    z_entry=z_entry,
                    signal=signal_direction,
                    z_history=z_history or [],
                    min_sl_buffer=min_sl_buffer
                )

                # Extract spread levels and convert to asset prices
                # NOTE: Cointegration strategy trades the SPREAD, not individual assets
                # Spread = Y - beta * X
                # Exit logic uses z-score, not price levels
                # Price levels stored here are for informational/monitoring purposes only
                spread_levels = levels['spread_levels']
                beta_val = levels['beta']

                # Get spread levels
                spread_entry = spread_levels['entry']
                spread_sl = spread_levels['stop_loss']
                spread_tp = spread_levels['take_profit_2']  # Use full reversion target

                # Convert spread levels to PRIMARY SYMBOL (X) prices for database storage
                # Formula: X = (Y - spread) / beta
                # These prices represent the primary symbol (X) being traded
                # The actual trading is done in spread space via z-score monitoring
                # Note: For SHORT spreads with negative beta, Y prices would be negative
                # so we use X prices which are always positive and meaningful
                if beta_val != 0:
                    entry_price = (pair_candles[-1]['close'] - spread_entry) / beta_val
                    stop_loss = (pair_candles[-1]['close'] - spread_sl) / beta_val
                    take_profit = (pair_candles[-1]['close'] - spread_tp) / beta_val
                else:
                    entry_price = current_price
                    stop_loss = None
                    take_profit = None

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

        # Build strategy metadata for exit logic and monitoring
        strategy_metadata = None
        if beta is not None and spread_mean is not None and spread_std is not None:
            z_exit = self.get_config_value('z_exit', 0.5)

            # Calculate adaptive max_spread_deviation from z_history (99th percentile)
            # This prevents premature stops due to normal volatility while protecting against tail risk
            adaptive_sl_z = 3.0  # Default fallback
            if z_history and len(z_history) > 0:
                try:
                    z_99 = float(np.percentile([abs(z) for z in z_history], 99))
                    # Add 1.5σ buffer to 99th percentile for crypto fat-tail protection
                    adaptive_sl_z = max(z_entry + 1.5, z_99 + 1.5)
                except (ValueError, TypeError):
                    adaptive_sl_z = 3.0

            strategy_metadata = {
                # Current values (for realtime calculations)
                "beta": float(beta),
                "spread_mean": float(spread_mean),
                "spread_std": float(spread_std),
                "z_exit_threshold": float(z_exit),
                "pair_symbol": pair_symbol,

                # Historical values at entry time (FROZEN - for chart and exit logic)
                "z_score_at_entry": float(z_score),
                "spread_mean_at_entry": float(spread_mean),  # Capture at signal time
                "spread_std_at_entry": float(spread_std),    # Capture at signal time

                # Prices at entry time (FROZEN - for fill)
                "price_x_at_entry": float(current_price),
                "price_y_at_entry": float(pair_candles[-1]['close']) if pair_candles else None,

                # Adaptive stop loss
                "max_spread_deviation": float(adaptive_sl_z),
            }

        # Normalize position size multiplier to 0.5-1.5 range
        raw_multiplier = signal.get('size_multiplier', 1.0)
        normalized_multiplier = self.normalize_position_size_multiplier(raw_multiplier)

        # Calculate dynamic position sizing for spread-based trades
        units_x = None
        units_y = None
        if (signal_direction != 0 and beta is not None and spread_mean is not None and
            spread_std is not None and z_history is not None):
            try:
                # Get portfolio value and risk percent from config
                portfolio_value = self.get_config_value('portfolio_value', 10000)
                risk_percent = self.get_config_value('risk_percent', 0.02)

                # Calculate dynamic position
                position_sizing = calculate_dynamic_position(
                    portfolio_value=portfolio_value,
                    risk_percent=risk_percent,
                    z_entry=z_entry,
                    z_score_current=z_score,
                    spread_mean=spread_mean,
                    spread_std=spread_std,
                    beta=beta,
                    signal=signal_direction,
                    z_history=z_history,
                    confidence=confidence
                )

                units_x = position_sizing['units_x']
                units_y = position_sizing['units_y']

                self.logger.debug(
                    f"Position sizing for {symbol}/{pair_symbol}: "
                    f"units_x={units_x:.4f}, units_y={units_y:.4f}, "
                    f"risk_usd=${position_sizing['spread_risk_usd']:.2f}"
                )
            except Exception as e:
                self.logger.warning(f"Failed to calculate dynamic position sizing for {symbol}: {e}")
                units_x = None
                units_y = None

        return {
            "symbol": symbol,
            "recommendation": recommendation,
            "confidence": confidence,
            "setup_quality": signal.get('size_multiplier', 0.5),
            "position_size_multiplier": normalized_multiplier,
            "market_environment": 0.5,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "analysis": {
                "strategy": "cointegration",
                "z_score": float(z_score),
                "is_mean_reverting": bool(signal.get('is_mean_reverting', False)),
                "size_multiplier": float(signal.get('size_multiplier', 1.0)),
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward_ratio": risk_reward,
            },
            "chart_path": "",
            "timeframe": analysis_timeframe,
            "cycle_id": cycle_id,
            # Add strategy UUID for traceability
            "strategy_uuid": self.strategy_uuid,
            "strategy_type": self.STRATEGY_TYPE,
            "strategy_name": self.STRATEGY_NAME,
            # Add strategy metadata for exit logic and monitoring
            "strategy_metadata": strategy_metadata,
            # Spread-based position sizing (units for both symbols)
            "units_x": units_x,
            "units_y": units_y,
            "pair_symbol": pair_symbol,
            # Add validation results for reproducibility
            "validation_results": {
                "z_score_valid": z_score is not None,
                "price_levels_valid": entry_price is not None and stop_loss is not None and take_profit is not None,
                "mean_reverting": signal.get('is_mean_reverting', False),
                "confidence_valid": 0 <= confidence <= 1,
            },
        }

    def validate_signal(self, signal: Dict[str, Any]) -> bool:
        """
        Validate spread-based signal.

        Checks:
        - Z-score distance to SL is adequate (>= min_z_distance)
        - Spread levels are in correct order
        - Confidence is reasonable

        Args:
            signal: Signal dict with z_score, entry_price, stop_loss, take_profit

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        min_z_distance = self.get_config_value("min_z_distance", 0.5)

        z_score = signal.get("z_score", 0)
        entry = signal.get("entry_price")
        sl = signal.get("stop_loss")
        tp = signal.get("take_profit")

        if not all([entry, sl, tp]):
            raise ValueError(f"Missing price levels: entry={entry}, sl={sl}, tp={tp}")

        if entry <= 0 or sl <= 0 or tp <= 0:
            raise ValueError(f"Prices must be positive: entry={entry}, sl={sl}, tp={tp}")

        # For spread-based, check z-score distance to SL
        z_distance_to_sl = abs(z_score)
        if z_distance_to_sl < min_z_distance:
            raise ValueError(
                f"Z-score distance to SL {z_distance_to_sl:.2f} below minimum {min_z_distance}"
            )

        # Determine direction based on entry vs SL
        is_long = entry > sl

        if is_long:
            if not (sl < entry < tp):
                raise ValueError(
                    f"Long signal prices in wrong order: SL({sl}) < Entry({entry}) < TP({tp})"
                )
        else:
            if not (tp < entry < sl):
                raise ValueError(
                    f"Short signal prices in wrong order: TP({tp}) < Entry({entry}) < SL({sl})"
                )

        return True

    def calculate_risk_metrics(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate spread-based risk metrics.

        Returns:
            Dict with: z_distance_to_sl, z_distance_to_tp, spread_volatility
        """
        z_score = signal.get("z_score", 0)
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
            "z_score": z_score,
            "z_distance_to_sl": abs(z_score),
            "risk_per_unit": risk_per_unit,
            "reward_per_unit": reward_per_unit,
            "risk_reward_ratio": rr_ratio,
        }

    def get_exit_condition(self) -> Dict[str, Any]:
        """
        Get spread-based exit condition metadata.

        Returns:
            Dict with z-score exit parameters for simulator to check
        """
        z_exit = self.get_config_value("z_exit", 0.4)

        return {
            "type": "z_score",
            "z_exit": z_exit,
            "description": f"Exit when z-score crosses {z_exit} threshold",
        }

    def get_monitoring_metadata(self) -> Dict[str, Any]:
        """
        Get spread-based monitoring metadata.

        Returns:
            Dict with z-score exit parameters and age-based cancellation config
        """
        z_exit = self.get_config_value("z_exit", 0.5)

        return {
            "type": "z_score",
            "z_exit": z_exit,
            # Age-based cancellation: ALWAYS ON for spread-based strategies
            # Uses time-based (5 minutes = 300 seconds) instead of bar-based
            # to avoid long timeouts on higher timeframes (e.g., 1d)
            "enable_age_cancellation": True,
            "age_cancellation_seconds": 300,  # 5 minutes timeout for all timeframes
        }

    def _fetch_pair_candle_from_api(
        self,
        pair_symbol: str,
        current_candle: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch the pair candle from live API for the same timestamp as current_candle.

        This is called by should_exit() when pair_candle is not provided.
        Used by simulator to get real-time pair data for z-score calculation.

        Args:
            pair_symbol: Symbol of the pair (e.g., "ETH")
            current_candle: Current candle with timestamp

        Returns:
            Pair candle dict with {timestamp, open, high, low, close} or None if fetch fails
        """
        if not self.candle_adapter:
            logger.warning(f"Candle adapter not available, cannot fetch pair candle for {pair_symbol}")
            return None

        try:
            # Get the timestamp from current candle
            current_timestamp = current_candle.get("timestamp")
            if not current_timestamp:
                logger.warning("Current candle has no timestamp, cannot fetch pair candle")
                return None

            # Normalize pair symbol for Bybit
            normalized_pair = normalize_symbol_for_bybit(pair_symbol)

            # Fetch just 1 candle from API for this timestamp
            # Use prefer_source="api" to get live data, not cached
            candles = asyncio.run(self.candle_adapter.get_candles(
                normalized_pair,
                timeframe="1h",  # Use same timeframe as analysis
                limit=1,
                min_candles=1,
                prefer_source="api",  # Always fetch from live API
                cache_to_db=False  # Don't cache for simulator
            ))

            if candles and len(candles) > 0:
                # Return the most recent candle
                pair_candle = candles[-1]
                logger.debug(f"Fetched pair candle for {pair_symbol}: close={pair_candle.get('close')}")
                return pair_candle
            else:
                logger.warning(f"No candles returned from API for {pair_symbol}")
                return None

        except Exception as e:
            logger.error(f"Error fetching pair candle for {pair_symbol}: {e}", exc_info=True)
            return None

    def should_exit(
        self,
        trade: Dict[str, Any],
        current_candle: Dict[str, Any],
        pair_candle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Check if spread-based trade should exit.

        Exit conditions (checked in order):
        1. Z-score crosses exit threshold (mean reversion)
        2. Z-score exceeds max_spread_deviation (risk management - if enabled)

        Args:
            trade: Trade record with strategy_metadata containing beta, spread_mean, spread_std, z_exit_threshold, pair_symbol
            current_candle: Current candle for main symbol {timestamp, open, high, low, close}
            pair_candle: Optional pair candle (if not provided, will fetch from live API)

        Returns:
            Dict with 'should_exit' bool and 'exit_details' dict
        """
        try:
            # Get strategy metadata stored during trade creation
            metadata = trade.get("strategy_metadata", {})
            beta = metadata.get("beta")
            spread_mean = metadata.get("spread_mean")
            spread_std = metadata.get("spread_std")
            z_exit_threshold = metadata.get("z_exit_threshold")
            pair_symbol = metadata.get("pair_symbol")

            # Validate we have all needed data (use 'is not None' to allow 0 values)
            if beta is None or spread_mean is None or spread_std is None or z_exit_threshold is None:
                return {
                    "should_exit": False,
                    "exit_details": {
                        "reason": "no_exit",
                        "error": "Missing strategy metadata for z-score calculation",
                    }
                }

            # Get current prices
            current_price = current_candle.get("close")

            # If pair_candle not provided, fetch from live API
            if not pair_candle and pair_symbol:
                try:
                    pair_candle = self._fetch_pair_candle_from_api(pair_symbol, current_candle)
                except Exception as e:
                    logger.error(f"Failed to fetch pair candle for {pair_symbol}: {e}")
                    return {
                        "should_exit": False,
                        "exit_details": {
                            "reason": "no_exit",
                            "error": f"Failed to fetch pair candle: {e}",
                        }
                    }

            pair_price = pair_candle.get("close") if pair_candle else None

            if not current_price or not pair_price:
                return {
                    "should_exit": False,
                    "exit_details": {
                        "reason": "no_exit",
                        "error": "Missing candle data for z-score calculation",
                    }
                }

            # Recalculate z-score with current prices
            spread = pair_price - beta * current_price
            z_score = (spread - spread_mean) / spread_std if spread_std > 0 else 0

            # Get adaptive max_spread_deviation from metadata (stored at entry time)
            # Falls back to global config if not in metadata (for backward compatibility)
            max_spread_deviation = metadata.get("max_spread_deviation")
            if max_spread_deviation is None:
                max_spread_deviation = self.get_config_value("max_spread_deviation", 3.0)

            # Check if z-score crossed exit threshold (mean reversion)
            threshold_crossed = abs(z_score) <= z_exit_threshold

            if threshold_crossed:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "z_score_exit",
                        "z_score": float(z_score),
                        "spread": float(spread),
                        "threshold": float(z_exit_threshold),
                        "threshold_crossed": True,
                        "beta": float(beta),
                        "spread_mean": float(spread_mean),
                        "spread_std": float(spread_std),
                        "pair_symbol": pair_symbol,
                        "current_price": float(current_price),
                        "pair_price": float(pair_price),
                    }
                }

            # Check if z-score exceeded max_spread_deviation (force-close for risk management)
            if max_spread_deviation > 0 and abs(z_score) >= max_spread_deviation:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "max_spread_deviation_exceeded",
                        "z_score": float(z_score),
                        "spread": float(spread),
                        "max_deviation": float(max_spread_deviation),
                        "deviation_exceeded": True,
                        "beta": float(beta),
                        "spread_mean": float(spread_mean),
                        "spread_std": float(spread_std),
                        "pair_symbol": pair_symbol,
                        "current_price": float(current_price),
                        "pair_price": float(pair_price),
                    }
                }

            # No exit condition met
            return {
                "should_exit": False,
                "exit_details": {
                    "reason": "no_exit",
                    "z_score": float(z_score),
                    "spread": float(spread),
                    "threshold": float(z_exit_threshold),
                    "threshold_crossed": False,
                    "max_deviation": float(max_spread_deviation) if max_spread_deviation > 0 else None,
                    "deviation_exceeded": False if max_spread_deviation > 0 else None,
                    "beta": float(beta),
                    "spread_mean": float(spread_mean),
                    "spread_std": float(spread_std),
                    "pair_symbol": pair_symbol,
                    "current_price": float(current_price),
                    "pair_price": float(pair_price),
                }
            }

        except Exception as e:
            logger.error(f"Error in should_exit: {e}")
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
        Get spread-based strategy settings schema.

        Returns:
            Dict with settings schema for CointegrationAnalysisModule
        """
        return {
            # Pair discovery settings
            "pair_discovery_mode": {
                "type": "select",
                "options": [
                    {"value": "static", "label": "Static (predefined pairs)"},
                    {"value": "auto_screen", "label": "Auto-Screen (discover pairs)"},
                ],
                "default": "static",
                "description": "How to discover trading pairs: static (use configured pairs) or auto_screen (run screener)",
            },
            "analysis_timeframe": {
                "type": "select",
                "options": [
                    {"value": "1m", "label": "1 minute"},
                    {"value": "5m", "label": "5 minutes"},
                    {"value": "15m", "label": "15 minutes"},
                    {"value": "30m", "label": "30 minutes"},
                    {"value": "1h", "label": "1 hour"},
                    {"value": "4h", "label": "4 hours"},
                    {"value": "1d", "label": "1 day"},
                ],
                "default": "1h",
                "description": "Timeframe for cointegration analysis (independent of cycle timeframe)",
            },
            "screener_cache_hours": {
                "type": "number",
                "default": 24,
                "description": "How long to cache screener results before refreshing (hours)",
            },
            "min_volume_usd": {
                "type": "number",
                "default": 1000000,
                "description": "Minimum 24h trading volume in USD for pair screening",
            },
            "batch_size": {
                "type": "number",
                "default": 15,
                "description": "Number of symbols to process per batch during screening",
            },
            "candle_limit": {
                "type": "number",
                "default": 1000,
                "description": "Number of candles to fetch per symbol during screening",
            },

            # Cointegration analysis settings
            "lookback": {
                "type": "number",
                "default": 90,
                "description": "Lookback period (candles) for cointegration analysis",
            },
            "z_entry": {
                "type": "float",
                "default": 2.0,
                "description": "Z-score threshold for entry signal",
            },
            "z_exit": {
                "type": "float",
                "default": 0.5,
                "description": "Z-score threshold for exit signal",
            },
            "use_adf": {
                "type": "boolean",
                "default": True,
                "description": "Use ADF test for mean reversion detection (True) or Hurst exponent (False). ADF is stricter and more selective for signals.",
            },
            "use_soft_vol": {
                "type": "boolean",
                "default": False,
                "description": "Use soft volatility adjustment for cointegration",
            },
            "min_sl_buffer": {
                "type": "float",
                "default": 1.5,
                "description": "Minimum z-distance from entry to stop loss (adaptive SL buffer)",
            },
            "enable_dynamic_sizing": {
                "type": "boolean",
                "default": True,
                "description": "Enable dynamic position sizing based on edge and volatility",
            },

            # Risk management settings
            "max_spread_deviation": {
                "type": "float",
                "default": 3.0,
                "description": "Maximum z-score deviation before closing position. Set to 0 to disable.",
            },
            "min_z_distance": {
                "type": "float",
                "default": 0.5,
                "description": "Minimum z-score distance to SL for signal validation",
            },
        }

