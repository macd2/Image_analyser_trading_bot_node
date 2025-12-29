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
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Setup logging to stderr
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger(__name__)


def log_error_to_db(trade_id: str, symbol: str, event: str, message: str, context: Optional[Dict[str, Any]] = None) -> None:
    """
    Log error to centralized error_logs table using the centralized database layer.

    Args:
        trade_id: Trade ID for correlation
        symbol: Symbol being traded
        event: Event type (e.g., 'strategy_exit_failed', 'strategy_not_found')
        message: Error message
        context: Optional context dict with additional debugging info
    """
    try:
        from trading_bot.db.client import get_connection, execute, release_connection

        conn = None
        try:
            conn = get_connection(timeout_seconds=5.0)

            log_id = str(uuid.uuid4())[:12]
            timestamp = datetime.now(timezone.utc).isoformat()
            context_json = json.dumps(context) if context else None

            execute(conn, """
                INSERT INTO error_logs (
                    id, timestamp, level, trade_id, symbol,
                    component, event, message, context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_id,
                timestamp,
                'ERROR',
                trade_id,
                symbol,
                'check_strategy_exit',
                event,
                message,
                context_json,
            ), auto_commit=True)

            # Log to stderr for visibility
            print(f"[check_strategy_exit] ✅ Logged error to DB: {event} for trade {trade_id}", file=sys.stderr)

        finally:
            if conn:
                release_connection(conn)

    except Exception as e:
        # Fallback: log to stderr if database logging fails
        print(f"[check_strategy_exit] ⚠️  Failed to log error to DB: {e}", file=sys.stderr)
        print(f"[check_strategy_exit] Original error: {event} - {message}", file=sys.stderr)

def check_strategy_exit(
    trade_id: str,
    strategy_name: str,
    candles: List[Dict[str, Any]],
    trade_data: Dict[str, Any],
    pair_candles: Optional[List[Dict[str, Any]]] = None
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
            error_msg = "trade_id is required"
            logger.error(f"ERROR: {error_msg}")
            log_error_to_db("unknown", "unknown", "missing_trade_id", error_msg)
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": error_msg
            }

        if not strategy_name:
            error_msg = "strategy_name is required"
            logger.error(f"ERROR: {error_msg} for trade {trade_id}")
            log_error_to_db(trade_id, "unknown", "missing_strategy_name", error_msg)
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": error_msg
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
            error_msg = f"Strategy not found: {strategy_name}"
            logger.error(f"ERROR: {error_msg}. Available: {list(strategies.keys())}")
            log_error_to_db(trade_id, "unknown", "strategy_not_found", error_msg, {
                "strategy_name": strategy_name,
                "available_strategies": list(strategies.keys())
            })
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": error_msg
            }

        # Instantiate strategy
        strategy_class = strategies[strategy_name]

        # For simulator, we need a minimal config - try to load from first available instance
        # or create a minimal config
        try:
            from trading_bot.db.client import get_connection, query_one, release_connection
            conn = get_connection(timeout_seconds=5.0)
            instance = query_one(conn, "SELECT id FROM instances LIMIT 1")
            release_connection(conn)
            instance_id = instance.get('id') if instance else 'simulator'
        except Exception as e:
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
            error_msg = f"Failed to instantiate strategy: {e}"
            logger.error(f"ERROR: {error_msg} for trade {trade_id}", exc_info=True)
            log_error_to_db(trade_id, trade_data.get("symbol", "unknown"), "strategy_instantiation_failed", error_msg, {
                "strategy_name": strategy_name,
                "exception_type": type(e).__name__
            })
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": error_msg
            }

        # Iterate through candles and check for exit
        # NOTE: For spread-based strategies, pair_candles are provided from the database cache
        # If not available, the strategy's should_exit() method can fetch from live API as fallback
        last_exit_result = None  # Track last exit_result for stop/TP syncing when holding

        # Determine position side (LONG or SHORT)
        # trade_data["side"] can be 'Buy' (LONG) or 'Sell' (SHORT)
        is_long = trade_data.get("side", "Buy").lower() in ["buy", "long"]

        # Get strategy type to determine exit logic
        # CRITICAL: Spread-based trades should ONLY use strategy.should_exit() for exits
        # Price-based trades can use both strategy.should_exit() AND price-level SL/TP checks
        strategy_type = trade_data.get("strategy_type")
        is_spread_based = strategy_type == "spread_based"

        # Track simulated stops/TPs as they change each candle
        simulated_stops = {
            "stop_loss": trade_data.get("stop_loss"),
            "take_profit": trade_data.get("take_profit")
        }
        stop_updates = []  # Audit trail of all stop/TP changes

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

                # Track last exit_result for stop/TP syncing when holding position
                last_exit_result = exit_result

                # Update simulated stops if strategy provides new ones
                exit_details = exit_result.get("exit_details", {})

                if "stop_level" in exit_details:
                    new_sl = exit_details["stop_level"]
                    if simulated_stops["stop_loss"] and abs(new_sl - simulated_stops["stop_loss"]) > 0.0001:
                        stop_updates.append({
                            "candle_index": i,
                            "timestamp": current_candle_dict.get("timestamp"),
                            "type": "stop_loss",
                            "old": simulated_stops["stop_loss"],
                            "new": new_sl
                        })
                        simulated_stops["stop_loss"] = new_sl

                if "tp_level" in exit_details:
                    new_tp = exit_details["tp_level"]
                    if simulated_stops["take_profit"] and abs(new_tp - simulated_stops["take_profit"]) > 0.0001:
                        stop_updates.append({
                            "candle_index": i,
                            "timestamp": current_candle_dict.get("timestamp"),
                            "type": "take_profit",
                            "old": simulated_stops["take_profit"],
                            "new": new_tp
                        })
                        simulated_stops["take_profit"] = new_tp

                # CRITICAL FIX: For spread-based trades, SKIP price-level SL/TP checks
                # Spread-based trades should ONLY exit via strategy.should_exit() (z-score logic)
                # Price-level SL/TP checks are ONLY for price-based strategies
                if is_spread_based:
                    # For spread-based trades, ONLY check strategy.should_exit() result
                    # Do NOT check if candle high/low touched SL/TP levels
                    # The strategy.should_exit() already checked z-score exit conditions above
                    pass  # Skip price-level SL/TP checks
                else:
                    # For price-based trades, check if SL/TP was hit using CURRENT simulated stops
                    # This respects the dynamic stop/TP changes from the strategy
                    candle_high = current_candle_dict.get("high", 0)
                    candle_low = current_candle_dict.get("low", 0)

                    if is_long:
                        # Long position: SL hit if low <= stopLoss, TP hit if high >= takeProfit
                        sl_hit = simulated_stops["stop_loss"] and candle_low <= simulated_stops["stop_loss"]
                        tp_hit = simulated_stops["take_profit"] and candle_high >= simulated_stops["take_profit"]

                        if sl_hit and tp_hit:
                            # Both hit in same candle - determine which first by checking open price
                            if abs(current_candle_dict.get("open", 0) - simulated_stops["stop_loss"]) < abs(current_candle_dict.get("open", 0) - simulated_stops["take_profit"]):
                                return {
                                    "should_exit": True,
                                    "exit_price": simulated_stops["stop_loss"],
                                    "exit_reason": "sl_hit",
                                    "exit_timestamp": current_candle_dict.get("timestamp"),
                                    "current_price": current_candle_dict.get("close"),
                                    "stop_updates": stop_updates,
                                    "final_stops": simulated_stops
                                }
                            else:
                                return {
                                    "should_exit": True,
                                    "exit_price": simulated_stops["take_profit"],
                                    "exit_reason": "tp_hit",
                                    "exit_timestamp": current_candle_dict.get("timestamp"),
                                    "current_price": current_candle_dict.get("close"),
                                    "stop_updates": stop_updates,
                                    "final_stops": simulated_stops
                                }
                        elif sl_hit:
                            return {
                                "should_exit": True,
                                "exit_price": simulated_stops["stop_loss"],
                                "exit_reason": "sl_hit",
                                "exit_timestamp": current_candle_dict.get("timestamp"),
                                "current_price": current_candle_dict.get("close"),
                                "stop_updates": stop_updates,
                                "final_stops": simulated_stops
                            }
                        elif tp_hit:
                            return {
                                "should_exit": True,
                                "exit_price": simulated_stops["take_profit"],
                                "exit_reason": "tp_hit",
                                "exit_timestamp": current_candle_dict.get("timestamp"),
                                "current_price": current_candle_dict.get("close"),
                                "stop_updates": stop_updates,
                                "final_stops": simulated_stops
                            }
                    else:
                        # Short position: SL hit if high >= stopLoss, TP hit if low <= takeProfit
                        sl_hit = simulated_stops["stop_loss"] and candle_high >= simulated_stops["stop_loss"]
                        tp_hit = simulated_stops["take_profit"] and candle_low <= simulated_stops["take_profit"]

                        if sl_hit and tp_hit:
                            # Both hit in same candle - determine which first
                            if abs(current_candle_dict.get("open", 0) - simulated_stops["stop_loss"]) < abs(current_candle_dict.get("open", 0) - simulated_stops["take_profit"]):
                                return {
                                    "should_exit": True,
                                    "exit_price": simulated_stops["stop_loss"],
                                    "exit_reason": "sl_hit",
                                    "exit_timestamp": current_candle_dict.get("timestamp"),
                                    "current_price": current_candle_dict.get("close"),
                                    "stop_updates": stop_updates,
                                    "final_stops": simulated_stops
                                }
                            else:
                                return {
                                    "should_exit": True,
                                    "exit_price": simulated_stops["take_profit"],
                                    "exit_reason": "tp_hit",
                                    "exit_timestamp": current_candle_dict.get("timestamp"),
                                    "current_price": current_candle_dict.get("close"),
                                    "stop_updates": stop_updates,
                                    "final_stops": simulated_stops
                                }
                        elif sl_hit:
                            return {
                                "should_exit": True,
                                "exit_price": simulated_stops["stop_loss"],
                                "exit_reason": "sl_hit",
                                "exit_timestamp": current_candle_dict.get("timestamp"),
                                "current_price": current_candle_dict.get("close"),
                                "stop_updates": stop_updates,
                                "final_stops": simulated_stops
                            }
                        elif tp_hit:
                            return {
                                "should_exit": True,
                                "exit_price": simulated_stops["take_profit"],
                                "exit_reason": "tp_hit",
                                "exit_timestamp": current_candle_dict.get("timestamp"),
                                "current_price": current_candle_dict.get("close"),
                                "stop_updates": stop_updates,
                                "final_stops": simulated_stops
                            }

                # Check if should exit
                if exit_result.get("should_exit"):
                    reason = exit_details.get("reason", "strategy_exit")

                    logger.info(f"Strategy exit triggered for trade {trade_id} at candle {i}: {reason}")

                    # Build response with optional strategy-calculated stops
                    response = {
                        "should_exit": True,
                        "exit_price": current_candle_dict.get("close"),
                        "exit_reason": reason,
                        "exit_timestamp": current_candle_dict.get("timestamp"),
                        "current_price": current_candle_dict.get("close"),
                        "stop_updates": stop_updates,
                        "final_stops": simulated_stops
                    }

                    # Include strategy-calculated stops if provided (for consistency with PositionMonitor)
                    if "stop_level" in exit_details:
                        response["stop_level"] = exit_details.get("stop_level")
                    if "tp_level" in exit_details:
                        response["tp_level"] = exit_details.get("tp_level")

                    return response
            except Exception as e:
                error_msg = f"Exception in candle {i}: {e}"
                logger.error(f"ERROR: {error_msg} for trade {trade_id}", exc_info=True)
                log_error_to_db(trade_id, trade_data.get("symbol", "unknown"), "candle_processing_error", error_msg, {
                    "candle_index": i,
                    "exception_type": type(e).__name__
                })
                continue

        # No exit condition met
        logger.info(f"No exit condition met for trade {trade_id} after checking {len(candles)} candles")

        # Return response with optional strategy-calculated stops from last candle check
        # This allows strategies to provide dynamic stop/TP levels even when holding
        response = {
            "should_exit": False,
            "exit_price": None,
            "exit_reason": None,
            "exit_timestamp": None,
            "current_price": candles[-1].get("close") if candles else None,
            "stop_updates": stop_updates,  # Include audit trail of all stop/TP changes
            "final_stops": simulated_stops  # Include final simulated stops
        }

        # If we have a last exit_result from the loop, include strategy-calculated stops
        # This provides consistency with PositionMonitor's stop/TP syncing
        if last_exit_result:
            exit_details = last_exit_result.get("exit_details", {})
            if "stop_level" in exit_details:
                response["stop_level"] = exit_details.get("stop_level")
            if "tp_level" in exit_details:
                response["tp_level"] = exit_details.get("tp_level")

        return response

    except Exception as e:
        error_msg = f"Unexpected error checking strategy exit: {e}"
        logger.error(f"ERROR: {error_msg} for trade {trade_id}", exc_info=True)
        log_error_to_db(trade_id, trade_data.get("symbol", "unknown") if 'trade_data' in locals() else "unknown",
                       "strategy_exit_check_failed", error_msg, {
                           "exception_type": type(e).__name__
                       })
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

