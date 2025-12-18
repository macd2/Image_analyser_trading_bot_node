"""
API endpoint for strategy-specific exit checks in simulator.
Called by Node.js auto-close route to check if a trade should exit based on strategy logic.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from trading_bot.strategies.factory import StrategyFactory
from trading_bot.config.settings import Config

logger = logging.getLogger(__name__)


class StrategyExitChecker:
    """Check strategy-specific exit conditions for simulator."""

    def __init__(self):
        self.config = Config.load()

    def check_exit(
        self,
        trade_id: str,
        strategy_name: str,
        candles: List[Dict[str, Any]],
        trade_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check if trade should exit using strategy.should_exit().

        Args:
            trade_id: Trade ID for logging
            strategy_name: Strategy name (e.g., "CointegrationSpreadTrader")
            candles: List of candles [{"timestamp": ms, "open": f, "high": f, "low": f, "close": f}, ...]
            trade_data: Trade info {"symbol": str, "side": str, "entry_price": f, "stop_loss": f, "take_profit": f, "strategy_metadata": dict}

        Returns:
            {"should_exit": bool, "exit_price": float, "exit_reason": str, "exit_timestamp": int, "current_price": float}
        """
        try:
            if not candles:
                return {
                    "should_exit": False,
                    "exit_price": None,
                    "exit_reason": None,
                    "exit_timestamp": None,
                    "current_price": None
                }

            # Get strategy class from factory registry
            from trading_bot.strategies import StrategyFactory as SF
            strategies = SF.get_available_strategies()

            if strategy_name not in strategies:
                logger.warning(f"Strategy not found: {strategy_name}. Available: {list(strategies.keys())}")
                return {
                    "should_exit": False,
                    "exit_price": None,
                    "exit_reason": None,
                    "exit_timestamp": None,
                    "current_price": None
                }

            # Instantiate strategy (use dummy instance_id since we only need should_exit method)
            strategy_class = strategies[strategy_name]
            strategy = strategy_class(
                config=self.config,
                instance_id="simulator",
                run_id=None,
                strategy_config={}
            )

            # Iterate through candles and check for exit
            for candle in candles:
                current_candle_dict = {
                    "timestamp": candle.get("timestamp"),
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "close": candle.get("close"),
                }

                # For spread-based strategies, pair_candle would be fetched here
                # For now, pass None and let strategy handle it
                pair_candle_dict = None

                # Call strategy.should_exit()
                exit_result = strategy.should_exit(
                    trade=trade_data,
                    current_candle=current_candle_dict,
                    pair_candle=pair_candle_dict,
                )

                # Check if should exit
                if exit_result.get("should_exit"):
                    exit_details = exit_result.get("exit_details", {})
                    reason = exit_details.get("reason", "strategy_exit")

                    return {
                        "should_exit": True,
                        "exit_price": current_candle_dict.get("close"),
                        "exit_reason": reason,
                        "exit_timestamp": current_candle_dict.get("timestamp"),
                        "current_price": current_candle_dict.get("close")
                    }

            # No exit condition met
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": candles[-1].get("close") if candles else None
            }

        except Exception as e:
            logger.error(f"Error checking strategy exit for trade {trade_id}: {e}", exc_info=True)
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": str(e)
            }


# Global instance
_checker = None


def get_checker() -> StrategyExitChecker:
    """Get or create the strategy exit checker."""
    global _checker
    if _checker is None:
        _checker = StrategyExitChecker()
    return _checker

