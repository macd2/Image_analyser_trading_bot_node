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
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy
from trading_bot.strategies.cointegration.price_levels import calculate_levels
from trading_bot.core.utils import normalize_symbol_for_bybit

logger = logging.getLogger(__name__)


class CointegrationAnalysisModule(BaseAnalysisModule):
    """Cointegration-based spread trading strategy."""

    # Strategy type identification
    STRATEGY_TYPE = "spread_based"
    STRATEGY_NAME = "CointegrationAnalysisModule"
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
            logger.debug(f"📊 No screener cache found at {cache_path}")
            return None

        try:
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)

            # Check if cache is fresh
            cache_hours = self.get_config_value('screener_cache_hours', 24)
            screened_at = datetime.fromisoformat(cache_data.get('timestamp', ''))
            cache_age = datetime.now() - screened_at

            if cache_age > timedelta(hours=cache_hours):
                logger.info(f"📊 Screener cache is {cache_age.total_seconds()/3600:.1f}h old (max: {cache_hours}h), will refresh")
                return None

            # Verify timeframe matches
            cached_timeframe = cache_data.get('timeframe')
            if cached_timeframe != timeframe:
                logger.info(f"📊 Screener cache has different timeframe ({cached_timeframe} vs {timeframe}), will refresh")
                return None

            logger.info(f"✅ Using cached screener results ({cache_age.total_seconds()/3600:.1f}h old, timeframe={timeframe})")
            return cache_data
        except Exception as e:
            logger.warning(f"⚠️  Failed to load screener cache: {e}")
            return None

    def _save_screener_cache(self, timeframe: str, screener_data: Dict[str, Any]) -> bool:
        """Save screener results to cache file."""
        cache_path = self._get_screener_cache_path(timeframe)

        try:
            with open(cache_path, 'w') as f:
                json.dump(screener_data, f, indent=2)
            logger.info(f"✅ Screener results saved to cache: {cache_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save screener cache: {e}")
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
        logger.info(f"📊 Running screener for timeframe {timeframe}...")
        self._heartbeat(f"Running screener for timeframe {timeframe}")

        try:
            screener_script = Path(__file__).parent / "run_full_screener.py"
            instance_name = self.instance_id or "default"

            # Get screener settings from config
            min_volume_usd = self.get_config_value('min_volume_usd', 1_000_000)
            batch_size = self.get_config_value('batch_size', 15)

            result = subprocess.run(
                [
                    sys.executable, str(screener_script),
                    "--timeframe", timeframe,
                    "--instance-id", instance_name,
                    "--min-volume-usd", str(min_volume_usd),
                    "--batch-size", str(batch_size)
                ],
                cwd=Path(__file__).parent,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"❌ Screener failed: {result.stderr}")
                self._heartbeat(f"Screener failed for timeframe {timeframe}")
                return {}

            # Load the newly generated results
            cache_path = self._get_screener_cache_path(timeframe)
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    screener_data = json.load(f)

                # Convert pairs array to dict format
                pairs_dict = {}
                for pair_info in screener_data.get('pairs', []):
                    symbol1 = pair_info.get('symbol1')
                    symbol2 = pair_info.get('symbol2')
                    if symbol1 and symbol2:
                        pairs_dict[symbol1] = symbol2

                logger.info(f"✅ Screener completed: found {len(pairs_dict)} pairs")
                self._heartbeat(f"Screener found {len(pairs_dict)} pairs")
                return pairs_dict
            else:
                logger.error(f"❌ Screener results file not found at {cache_path}")
                return {}
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Screener timed out after 10 minutes")
            self._heartbeat(f"Screener timed out")
            return {}
        except Exception as e:
            logger.error(f"❌ Error running screener: {e}")
            self._heartbeat(f"Screener error: {e}")
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
            logger.info(f"🔗 Pair discovery mode: AUTO_SCREEN (timeframe: {analysis_timeframe})")
            self._heartbeat(f"Auto-screening for pairs (timeframe: {analysis_timeframe})")
            pairs = await self._get_or_refresh_screener_results(analysis_timeframe)
        else:
            logger.info(f"🔗 Pair discovery mode: STATIC")
            pairs = self.get_config_value('pairs', {})

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
                    pair_symbol=pair_symbol,
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
        pair_symbol: Optional[str] = None,
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

        # Build strategy metadata for exit logic and monitoring
        strategy_metadata = None
        if beta is not None and spread_mean is not None and spread_std is not None:
            z_exit = self.get_config_value('z_exit', 0.5)
            strategy_metadata = {
                "beta": float(beta),
                "spread_mean": float(spread_mean),
                "spread_std": float(spread_std),
                "z_score_at_entry": float(z_score),
                "pair_symbol": pair_symbol,
                "z_exit_threshold": float(z_exit),
            }

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
            # Add strategy UUID for traceability
            "strategy_uuid": self.strategy_uuid,
            "strategy_type": self.STRATEGY_TYPE,
            "strategy_name": self.STRATEGY_NAME,
            # Add strategy metadata for exit logic and monitoring
            "strategy_metadata": strategy_metadata,
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
        z_exit = self.get_config_value("z_exit", 0.5)

        return {
            "type": "z_score",
            "z_exit": z_exit,
            "description": f"Exit when z-score crosses {z_exit} threshold",
        }

    def get_monitoring_metadata(self) -> Dict[str, Any]:
        """
        Get spread-based monitoring metadata.

        Returns:
            Dict with z-score exit parameters for position monitor
        """
        z_exit = self.get_config_value("z_exit", 0.5)

        return {
            "type": "z_score",
            "z_exit": z_exit,
        }

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
            pair_candle: Current candle for pair symbol {timestamp, open, high, low, close}

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

            # Get max_spread_deviation setting (0 = disabled)
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

            # Cointegration analysis settings
            "lookback": {
                "type": "number",
                "default": 120,
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
            "use_soft_vol": {
                "type": "boolean",
                "default": False,
                "description": "Use soft volatility adjustment for cointegration",
            },

            # Risk management settings
            "max_spread_deviation": {
                "type": "float",
                "default": 3.0,
                "description": "Maximum z-score deviation before closing position",
            },
            "min_z_distance": {
                "type": "float",
                "default": 0.5,
                "description": "Minimum z-score distance to SL for signal validation",
            },
        }

