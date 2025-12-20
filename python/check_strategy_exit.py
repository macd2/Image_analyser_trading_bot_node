#!/usr/bin/env python3
"""
Check strategy-specific exit conditions for simulator.
Called by Node.js auto-close route via spawn.

Usage:
  python3 check_strategy_exit.py <trade_id> <strategy_name> <candles_json> <trade_data_json>

Output: JSON with {"should_exit": bool, "exit_price": float, "exit_reason": str, ...}
"""

import sys
import json
import logging
from typing import Dict, Any, List

# Setup logging to stderr
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger(__name__)

def check_strategy_exit(
    trade_id: str,
    strategy_name: str,
    candles: List[Dict[str, Any]],
    trade_data: Dict[str, Any],
    pair_candles: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Check if trade should exit using strategy.should_exit().

    IMPORTANT: This function ONLY handles non-price-based strategies.
    Price-based strategies should use TP/SL logic in the simulator.

    Args:
        trade_id: Trade ID
        strategy_name: Name of the strategy
        candles: List of primary symbol candles
        trade_data: Trade data dict
        pair_candles: Optional list of pair symbol candles for spread-based strategies
    """
    try:
        # Validate inputs
        if not trade_id:
            logger.error("ERROR: trade_id is required")
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": "trade_id is required"
            }

        if not strategy_name:
            logger.error(f"ERROR: strategy_name is required for trade {trade_id}")
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": "strategy_name is required"
            }

        if not candles:
            logger.warning(f"WARNING: No candles provided for trade {trade_id}")
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None
            }

        # Import strategy factory
        from trading_bot.strategies import StrategyFactory
        from trading_bot.config.settings_v2 import ConfigV2

        # Get strategy class from factory registry
        strategies = StrategyFactory.get_available_strategies()

        if strategy_name not in strategies:
            logger.error(f"ERROR: Strategy not found: {strategy_name}. Available: {list(strategies.keys())}")
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": f"Strategy not found: {strategy_name}"
            }

        # Instantiate strategy
        strategy_class = strategies[strategy_name]

        # For simulator, we need a minimal config - try to load from first available instance
        # or create a minimal config
        try:
            from trading_bot.db.client import get_connection, query_one, release_connection
            conn = get_connection()
            instance = query_one(conn, "SELECT id FROM instances LIMIT 1")
            release_connection(conn)
            instance_id = instance.get('id') if instance else 'simulator'
        except Exception:
            instance_id = 'simulator'

        try:
            config = ConfigV2.load(instance_id=instance_id)
        except Exception as e:
            logger.error(f"ERROR: Failed to load config for instance {instance_id}: {e}")
            # Create a minimal config for simulator
            from trading_bot.config.settings_v2 import (
                PathsConfig, OpenAIConfig, BybitConfig, TradingConfig, FileManagementConfig
            )
            config = ConfigV2(
                paths=PathsConfig(database="data/trading.db", charts="data/charts", logs="logs", session_file="data/"),
                openai=OpenAIConfig(api_key="", model="gpt-4", max_tokens=2000, temperature=0.7),
                bybit=BybitConfig(use_testnet=False, recv_window=5000, max_retries=3),
                trading=TradingConfig(
                    paper_trading=True, auto_approve_trades=False, min_confidence_threshold=0.5,
                    min_rr=1.0, risk_percentage=1.0, max_loss_usd=100.0, leverage=1,
                    max_concurrent_trades=5, timeframe="1h", enable_position_tightening=False,
                    enable_sl_tightening=False
                ),
                file_management=FileManagementConfig(enable_backup=False)
            )

        try:
            strategy = strategy_class(
                config=config,
                instance_id=instance_id,
                run_id=None,
                strategy_config={}
            )
        except Exception as e:
            logger.error(f"ERROR: Failed to instantiate strategy {strategy_name} for trade {trade_id}: {e}", exc_info=True)
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": f"Failed to instantiate strategy: {e}"
            }

        # Iterate through candles and check for exit
        # NOTE: For spread-based strategies, pair_candles are provided from the database cache
        # If not available, the strategy's should_exit() method can fetch from live API as fallback
        for i, candle in enumerate(candles):
            try:
                current_candle_dict = {
                    "timestamp": candle.get("timestamp"),
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "close": candle.get("close"),
                }

                # Find corresponding pair candle by timestamp
                pair_candle_dict = None
                if pair_candles:
                    for pair_candle in pair_candles:
                        if pair_candle.get("timestamp") == current_candle_dict.get("timestamp"):
                            pair_candle_dict = {
                                "timestamp": pair_candle.get("timestamp"),
                                "open": pair_candle.get("open"),
                                "high": pair_candle.get("high"),
                                "low": pair_candle.get("low"),
                                "close": pair_candle.get("close"),
                            }
                            break

                # Call strategy.should_exit()
                # For spread-based strategies, pair_candle is provided from database cache
                # If not available, strategy can fetch from live API as fallback
                exit_result = strategy.should_exit(
                    trade=trade_data,
                    current_candle=current_candle_dict,
                    pair_candle=pair_candle_dict,  # Provided from database cache if available
                )

                # Validate exit_result
                if not isinstance(exit_result, dict):
                    logger.error(f"ERROR: strategy.should_exit() returned non-dict for trade {trade_id}: {type(exit_result)}")
                    continue

                # Check if should exit
                if exit_result.get("should_exit"):
                    exit_details = exit_result.get("exit_details", {})
                    reason = exit_details.get("reason", "strategy_exit")

                    logger.info(f"Strategy exit triggered for trade {trade_id} at candle {i}: {reason}")
                    return {
                        "should_exit": True,
                        "exit_price": current_candle_dict.get("close"),
                        "exit_reason": reason,
                        "exit_timestamp": current_candle_dict.get("timestamp"),
                        "current_price": current_candle_dict.get("close")
                    }
            except Exception as e:
                logger.error(f"ERROR: Exception in candle {i} for trade {trade_id}: {e}", exc_info=True)
                continue

        # No exit condition met
        logger.info(f"No exit condition met for trade {trade_id} after checking {len(candles)} candles")
        return {
            "should_exit": False,
            "exit_price": None,
            "exit_reason": None,
            "exit_timestamp": None,
            "current_price": candles[-1].get("close") if candles else None
        }

    except Exception as e:
        logger.error(f"ERROR: Unexpected error checking strategy exit for trade {trade_id}: {e}", exc_info=True)
        return {
            "should_exit": False,
            "exit_price": None,
            "exit_reason": None,
            "exit_timestamp": None,
            "current_price": None,
            "error": str(e)
        }


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Usage: check_strategy_exit.py <trade_id> <strategy_name> <candles_json> <trade_data_json> [pair_candles_json]"}))
        sys.exit(1)

    trade_id = sys.argv[1]
    strategy_name = sys.argv[2]
    candles_json = sys.argv[3]
    trade_data_json = sys.argv[4]
    pair_candles_json = sys.argv[5] if len(sys.argv) > 5 else "[]"

    try:
        candles = json.loads(candles_json)
        trade_data = json.loads(trade_data_json)
        pair_candles = json.loads(pair_candles_json)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    result = check_strategy_exit(trade_id, strategy_name, candles, trade_data, pair_candles)
    print(json.dumps(result))

