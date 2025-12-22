"""
NewListingStrategy - Price-based strategy for newly listed coins on Bybit.

Features:
- Monitors Bybit announcements for new derivative listings
- Enters long positions on newly listed pairs as early as possible
- Fixed $100 position sizing with 5% stop loss and 30% take profit
- Smart trailing stop mechanism to let winners run
- Duplicate prevention using recommendations history
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from trading_bot.config.settings_v2 import Config
from trading_bot.core.bybit_api_manager import BybitAPIManager
from trading_bot.core.error_logger import set_cycle_id, clear_cycle_id
from trading_bot.core.utils import normalize_symbol_for_bybit
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.db.client import get_connection, release_connection, query

logger = logging.getLogger(__name__)


class NewListingStrategy(BaseAnalysisModule):
    """
    Price-based strategy for trading newly listed coins on Bybit.
    
    Monitors announcements for new derivative listings and enters long positions
    as early as possible after trading begins.
    """

    # Strategy type identification
    STRATEGY_TYPE = "price_based"
    STRATEGY_NAME = "NewListingStrategy"
    STRATEGY_VERSION = "1.0"

    # Strategy configuration with hardcoded values for contract compliance
    DEFAULT_CONFIG = {
        "confidence": 0.75,  # Default confidence for new listing trades
        "position_size_multiplier": 1.0,  # Standard position sizing
        "fixed_position_size_usd": 100.0,  # Fixed $100 per trade
        "stop_loss_percent": 5.0,  # 5% below entry
        "take_profit_percent": 30.0,  # 30% above entry
        "max_candles_after_listing": 5,  # Enter within first 5 candles
        "candle_fetch_limit": 20,  # Fetch up to 20 candles to check entry window
        "announcement_lookback_hours": 28,  # Check announcements from last 28 hours
        "timeframe": "5m",  # Candle timeframe for analysis
        "locale": "en-US",  # Announcement language
    }

    def __init__(
        self,
        config: Config,
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        heartbeat_callback: Optional[Any] = None,
        testnet: bool = False,
    ):
        """Initialize NewListingStrategy."""
        super().__init__(
            config=config,
            instance_id=instance_id,
            run_id=run_id,
            strategy_config=strategy_config,
            heartbeat_callback=heartbeat_callback,
        )
        
        self.testnet = testnet
        self.api_manager = BybitAPIManager(config, use_testnet=testnet)
        self._cycle_count = 0

    async def run_analysis_cycle(
        self,
        symbols: List[str],
        timeframe: str,
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Run analysis cycle to find and analyze newly listed coins.

        Args:
            symbols: Ignored - strategy discovers symbols from announcements
            timeframe: Ignored - uses timeframe from config
            cycle_id: Cycle identifier

        Returns:
            List of recommendation dicts
        """
        set_cycle_id(cycle_id)
        self._cycle_count += 1

        # Get timeframe from config instead of parameter
        config_timeframe = self.get_config_value("timeframe", "5m")

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"🔄 NEW LISTING STRATEGY CYCLE #{self._cycle_count} [{cycle_id}]")
        self.logger.info(f"Timeframe: {config_timeframe}")
        self.logger.info(f"{'='*60}")

        recommendations: List[Dict[str, Any]] = []

        try:
            # Fetch recent announcements for new listings
            new_listings = await self._fetch_new_listings()

            if not new_listings:
                self.logger.info("No new listings found in announcements")
                return recommendations

            self.logger.info(f"Found {len(new_listings)} new listings")

            # Analyze all listings in parallel using asyncio.gather()
            analysis_tasks = [
                self._analyze_new_listing(listing, config_timeframe, cycle_id)
                for listing in new_listings
            ]

            results = await asyncio.gather(*analysis_tasks, return_exceptions=True)

            # Process results and handle exceptions
            for i, result in enumerate(results):
                if self._stop_requested:
                    break

                if isinstance(result, Exception):
                    symbol = new_listings[i].get('symbol', 'UNKNOWN')
                    self.logger.error(f"Error analyzing listing {symbol}: {result}")
                elif result is not None:
                    recommendations.append(result)  # type: ignore

            self.logger.info(f"Generated {len(recommendations)} recommendations")
            return recommendations

        except Exception as e:
            self.logger.error(f"Strategy cycle failed: {e}", exc_info=True)
            return recommendations
        finally:
            clear_cycle_id()

    async def _fetch_new_listings(self) -> List[Dict[str, Any]]:
        """Fetch new derivative listings from Bybit announcements."""
        try:
            locale = self.get_config_value("locale", "en-US")

            # Fetch announcements with type=new_crypto (limit 1000 to see actual length)
            response = self.api_manager.get_announcements(
                locale=locale,
                type="new_crypto",
                limit=100,
            )

            if response.get("retCode") != 0:
                self.logger.error(f"Failed to fetch announcements: {response.get('retMsg')}")
                return []

            announcements = response.get("result", {}).get("list", [])
            self.logger.info(f"Fetched {len(announcements)} total announcements")
            new_listings = []

            for ann in announcements:
                # Filter for derivatives tag
                tags = ann.get("tags", [])
                if "Derivatives" not in tags and "Futures" not in tags:
                    continue

                # Filter out pre-market announcements
                title = ann.get("title", "")
                if "Pre-Market" in title or "pre-market" in title or "Pre Market" in title:
                    continue

                # Extract symbol from title (e.g., "New Listing: XYZ (XYZUSDT)")
                symbol = self._extract_symbol_from_title(title)

                if symbol:
                    new_listings.append({
                        "symbol": symbol,
                        "title": title,
                        "announcement_time": ann.get("dateTimestamp", 0),
                        "tags": tags,
                    })

            return new_listings

        except Exception as e:
            self.logger.error(f"Error fetching announcements: {e}")
            return []

    def _extract_symbol_from_title(self, title: str) -> Optional[str]:
        """Extract trading symbol from announcement title."""
        # Look for pattern like "XYZUSDT" in titles like "New Listing : XYZUSDT Perpetual Contract..."
        import re
        match = re.search(r'([A-Z0-9]+USDT)', title)
        if match:
            return match.group(1)
        return None

    async def _analyze_new_listing(
        self,
        listing: Dict[str, Any],
        timeframe: str,
        cycle_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Analyze a new listing and generate recommendation if conditions met."""
        symbol = listing.get("symbol")
        
        # Check for duplicates
        if await self._is_duplicate(symbol):
            self.logger.info(f"Skipping {symbol} - already analyzed")
            return None

        # Verify symbol is tradable
        if not await self._verify_tradable(symbol):
            self.logger.info(f"Symbol {symbol} not yet tradable")
            return None

        # Get candle data
        candles = await self._get_candles(symbol, timeframe)
        if not candles or len(candles) == 0:
            self.logger.warning(f"No candle data for {symbol}")
            return None

        # Check if within first N candles
        max_candles = self.get_config_value("max_candles_after_listing", 5)
        if len(candles) > max_candles:
            self.logger.info(f"{symbol} - Too many candles ({len(candles)}) on {timeframe}")
            return None

        # Get current market price for entry
        entry_price = await self._get_current_price(symbol)
        if entry_price is None or entry_price <= 0:
            self.logger.warning(f"Could not get current price for {symbol}")
            return None

        # Calculate risk levels based on current market price
        stop_loss_percent = self.get_config_value("stop_loss_percent", 5.0)
        take_profit_percent = self.get_config_value("take_profit_percent", 30.0)
        stop_loss = entry_price * (1 - stop_loss_percent / 100)
        take_profit = entry_price * (1 + take_profit_percent / 100)

        # Get first candle for analysis metadata
        first_candle = candles[0]

        # Build recommendation
        return {
            "symbol": symbol,
            "recommendation": "BUY",
            "confidence": self.get_config_value("confidence", 0.75),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": (take_profit - entry_price) / (entry_price - stop_loss) if entry_price > stop_loss else 0,
            "setup_quality": 0.8,  # New listings have good setup quality
            "position_size_multiplier": self.get_config_value("position_size_multiplier", 1.0),
            "market_environment": 0.7,  # Neutral market environment
            "analysis": {
                "strategy": "new_listing",
                "listing_symbol": symbol,
                "entry_candle_index": 0,
                "candles_since_listing": len(candles),
                "first_candle_low": float(first_candle.get("low", 0)),
                "first_candle_high": float(first_candle.get("high", 0)),
                "announcement_title": listing.get("title"),
            },
            "chart_path": "",
            "timeframe": timeframe,
            "cycle_id": cycle_id,
        }

    async def _is_duplicate(self, symbol: str) -> bool:
        """Check if symbol was already analyzed."""
        try:
            conn = get_connection()
            try:
                # Query recommendations for this symbol and strategy
                rows = query(
                    conn,
                    """
                    SELECT id FROM recommendations 
                    WHERE symbol = ? AND strategy_name = ?
                    LIMIT 1
                    """,
                    (symbol, self.STRATEGY_NAME),
                )
                return len(rows) > 0
            finally:
                release_connection(conn)
        except Exception as e:
            self.logger.error(f"Error checking duplicates: {e}")
            return False

    async def _verify_tradable(self, symbol: str) -> bool:
        """Verify symbol is tradable on Bybit."""
        try:
            response = self.api_manager.get_instruments_info(symbol=symbol)
            if response.get("retCode") != 0:
                return False
            
            instruments = response.get("result", {}).get("list", [])
            if not instruments:
                return False
            
            # Check if trading is enabled
            status = instruments[0].get("status", "")
            return status == "Trading"
        except Exception as e:
            self.logger.error(f"Error verifying tradability: {e}")
            return False

    async def _get_candles(self, symbol: str, timeframe: str) -> List[Dict[str, Any]]:
        """Get recent candles for symbol."""
        try:
            # Map timeframe to Bybit format
            tf_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}
            bybit_tf = tf_map.get(timeframe, "60")

            # Get candle fetch limit from config
            candle_limit = self.get_config_value("candle_fetch_limit", 20)

            response = self.api_manager.get_kline(
                symbol=symbol,
                interval=bybit_tf,
                limit=candle_limit,
            )
            
            if response.get("retCode") != 0:
                return []
            
            klines = response.get("result", {}).get("list", [])
            candles = []
            
            for kline in klines:
                candles.append({
                    "timestamp": int(kline[0]),
                    "open": float(kline[1]),
                    "high": float(kline[2]),
                    "low": float(kline[3]),
                    "close": float(kline[4]),
                    "volume": float(kline[5]),
                })
            
            return list(reversed(candles))  # Oldest first
        except Exception as e:
            self.logger.error(f"Error fetching candles: {e}")
            return []

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """
        Fetch the current market price (last traded price) for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'RAVEUSDT')

        Returns:
            Current market price as float, or None if fetch fails
        """
        try:
            response = self.api_manager.get_tickers(symbol=symbol)

            if response.get("retCode") != 0:
                self.logger.warning(f"Failed to get current price for {symbol}: {response.get('retMsg')}")
                return None

            tickers = response.get("result", {}).get("list", [])
            if not tickers:
                self.logger.warning(f"No ticker data for {symbol}")
                return None

            last_price = float(tickers[0].get("lastPrice", 0))
            if last_price <= 0:
                self.logger.warning(f"Invalid price for {symbol}: {last_price}")
                return None

            return last_price
        except Exception as e:
            self.logger.error(f"Error fetching current price for {symbol}: {e}")
            return None

    def validate_signal(self, signal: Dict[str, Any]) -> bool:
        """Validate signal meets strategy requirements."""
        required_fields = ["entry_price", "stop_loss", "take_profit"]
        for field in required_fields:
            if field not in signal or signal[field] is None or signal[field] <= 0:
                return False
        
        # Validate stop loss is below entry
        if signal["stop_loss"] >= signal["entry_price"]:
            return False
        
        # Validate take profit is above entry
        if signal["take_profit"] <= signal["entry_price"]:
            return False
        
        return True

    def calculate_risk_metrics(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate risk metrics for the signal."""
        entry = signal.get("entry_price", 0)
        sl = signal.get("stop_loss", 0)
        tp = signal.get("take_profit", 0)
        
        if entry <= 0 or sl <= 0:
            return {"risk_per_unit": 0, "rr_ratio": 0}
        
        risk_per_unit = entry - sl
        profit_per_unit = tp - entry
        rr_ratio = profit_per_unit / risk_per_unit if risk_per_unit > 0 else 0
        
        return {
            "risk_per_unit": risk_per_unit,
            "rr_ratio": rr_ratio,
            "risk_percent": (risk_per_unit / entry) * 100,
        }

    async def should_exit(
        self,
        trade: Dict[str, Any],
        current_candle: Dict[str, Any],
        pair_candle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Stateless, tick-accurate exit decision for new listings.
        - Uses LIVE PRICE for all exit checks (via self._get_current_price)
        - Dynamic trailing stop + dynamic take-profit (TP = stop × (1 + buffer))
        - Phased logic: Breakeven → Impulse → Parabolic → Emergency
        - Fully compatible with your existing trade dict format.

        🔹 Trade dict must contain at least: {"entry_price": float}
        🔹 Optional: {"take_profit": float, "stop_loss": float}
        """
        # ────────────────────────────────────────
        # 1. Input validation & initialization
        # ────────────────────────────────────────
        entry_price = float(trade.get("entry_price", 0))
        if not entry_price:
            raise ValueError("Trade must include 'entry_price'")

        # Get symbol from trade dict
        symbol = trade.get("symbol")
        if not symbol:
            raise ValueError("Trade must include 'symbol'")

        # Strategy parameters (configurable via class attrs if desired)
        fee_buffer = 0.001          # 0.1% for fees
        initial_stop_pct = 0.08     # 8%
        breakeven_trigger = 0.12    # +12%
        impulse_body_ratio = 0.65
        impulse_buffer_pct = 0.015  # 1.5%
        parabolic_trail_pct = 0.03  # 3%
        emergency_dump_pct = 0.15   # 15%
        tp_buffer_pct = 0.12        # 12% above stop (Phase 1–2)
        tp_buffer_phase3 = 0.18     # 18% above stop (Phase 3, stronger momentum)

        # Fetch REAL-TIME price — your existing method
        try:
            live_price = await self._get_current_price(symbol)
        except Exception as e:
            # Fallback: use candle close (log in prod)
            live_price = current_candle.get("close")
            if not live_price:
                self.logger.warning(f"Could not get live price for {symbol}: {e}")
                return {
                    "should_exit": False,
                    "exit_details": {
                        "reason": "error",
                        "error": f"Could not fetch price data: {e}",
                    }
                }
        current_price = float(live_price)

        # ────────────────────────────────────────
        # 2. Reconstruct strategy state from trade metadata
        #    (stateless → store phase/stop/highest in trade["meta"])
        # ────────────────────────────────────────
        meta = trade.get("meta", {})
        phase = meta.get("phase", 1)
        stop = meta.get("stop", entry_price * (1 - initial_stop_pct))
        highest = meta.get("highest", entry_price)
        candles = meta.get("candles", [])

        # Append current candle for signal logic
        candles.append(current_candle)
        if len(candles) > 100:
            candles = candles[-50:]  # prevent memory bloat

        # Update highest
        highest = max(highest, current_candle["high"])

        # ────────────────────────────────────────
        # 3. Helper functions (embedded for statelessness)
        # ────────────────────────────────────────
        def _is_impulse_candle(c):
            rng = c["high"] - c["low"]
            if rng <= 0:
                return False
            body = abs(c["close"] - c["open"])
            return body / rng >= impulse_body_ratio and c["close"] > c["open"]

        def _is_parabolic(cs):
            if len(cs) < 3:
                return False
            c1, c2, c3 = cs[-3:]
            vol_expansion = (c3["high"] - c3["low"]) > 2 * (c2["high"] - c2["low"])
            strong_close = (c3["high"] - c3["close"]) / (c3["high"] - c3["low"]) > 0.35
            return vol_expansion or strong_close

        # ────────────────────────────────────────
        # 4. Phase & Stop Update Logic (same as your class)
        # ────────────────────────────────────────
        pnl = (current_price - entry_price) / entry_price

        # Phase 1 → Breakeven
        if phase == 1 and pnl >= breakeven_trigger:
            stop = entry_price * (1 + fee_buffer)
            phase = 2

        # Phase 2 → Impulse trailing
        if phase >= 2 and _is_impulse_candle(current_candle):
            impulse_low = current_candle["low"] * (1 - impulse_buffer_pct)
            if impulse_low > stop:
                stop = impulse_low

        # Phase 2 → Phase 3 (parabolic)
        if phase == 2 and _is_parabolic(candles):
            phase = 3

        # Phase 3 → Tighter trailing
        if phase == 3:
            tight_stop = highest * (1 - parabolic_trail_pct)
            if tight_stop > stop:
                stop = tight_stop

        # ────────────────────────────────────────
        # 5. Exit Checks — ALL USING LIVE PRICE
        # ────────────────────────────────────────

        # 🔴 Emergency Dump (after +40% gain)
        if (highest - entry_price) / entry_price > 0.4:
            drop_from_high = (highest - current_price) / highest
            if drop_from_high >= emergency_dump_pct:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "emergency_dump",
                        "exit_price": current_price,
                        "loss_percent": ((current_price - entry_price) / entry_price) * 100,
                        "pnl_at_peak": ((highest - entry_price) / entry_price) * 100,
                    },
                    # Update meta for logging/backtesting
                    "updated_meta": {"phase": phase, "stop": stop, "highest": highest, "candles": candles},
                }

        # 🔴 Stop Hit (live price ≤ stop)
        if current_price <= stop:
            return {
                "should_exit": True,
                "exit_details": {
                    "reason": "trailing_stop_hit",
                    "exit_price": current_price,
                    "loss_percent": ((current_price - entry_price) / entry_price) * 100,
                },
                "updated_meta": {"phase": phase, "stop": stop, "highest": highest, "candles": candles},
            }

        # 🟢 Dynamic Take Profit (active from Phase 2+)
        dynamic_tp = None
        if phase >= 2:
            buffer = tp_buffer_phase3 if phase == 3 else tp_buffer_pct
            dynamic_tp = stop * (1 + buffer)
            # Optional: cap at 3× entry to avoid absurd values
            dynamic_tp = min(dynamic_tp, entry_price * 5.0)

        # Respect user-defined TP only if *tighter* than dynamic TP
        static_tp = trade.get("take_profit")
        effective_tp = None
        if dynamic_tp and static_tp:
            effective_tp = max(static_tp, dynamic_tp)  # use looser (higher) TP
        elif dynamic_tp:
            effective_tp = dynamic_tp
        elif static_tp:
            effective_tp = static_tp

        # TP Hit
        if effective_tp and current_price >= effective_tp:
            return {
                "should_exit": True,
                "exit_details": {
                    "reason": "take_profit_hit",
                    "exit_price": current_price,
                    "profit_percent": ((current_price - entry_price) / entry_price) * 100,
                    "tp_level": effective_tp,
                    "tp_type": "dynamic" if dynamic_tp else "static",
                },
                "updated_meta": {"phase": phase, "stop": stop, "highest": highest, "candles": candles},
            }

        # 🔴 Static Stop Loss (fallback, if tighter than trailing stop)
        static_sl = trade.get("stop_loss")
        if static_sl and current_price <= static_sl and static_sl < stop:
            return {
                "should_exit": True,
                "exit_details": {
                    "reason": "static_stop_hit",
                    "exit_price": current_price,
                    "loss_percent": ((current_price - entry_price) / entry_price) * 100,
                },
                "updated_meta": {"phase": phase, "stop": stop, "highest": highest, "candles": candles},
            }

        # ✅ Hold
        return {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "current_price": current_price,
                "stop_level": stop,
                "phase": phase,
                "highest_seen": highest,
                "breakeven_achieved": phase >= 2,
                "dynamic_tp": dynamic_tp,
                "tp_level": effective_tp, # effective tp level
            },
            "updated_meta": {"phase": phase, "stop": stop, "highest": highest, "candles": candles},
        }

    def get_exit_condition(self) -> Dict[str, Any]:
        """Get strategy-specific exit condition metadata."""
        return {
            "type": "price_level",
            "trailing_stop_enabled": True,
            "trailing_stop_config": {
                "breakeven_at_profit_percent": 12,
                "trail_by_percent": 3,
                "trail_by_percent_at_profit": 3,
            },
        }

    def get_monitoring_metadata(self) -> Dict[str, Any]:
        """Get metadata for position monitoring."""
        return {
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "trailing_stop_enabled": True,
        }

    @classmethod
    def get_required_settings(cls) -> Dict[str, Any]:
        """Get price-based strategy settings schema."""
        return {
            "enable_trailing_stop": {
                "type": "bool",
                "default": True,
                "description": "Enable trailing stop mechanism",
            },
            "trailing_stop_config": {
                "type": "dict",
                "default": {
                    "breakeven_at_profit_percent": 10,
                    "trail_by_percent": 10,
                    "trail_by_percent_at_profit": 20,
                },
                "description": "Trailing stop configuration parameters",
            },
        }

