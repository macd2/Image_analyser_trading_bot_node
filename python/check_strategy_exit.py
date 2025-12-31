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
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

# Setup logging to stderr
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger(__name__)


def validate_input_parameters(
    trade_id: str,
    strategy_name: str,
    candles: Any,
    trade_data: Any,
    pair_candles: Any
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    COMPREHENSIVE VALIDATION: Check ALL input parameters and values.

    Returns:
        Tuple of (is_valid, error_message, error_context)
        - is_valid: True if all validations pass
        - error_message: Error message if validation fails
        - error_context: Additional context for error logging
    """

    # ============================================================================
    # STEP 1: Validate command-line arguments
    # ============================================================================

    if not trade_id or not isinstance(trade_id, str) or trade_id.strip() == "":
        return False, "trade_id is required and must be a non-empty string", None

    if not strategy_name or not isinstance(strategy_name, str) or strategy_name.strip() == "":
        return False, "strategy_name is required and must be a non-empty string", None

    # ============================================================================
    # STEP 2: Validate candles parameter
    # ============================================================================

    if candles is None:
        return False, "candles parameter is required (cannot be None)", {
            "trade_id": trade_id,
            "strategy_name": strategy_name
        }

    if not isinstance(candles, list):
        return False, f"candles must be a list, got {type(candles).__name__}", {
            "trade_id": trade_id,
            "strategy_name": strategy_name,
            "candles_type": type(candles).__name__
        }

    if len(candles) == 0:
        return False, "candles list is empty - need at least 1 candle for exit check", {
            "trade_id": trade_id,
            "strategy_name": strategy_name
        }

    # Validate each candle has required fields
    required_candle_fields = ["timestamp", "open", "high", "low", "close"]
    for i, candle in enumerate(candles):
        if not isinstance(candle, dict):
            return False, f"candle at index {i} is not a dict, got {type(candle).__name__}", {
                "trade_id": trade_id,
                "candle_index": i,
                "candle_type": type(candle).__name__
            }

        for field in required_candle_fields:
            if field not in candle:
                return False, f"candle at index {i} missing required field '{field}'", {
                    "trade_id": trade_id,
                    "candle_index": i,
                    "missing_field": field,
                    "candle_keys": list(candle.keys())
                }

            value = candle[field]
            if value is None:
                return False, f"candle at index {i} has None value for field '{field}'", {
                    "trade_id": trade_id,
                    "candle_index": i,
                    "field": field
                }

            # For numeric fields (open, high, low, close), validate they are numbers
            if field in ["open", "high", "low", "close"]:
                if not isinstance(value, (int, float)):
                    return False, f"candle at index {i} field '{field}' must be numeric, got {type(value).__name__}", {
                        "trade_id": trade_id,
                        "candle_index": i,
                        "field": field,
                        "value_type": type(value).__name__
                    }

                if value < 0:
                    return False, f"candle at index {i} field '{field}' cannot be negative (value: {value})", {
                        "trade_id": trade_id,
                        "candle_index": i,
                        "field": field,
                        "value": value
                    }

    # ============================================================================
    # STEP 3: Validate trade_data parameter
    # ============================================================================

    if trade_data is None:
        return False, "trade_data parameter is required (cannot be None)", {
            "trade_id": trade_id,
            "strategy_name": strategy_name
        }

    if not isinstance(trade_data, dict):
        return False, f"trade_data must be a dict, got {type(trade_data).__name__}", {
            "trade_id": trade_id,
            "strategy_name": strategy_name,
            "trade_data_type": type(trade_data).__name__
        }

    # ============================================================================
    # STEP 4: Validate REQUIRED trade_data fields
    # ============================================================================

    required_trade_fields = ["symbol", "strategy_type", "side", "filled_at"]
    for field in required_trade_fields:
        if field not in trade_data:
            return False, f"trade_data missing required field '{field}'", {
                "trade_id": trade_id,
                "strategy_name": strategy_name,
                "missing_field": field,
                "trade_data_keys": list(trade_data.keys())
            }

        value = trade_data[field]
        if value is None:
            return False, f"trade_data field '{field}' cannot be None", {
                "trade_id": trade_id,
                "strategy_name": strategy_name,
                "field": field
            }

        if not isinstance(value, str) or value.strip() == "":
            return False, f"trade_data field '{field}' must be a non-empty string, got {type(value).__name__}", {
                "trade_id": trade_id,
                "strategy_name": strategy_name,
                "field": field,
                "value_type": type(value).__name__
            }

    # Validate symbol
    symbol = trade_data.get("symbol")
    if not symbol or not isinstance(symbol, str) or symbol.strip() == "":
        return False, "symbol must be a non-empty string", {
            "trade_id": trade_id,
            "strategy_name": strategy_name
        }

    # Validate strategy_type
    strategy_type = trade_data.get("strategy_type")
    valid_strategy_types = ["price_based", "spread_based"]
    if strategy_type not in valid_strategy_types:
        return False, f"strategy_type must be one of {valid_strategy_types}, got '{strategy_type}'", {
            "trade_id": trade_id,
            "symbol": symbol,
            "strategy_type": strategy_type,
            "valid_types": valid_strategy_types
        }

    # Validate side
    side = trade_data.get("side")
    valid_sides = ["Buy", "Sell", "buy", "sell", "LONG", "SHORT", "long", "short"]
    if side not in valid_sides:
        return False, f"side must be one of {valid_sides}, got '{side}'", {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "valid_sides": valid_sides
        }

    # Validate filled_at is a valid timestamp
    filled_at = trade_data.get("filled_at")
    try:
        if isinstance(filled_at, str):
            filled_at_str = filled_at.replace("+00", "Z").replace(" ", "T")
            if "T" not in filled_at_str:
                filled_at_str = filled_at_str.replace(" ", "T")
            datetime.fromisoformat(filled_at_str.replace("Z", "+00:00"))
        elif isinstance(filled_at, (int, float)):
            if filled_at <= 0:
                return False, f"filled_at timestamp must be positive, got {filled_at}", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "filled_at": filled_at
                }
        else:
            return False, f"filled_at must be string or numeric timestamp, got {type(filled_at).__name__}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "filled_at_type": type(filled_at).__name__
            }
    except (ValueError, AttributeError) as e:
        return False, f"filled_at is not a valid timestamp: {e}", {
            "trade_id": trade_id,
            "symbol": symbol,
            "filled_at": str(filled_at),
            "error": str(e)
        }

    # ============================================================================
    # STEP 5: Validate CONDITIONAL trade_data fields based on strategy_type
    # ============================================================================

    if strategy_type == "price_based":
        # Price-based strategies REQUIRE stop_loss and take_profit
        stop_loss = trade_data.get("stop_loss")
        take_profit = trade_data.get("take_profit")

        if stop_loss is None:
            return False, "stop_loss is required for price_based strategy", {
                "trade_id": trade_id,
                "symbol": symbol,
                "strategy_type": strategy_type
            }

        if take_profit is None:
            return False, "take_profit is required for price_based strategy", {
                "trade_id": trade_id,
                "symbol": symbol,
                "strategy_type": strategy_type
            }

        if not isinstance(stop_loss, (int, float)):
            return False, f"stop_loss must be numeric, got {type(stop_loss).__name__}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "stop_loss_type": type(stop_loss).__name__
            }

        if not isinstance(take_profit, (int, float)):
            return False, f"take_profit must be numeric, got {type(take_profit).__name__}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "take_profit_type": type(take_profit).__name__
            }

        if stop_loss <= 0:
            return False, f"stop_loss must be positive, got {stop_loss}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "stop_loss": stop_loss
            }

        if take_profit <= 0:
            return False, f"take_profit must be positive, got {take_profit}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "take_profit": take_profit
            }

    elif strategy_type == "spread_based":
        # Spread-based strategies REQUIRE strategy_metadata with specific fields
        strategy_metadata = trade_data.get("strategy_metadata")

        if strategy_metadata is None:
            return False, "strategy_metadata is required for spread_based strategy", {
                "trade_id": trade_id,
                "symbol": symbol,
                "strategy_type": strategy_type
            }

        # Parse if it's a JSON string
        if isinstance(strategy_metadata, str):
            try:
                strategy_metadata = json.loads(strategy_metadata)
            except json.JSONDecodeError as e:
                return False, f"strategy_metadata is not valid JSON: {e}", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "strategy_metadata": strategy_metadata[:100] if len(strategy_metadata) > 100 else strategy_metadata
                }

        if not isinstance(strategy_metadata, dict):
            return False, f"strategy_metadata must be a dict, got {type(strategy_metadata).__name__}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "strategy_metadata_type": type(strategy_metadata).__name__
            }

        # Required fields in strategy_metadata for spread-based
        required_metadata_fields = ["beta", "spread_mean", "spread_std", "z_exit_threshold", "pair_symbol", "price_y_at_entry", "max_spread_deviation"]
        for field in required_metadata_fields:
            if field not in strategy_metadata:
                return False, f"strategy_metadata missing required field '{field}'", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "missing_field": field,
                    "metadata_keys": list(strategy_metadata.keys())
                }

            value = strategy_metadata[field]
            if value is None:
                return False, f"strategy_metadata field '{field}' cannot be None", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "field": field
                }

            # Validate numeric fields
            if field in ["beta", "spread_mean", "spread_std", "z_exit_threshold", "price_y_at_entry", "max_spread_deviation"]:
                if not isinstance(value, (int, float)):
                    return False, f"strategy_metadata field '{field}' must be numeric, got {type(value).__name__}", {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "field": field,
                        "value_type": type(value).__name__
                    }

            # Validate pair_symbol is a string
            if field == "pair_symbol":
                if not isinstance(value, str) or value.strip() == "":
                    return False, f"strategy_metadata field 'pair_symbol' must be a non-empty string, got {type(value).__name__}", {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "pair_symbol_type": type(value).__name__
                    }

    # ============================================================================
    # STEP 6: Validate pair_candles parameter (if provided)
    # ============================================================================

    if pair_candles is not None:
        if not isinstance(pair_candles, list):
            return False, f"pair_candles must be a list, got {type(pair_candles).__name__}", {
                "trade_id": trade_id,
                "strategy_name": strategy_name,
                "pair_candles_type": type(pair_candles).__name__
            }

        # For spread-based strategies, pair_candles are CRITICAL
        if strategy_type == "spread_based" and len(pair_candles) == 0:
            return False, "pair_candles is empty for spread_based strategy - pair price data is required", {
                "trade_id": trade_id,
                "symbol": symbol,
                "strategy_type": strategy_type,
                "pair_symbol": trade_data.get("strategy_metadata", {}).get("pair_symbol") if isinstance(trade_data.get("strategy_metadata"), dict) else "unknown"
            }

        # Validate each pair candle has required fields
        for i, candle in enumerate(pair_candles):
            if not isinstance(candle, dict):
                return False, f"pair_candle at index {i} is not a dict, got {type(candle).__name__}", {
                    "trade_id": trade_id,
                    "pair_candle_index": i,
                    "candle_type": type(candle).__name__
                }

            for field in required_candle_fields:
                if field not in candle:
                    return False, f"pair_candle at index {i} missing required field '{field}'", {
                        "trade_id": trade_id,
                        "pair_candle_index": i,
                        "missing_field": field,
                        "candle_keys": list(candle.keys())
                    }

                value = candle[field]
                if value is None:
                    return False, f"pair_candle at index {i} has None value for field '{field}'", {
                        "trade_id": trade_id,
                        "pair_candle_index": i,
                        "field": field
                    }

                # For numeric fields, validate they are numbers
                if field in ["open", "high", "low", "close"]:
                    if not isinstance(value, (int, float)):
                        return False, f"pair_candle at index {i} field '{field}' must be numeric, got {type(value).__name__}", {
                            "trade_id": trade_id,
                            "pair_candle_index": i,
                            "field": field,
                            "value_type": type(value).__name__
                        }

                    if value < 0:
                        return False, f"pair_candle at index {i} field '{field}' cannot be negative (value: {value})", {
                            "trade_id": trade_id,
                            "pair_candle_index": i,
                            "field": field,
                            "value": value
                        }

    # ============================================================================
    # STEP 7: Validate database connectivity and trade existence
    # ============================================================================

    try:
        from trading_bot.db.client import get_connection, query_one, release_connection

        conn = None
        try:
            conn = get_connection(timeout_seconds=5.0)
        except Exception as e:
            return False, f"Failed to connect to database: {e}", {
                "trade_id": trade_id,
                "strategy_name": strategy_name,
                "error": str(e)
            }

        try:
            # Query trade from database
            db_trade = query_one(conn, "SELECT * FROM trades WHERE id = ?", (trade_id,))

            if not db_trade:
                return False, f"Trade not found in database (trade_id: {trade_id})", {
                    "trade_id": trade_id,
                    "strategy_name": strategy_name
                }

            # ================================================================
            # STEP 8: Validate data consistency - compare passed data with DB
            # ================================================================

            # Check symbol matches
            db_symbol = db_trade.get("symbol")
            if db_symbol != symbol:
                return False, f"Symbol mismatch: passed '{symbol}' but database has '{db_symbol}' for trade {trade_id}", {
                    "trade_id": trade_id,
                    "passed_symbol": symbol,
                    "db_symbol": db_symbol
                }

            # Check strategy_type matches
            db_strategy_type = db_trade.get("strategy_type")
            if db_strategy_type and db_strategy_type != strategy_type:
                return False, f"Strategy type mismatch: passed '{strategy_type}' but database has '{db_strategy_type}' for trade {trade_id}", {
                    "trade_id": trade_id,
                    "passed_strategy_type": strategy_type,
                    "db_strategy_type": db_strategy_type
                }

            # Check side matches
            db_side = db_trade.get("side")
            if db_side and db_side.lower() != side.lower():
                return False, f"Side mismatch: passed '{side}' but database has '{db_side}' for trade {trade_id}", {
                    "trade_id": trade_id,
                    "passed_side": side,
                    "db_side": db_side
                }

            # Check filled_at matches
            db_filled_at = db_trade.get("filled_at")
            if db_filled_at:
                # Normalize both timestamps for comparison
                try:
                    # Parse passed filled_at
                    if isinstance(filled_at, str):
                        filled_at_str = filled_at.replace("+00", "Z").replace(" ", "T")
                        if "T" not in filled_at_str:
                            filled_at_str = filled_at_str.replace(" ", "T")
                        passed_dt = datetime.fromisoformat(filled_at_str.replace("Z", "+00:00"))
                    elif isinstance(filled_at, (int, float)):
                        passed_dt = datetime.fromtimestamp(filled_at / 1000 if filled_at > 10000000000 else filled_at, tz=timezone.utc)
                    else:
                        passed_dt = filled_at  # Already a datetime object

                    # Parse database filled_at
                    if isinstance(db_filled_at, str):
                        # Handle PostgreSQL format: "2025-12-24 23:00:00+00:00"
                        db_filled_at_str = db_filled_at.replace("+00", "Z").replace(" ", "T")
                        if "T" not in db_filled_at_str:
                            db_filled_at_str = db_filled_at_str.replace(" ", "T")
                        db_dt = datetime.fromisoformat(db_filled_at_str.replace("Z", "+00:00"))
                    elif isinstance(db_filled_at, (int, float)):
                        db_dt = datetime.fromtimestamp(db_filled_at / 1000 if db_filled_at > 10000000000 else db_filled_at, tz=timezone.utc)
                    else:
                        db_dt = db_filled_at  # Already a datetime object

                    # Ensure both are datetime objects before comparison
                    if not isinstance(passed_dt, datetime):
                        return False, f"filled_at passed value is not a valid datetime: {type(passed_dt).__name__}", {
                            "trade_id": trade_id,
                            "passed_filled_at": str(filled_at),
                            "passed_type": type(passed_dt).__name__
                        }

                    if not isinstance(db_dt, datetime):
                        return False, f"filled_at database value is not a valid datetime: {type(db_dt).__name__}", {
                            "trade_id": trade_id,
                            "db_filled_at": str(db_filled_at),
                            "db_type": type(db_dt).__name__
                        }

                    # Allow 1 second tolerance for timestamp comparison
                    time_diff = abs((passed_dt - db_dt).total_seconds())
                    if time_diff > 1:
                        return False, f"filled_at timestamp mismatch: passed {filled_at} but database has {db_filled_at} for trade {trade_id}", {
                            "trade_id": trade_id,
                            "passed_filled_at": str(filled_at),
                            "db_filled_at": str(db_filled_at),
                            "difference_seconds": time_diff
                        }
                except Exception as ts_error:
                    return False, f"Error comparing filled_at timestamps: {ts_error}", {
                        "trade_id": trade_id,
                        "passed_filled_at": str(filled_at),
                        "db_filled_at": str(db_filled_at),
                        "error_type": type(ts_error).__name__
                    }

            # ================================================================
            # STEP 9: Validate metadata completeness for spread-based trades
            # ================================================================

            if strategy_type == "spread_based":
                db_metadata = db_trade.get("strategy_metadata")

                if not db_metadata:
                    return False, f"strategy_metadata is missing in database for spread-based trade {trade_id}", {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "strategy_type": strategy_type
                    }

                # Parse if it's a JSON string
                if isinstance(db_metadata, str):
                    try:
                        db_metadata = json.loads(db_metadata)
                    except json.JSONDecodeError as e:
                        return False, f"strategy_metadata in database is not valid JSON: {e}", {
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "db_metadata": db_metadata[:100] if len(db_metadata) > 100 else db_metadata
                        }

                if not isinstance(db_metadata, dict):
                    return False, f"strategy_metadata in database must be a dict, got {type(db_metadata).__name__}", {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "db_metadata_type": type(db_metadata).__name__
                    }

                # Verify all required fields are in database metadata
                required_db_metadata_fields = ["beta", "spread_mean", "spread_std", "z_exit_threshold", "pair_symbol", "price_y_at_entry", "max_spread_deviation"]
                for field in required_db_metadata_fields:
                    if field not in db_metadata:
                        return False, f"strategy_metadata in database missing required field '{field}' for trade {trade_id}", {
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "missing_field": field,
                            "db_metadata_keys": list(db_metadata.keys())
                        }

                    value = db_metadata[field]
                    if value is None:
                        return False, f"strategy_metadata in database field '{field}' is None for trade {trade_id}", {
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "field": field
                        }

        finally:
            if conn:
                release_connection(conn)

    except ImportError as e:
        return False, f"Failed to import database client: {e}", {
            "trade_id": trade_id,
            "strategy_name": strategy_name
        }
    except Exception as e:
        return False, f"Database validation error: {e}", {
            "trade_id": trade_id,
            "strategy_name": strategy_name,
            "error": str(e)
        }

    # ============================================================================
    # STEP 10: Validate candle symbol consistency
    # ============================================================================

    # Verify all candles are for the correct symbol
    for i, candle in enumerate(candles):
        # Candles don't have symbol field, but we can verify they're in order
        # Check that timestamps are in ascending order
        if i > 0:
            prev_ts = candles[i-1].get("timestamp")
            curr_ts = candle.get("timestamp")

            if prev_ts and curr_ts:
                try:
                    # Parse timestamps for comparison
                    if isinstance(prev_ts, str):
                        prev_ts_str = prev_ts.replace("+00", "Z").replace(" ", "T")
                        if "T" not in prev_ts_str:
                            prev_ts_str = prev_ts_str.replace(" ", "T")
                        prev_dt = datetime.fromisoformat(prev_ts_str.replace("Z", "+00:00"))
                        prev_ts_sec = prev_dt.timestamp()
                    else:
                        prev_ts_sec = prev_ts / 1000 if prev_ts > 10000000000 else prev_ts

                    if isinstance(curr_ts, str):
                        curr_ts_str = curr_ts.replace("+00", "Z").replace(" ", "T")
                        if "T" not in curr_ts_str:
                            curr_ts_str = curr_ts_str.replace(" ", "T")
                        curr_dt = datetime.fromisoformat(curr_ts_str.replace("Z", "+00:00"))
                        curr_ts_sec = curr_dt.timestamp()
                    else:
                        curr_ts_sec = curr_ts / 1000 if curr_ts > 10000000000 else curr_ts

                    if curr_ts_sec < prev_ts_sec:
                        return False, f"Candles are not in chronological order: candle {i-1} has timestamp {prev_ts}, candle {i} has earlier timestamp {curr_ts}", {
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "prev_candle_index": i-1,
                            "prev_timestamp": str(prev_ts),
                            "curr_candle_index": i,
                            "curr_timestamp": str(curr_ts)
                        }
                except Exception as ts_error:
                    return False, f"Error validating candle timestamp order at index {i}: {ts_error}", {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "candle_index": i
                    }

    # ============================================================================
    # STEP 11: Validate pair candles symbol consistency (if provided)
    # ============================================================================

    if pair_candles and len(pair_candles) > 0 and strategy_type == "spread_based":
        # Verify pair candles are in chronological order
        for i, candle in enumerate(pair_candles):
            if i > 0:
                prev_ts = pair_candles[i-1].get("timestamp")
                curr_ts = candle.get("timestamp")

                if prev_ts and curr_ts:
                    try:
                        # Parse timestamps for comparison
                        if isinstance(prev_ts, str):
                            prev_ts_str = prev_ts.replace("+00", "Z").replace(" ", "T")
                            if "T" not in prev_ts_str:
                                prev_ts_str = prev_ts_str.replace(" ", "T")
                            prev_dt = datetime.fromisoformat(prev_ts_str.replace("Z", "+00:00"))
                            prev_ts_sec = prev_dt.timestamp()
                        else:
                            prev_ts_sec = prev_ts / 1000 if prev_ts > 10000000000 else prev_ts

                        if isinstance(curr_ts, str):
                            curr_ts_str = curr_ts.replace("+00", "Z").replace(" ", "T")
                            if "T" not in curr_ts_str:
                                curr_ts_str = curr_ts_str.replace(" ", "T")
                            curr_dt = datetime.fromisoformat(curr_ts_str.replace("Z", "+00:00"))
                            curr_ts_sec = curr_dt.timestamp()
                        else:
                            curr_ts_sec = curr_ts / 1000 if curr_ts > 10000000000 else curr_ts

                        if curr_ts_sec < prev_ts_sec:
                            return False, f"Pair candles are not in chronological order: pair_candle {i-1} has timestamp {prev_ts}, pair_candle {i} has earlier timestamp {curr_ts}", {
                                "trade_id": trade_id,
                                "pair_symbol": trade_data.get("strategy_metadata", {}).get("pair_symbol") if isinstance(trade_data.get("strategy_metadata"), dict) else "unknown",
                                "prev_candle_index": i-1,
                                "prev_timestamp": str(prev_ts),
                                "curr_candle_index": i,
                                "curr_timestamp": str(curr_ts)
                            }
                    except Exception as ts_error:
                        return False, f"Error validating pair candle timestamp order at index {i}: {ts_error}", {
                            "trade_id": trade_id,
                            "pair_symbol": trade_data.get("strategy_metadata", {}).get("pair_symbol") if isinstance(trade_data.get("strategy_metadata"), dict) else "unknown",
                            "pair_candle_index": i
                        }

    # ============================================================================
    # ALL VALIDATIONS PASSED
    # ============================================================================

    return True, None, None


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
        # Log entry
        # CRITICAL: symbol and strategy_type are REQUIRED - NO FALLBACKS
        if not trade_data:
            error_msg = "trade_data is required"
            logger.error(f"ERROR: {error_msg} for trade {trade_id}")
            log_error_to_db(trade_id, "unknown", "missing_trade_data", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None
            }

        symbol = trade_data.get("symbol")
        if not symbol:
            error_msg = "symbol is required in trade_data"
            logger.error(f"ERROR: {error_msg} for trade {trade_id}")
            log_error_to_db(trade_id, "unknown", "missing_symbol", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None
            }

        strategy_type = trade_data.get("strategy_type")
        if not strategy_type:
            error_msg = "strategy_type is required in trade_data"
            logger.error(f"ERROR: {error_msg} for trade {trade_id}")
            log_error_to_db(trade_id, symbol, "missing_strategy_type", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None
            }

        print(f"\n{'='*80}", file=sys.stderr)
        print(f"[Exit-Check] ========== STRATEGY EXIT CHECK STARTED ==========", file=sys.stderr)
        print(f"[Exit-Check] Trade ID: {trade_id}", file=sys.stderr)
        print(f"[Exit-Check] Symbol: {symbol}", file=sys.stderr)
        print(f"[Exit-Check] Strategy: {strategy_name} ({strategy_type})", file=sys.stderr)
        print(f"[Exit-Check] Candles: {len(candles)}", file=sys.stderr)
        print(f"[Exit-Check] Pair candles: {len(pair_candles) if pair_candles else 'None'}", file=sys.stderr)
        print(f"{'='*80}", file=sys.stderr)

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

        print(f"[Exit-Check] Step 1: Loading strategy factory...", file=sys.stderr)
        # Import strategy factory
        from trading_bot.strategies import StrategyFactory
        from trading_bot.config.settings_v2 import ConfigV2

        # Get strategy class from factory registry
        strategies = StrategyFactory.get_available_strategies()
        print(f"[Exit-Check] Step 1 COMPLETE: Found {len(strategies)} available strategies", file=sys.stderr)

        if strategy_name not in strategies:
            error_msg = f"Strategy not found: {strategy_name}"
            print(f"[Exit-Check] Step 1 FAILED: {error_msg}", file=sys.stderr)
            print(f"[Exit-Check] Available strategies: {list(strategies.keys())}", file=sys.stderr)
            logger.error(f"ERROR: {error_msg}. Available: {list(strategies.keys())}")
            log_error_to_db(trade_id, symbol, "strategy_not_found", error_msg, {
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

        print(f"[Exit-Check] Step 2: Instantiating strategy {strategy_name}...", file=sys.stderr)
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
            print(f"[Exit-Check] Step 2 COMPLETE: Strategy instantiated successfully", file=sys.stderr)
        except Exception as e:
            error_msg = f"Failed to instantiate strategy: {e}"
            print(f"[Exit-Check] Step 2 FAILED: {error_msg}", file=sys.stderr)
            logger.error(f"ERROR: {error_msg} for trade {trade_id}", exc_info=True)
            log_error_to_db(trade_id, symbol, "strategy_instantiation_failed", error_msg, {
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

        # TASK 9: Validate pair candles for spread-based strategies
        strategy_type = trade_data.get("strategy_type")
        is_spread_based = strategy_type == "spread_based"

        print(f"[Exit-Check] Step 3: Validating inputs for {strategy_type} strategy...", file=sys.stderr)

        if is_spread_based:
            # For spread-based strategies, pair_candles are CRITICAL
            if pair_candles is None or len(pair_candles) == 0:
                error_msg = (
                    f"CRITICAL: Pair candles not provided for spread-based exit check. "
                    f"Trade ID: {trade_id}, Strategy: {strategy_name}. "
                    f"Cannot calculate z-score without pair price data."
                )
                print(f"[Exit-Check] Step 3 FAILED: {error_msg}", file=sys.stderr)
                logger.critical(error_msg)
                log_error_to_db(trade_id, symbol, "missing_pair_candles", error_msg)
                return {
                    "should_exit": False,
                    "exit_price": None,
                    "exit_reason": None,
                    "exit_timestamp": None,
                    "current_price": None,
                    "error": error_msg
                }

            # TASK 9: Align candles if lengths differ (take newest N from longer series)
            print(f"[Exit-Check] Step 3 DETAIL: Aligning candles - Main: {len(candles)}, Pair: {len(pair_candles)}", file=sys.stderr)
            if len(candles) != len(pair_candles):
                min_length = min(len(candles), len(pair_candles))
                trim_amount = len(candles) - min_length

                # Trim both to newest min_length candles
                candles = candles[trim_amount:]
                pair_candles = pair_candles[-min_length:]

                print(f"[Exit-Check] Step 3 DETAIL: Trimmed {trim_amount} candles from main series. Now aligned: {len(candles)} candles each", file=sys.stderr)

            print(f"[Exit-Check] Step 3 COMPLETE: Pair candles validated and aligned ({len(pair_candles)} candles)", file=sys.stderr)
        else:
            print(f"[Exit-Check] Step 3 COMPLETE: Price-based strategy (no pair candles needed)", file=sys.stderr)

        print(f"[Exit-Check] Step 4: Recalculating fill_candle_index based on timestamps...", file=sys.stderr)

        # Get fill timestamp and timeframe to find the correct fill candle
        filled_at = trade_data.get("filled_at")
        timeframe = trade_data.get("timeframe", "1h")

        # Convert timeframe to seconds
        timeframe_seconds = {
            "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800
        }.get(timeframe, 3600)

        # Find fill candle by timestamp (timeframe-aware)
        fill_candle_index = None
        if filled_at:
            try:
                from datetime import datetime, timezone
                # Parse filled_at timestamp
                if isinstance(filled_at, str):
                    # Handle both ISO format and PostgreSQL format
                    filled_at_str = filled_at.replace("+00", "Z").replace(" ", "T")
                    if "T" not in filled_at_str:
                        filled_at_str = filled_at_str.replace(" ", "T")
                    filled_dt = datetime.fromisoformat(filled_at_str.replace("Z", "+00:00"))
                else:
                    filled_dt = filled_at

                # Calculate which candle period contains this fill
                # For 1h: fill at 13:15 belongs to 13:00 candle (close time)
                fill_timestamp_sec = filled_dt.timestamp()
                candle_close_time_sec = (int(fill_timestamp_sec // timeframe_seconds) + 1) * timeframe_seconds

                # Find matching candle in aligned series
                for i, candle in enumerate(candles):
                    candle_ts = candle.get("timestamp")
                    if isinstance(candle_ts, str):
                        # Handle ISO format or PostgreSQL format
                        candle_ts_str = candle_ts.replace("+00", "Z").replace(" ", "T")
                        if "T" not in candle_ts_str:
                            candle_ts_str = candle_ts_str.replace(" ", "T")
                        candle_dt = datetime.fromisoformat(candle_ts_str.replace("Z", "+00:00"))
                        candle_ts_sec = candle_dt.timestamp()
                    elif isinstance(candle_ts, (int, float)):
                        # Handle Unix timestamp (milliseconds or seconds)
                        if candle_ts > 10000000000:  # Likely milliseconds (> year 2286 in seconds)
                            candle_ts_sec = candle_ts / 1000
                        else:
                            candle_ts_sec = candle_ts
                    else:
                        continue  # Skip if timestamp format is unknown

                    if abs(candle_ts_sec - candle_close_time_sec) < 1:  # Allow 1 second tolerance
                        fill_candle_index = i
                        print(f"[Exit-Check] Step 4 DETAIL: Found fill candle at index {fill_candle_index} (timestamp: {candle_ts})", file=sys.stderr)
                        break

                if fill_candle_index is None:
                    # Fill timestamp not found in aligned candles
                    # This means the fill happened before the aligned candle range
                    print(f"[Exit-Check] Step 4 WARNING: Fill timestamp not in aligned candle range. Fill time: {filled_at}, Earliest candle: {candles[0].get('timestamp') if candles else 'N/A'}", file=sys.stderr)
                    print(f"[Exit-Check] Step 4 DETAIL: This likely means candles were trimmed and fill is outside the range. Skipping this trade.", file=sys.stderr)
                    error_msg = (
                        f"CRITICAL: Fill timestamp not found in aligned candle range. "
                        f"Trade ID: {trade_id}, Fill time: {filled_at}. "
                        f"Candles may have been trimmed during alignment, removing the fill point."
                    )
                    logger.critical(error_msg)
                    log_error_to_db(trade_id, symbol, "fill_outside_candle_range", error_msg, {
                        "filled_at": str(filled_at),
                        "earliest_candle": candles[0].get('timestamp') if candles else None,
                        "total_candles": len(candles)
                    })
                    return {
                        "should_exit": False,
                        "exit_price": None,
                        "exit_reason": None,
                        "exit_timestamp": None,
                        "current_price": None,
                        "error": error_msg
                    }
            except Exception as e:
                print(f"[Exit-Check] Step 4 WARNING: Error calculating fill candle index: {e}", file=sys.stderr)
                error_msg = f"Error calculating fill candle index: {e}"
                logger.error(error_msg)
                log_error_to_db(trade_id, symbol, "fill_candle_calculation_error", error_msg)
                return {
                    "should_exit": False,
                    "exit_price": None,
                    "exit_reason": None,
                    "exit_timestamp": None,
                    "current_price": None,
                    "error": error_msg
                }
        else:
            error_msg = "filled_at timestamp not provided in trade_data"
            print(f"[Exit-Check] Step 4 WARNING: {error_msg}", file=sys.stderr)
            logger.warning(error_msg)
            log_error_to_db(trade_id, symbol, "missing_filled_at", error_msg)
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": error_msg
            }

        # Get lookback requirement from strategy
        lookback = strategy.get_config_value('lookback', 120)
        print(f"[Exit-Check] Step 4 DETAIL: Lookback requirement: {lookback} candles", file=sys.stderr)

        # VALIDATION: Check if we have enough lookback candles BEFORE fill
        if fill_candle_index < lookback:
            error_msg = (
                f"CRITICAL: Not enough lookback candles before fill. "
                f"Trade ID: {trade_id}, Have: {fill_candle_index}, Need: {lookback}. "
                f"Cannot calculate strategy indicators without sufficient lookback data."
            )
            print(f"[Exit-Check] Step 4 FAILED: {error_msg}", file=sys.stderr)
            logger.critical(error_msg)
            log_error_to_db(trade_id, symbol, "insufficient_lookback_candles", error_msg, {
                "fill_candle_index": fill_candle_index,
                "lookback_required": lookback,
                "total_candles": len(candles)
            })
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": error_msg
            }

        # VALIDATION: Check if we have at least 1 candle AFTER fill to check for exit
        if fill_candle_index + 1 >= len(candles):
            error_msg = (
                f"CRITICAL: No candles after fill to check exit. "
                f"Trade ID: {trade_id}, Fill index: {fill_candle_index}, Total candles: {len(candles)}. "
                f"Need at least one candle after fill for exit signal detection."
            )
            print(f"[Exit-Check] Step 4 FAILED: {error_msg}", file=sys.stderr)
            logger.critical(error_msg)
            log_error_to_db(trade_id, symbol, "no_candles_after_fill", error_msg, {
                "fill_candle_index": fill_candle_index,
                "total_candles": len(candles)
            })
            return {
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None,
                "error": error_msg
            }

        print(f"[Exit-Check] Step 4 COMPLETE: Fill candle index validated. Starting exit check from candle {fill_candle_index + 1}", file=sys.stderr)

        print(f"[Exit-Check] Step 5: Starting candle iteration...", file=sys.stderr)
        # Iterate through candles and check for exit
        # NOTE: For spread-based strategies, pair_candles are provided from the database cache
        # If not available, the strategy's should_exit() method can fetch from live API as fallback
        last_exit_result = None  # Track last exit_result for stop/TP syncing when holding

        # Determine position side (LONG or SHORT)
        # CRITICAL: side is REQUIRED - NO FALLBACK
        side = trade_data.get("side")
        if not side:
            error_msg = "side is required in trade_data (must be 'Buy' or 'Sell')"
            logger.error(f"ERROR: {error_msg} for trade {trade_id}")
            log_error_to_db(trade_id, symbol, "missing_side", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None
            }

        is_long = side.lower() in ["buy", "long"]
        side_str = "LONG" if is_long else "SHORT"

        # Track simulated stops/TPs as they change each candle
        # CRITICAL: For price-based strategies, SL/TP are REQUIRED
        stop_loss = trade_data.get("stop_loss")
        take_profit = trade_data.get("take_profit")

        if strategy_type == "price_based":
            if not stop_loss:
                error_msg = f"stop_loss is required for price_based strategy (trade {trade_id})"
                logger.error(f"ERROR: {error_msg}")
                log_error_to_db(trade_id, symbol, "missing_stop_loss", error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "should_exit": False,
                    "exit_price": None,
                    "exit_reason": None,
                    "exit_timestamp": None,
                    "current_price": None
                }
            if not take_profit:
                error_msg = f"take_profit is required for price_based strategy (trade {trade_id})"
                logger.error(f"ERROR: {error_msg}")
                log_error_to_db(trade_id, symbol, "missing_take_profit", error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "should_exit": False,
                    "exit_price": None,
                    "exit_reason": None,
                    "exit_timestamp": None,
                    "current_price": None
                }

        simulated_stops = {
            "stop_loss": stop_loss,
            "take_profit": take_profit
        }
        stop_updates = []  # Audit trail of all stop/TP changes

        print(f"[Exit-Check] Step 5 DETAIL: Position side={side_str}, SL={simulated_stops['stop_loss']}, TP={simulated_stops['take_profit']}", file=sys.stderr)

        # PERFORMANCE FIX: Create lookup dict for pair candles by timestamp (O(1) lookup instead of O(n) search)
        pair_candles_by_ts = {}
        if pair_candles:
            for pair_candle in pair_candles:
                ts = pair_candle.get("timestamp")
                if ts is not None:
                    pair_candles_by_ts[ts] = pair_candle

        # Start iteration from fill_candle_index + 1 (first candle AFTER fill)
        for i in range(fill_candle_index + 1, len(candles)):
            candle = candles[i]
            try:
                current_candle_dict = {
                    "timestamp": candle.get("timestamp"),
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "close": candle.get("close"),
                }

                # Find corresponding pair candle by timestamp (O(1) lookup)
                pair_candle_dict = None
                if pair_candles_by_ts:
                    pair_candle = pair_candles_by_ts.get(current_candle_dict.get("timestamp"))
                    if pair_candle:
                        pair_candle_dict = {
                            "timestamp": pair_candle.get("timestamp"),
                            "open": pair_candle.get("open"),
                            "high": pair_candle.get("high"),
                            "low": pair_candle.get("low"),
                            "close": pair_candle.get("close"),
                        }

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
                    # CRITICAL: Candle prices are REQUIRED - NO FALLBACKS
                    candle_high = current_candle_dict.get("high")
                    candle_low = current_candle_dict.get("low")

                    if candle_high is None or candle_low is None:
                        error_msg = f"Candle {i} missing high/low prices - cannot check SL/TP"
                        logger.error(f"ERROR: {error_msg} for trade {trade_id}")
                        continue

                    if is_long:
                        # Long position: SL hit if low <= stopLoss, TP hit if high >= takeProfit
                        sl_hit = simulated_stops["stop_loss"] and candle_low <= simulated_stops["stop_loss"]
                        tp_hit = simulated_stops["take_profit"] and candle_high >= simulated_stops["take_profit"]

                        if sl_hit and tp_hit:
                            # Both hit in same candle - determine which first by checking open price
                            candle_open = current_candle_dict.get("open")
                            if candle_open is None:
                                error_msg = f"Candle {i} missing open price - cannot determine SL/TP priority"
                                logger.error(f"ERROR: {error_msg} for trade {trade_id}")
                                continue

                            if abs(candle_open - simulated_stops["stop_loss"]) < abs(candle_open - simulated_stops["take_profit"]):
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
                            candle_open = current_candle_dict.get("open")
                            if candle_open is None:
                                error_msg = f"Candle {i} missing open price - cannot determine SL/TP priority"
                                logger.error(f"ERROR: {error_msg} for trade {trade_id}")
                                continue

                            if abs(candle_open - simulated_stops["stop_loss"]) < abs(candle_open - simulated_stops["take_profit"]):
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
                    exit_price = current_candle_dict.get("close")

                    print(f"[Exit-Check] Step 4 RESULT: EXIT SIGNAL DETECTED at candle {i}/{len(candles)}", file=sys.stderr)
                    print(f"[Exit-Check] Step 4 DETAIL: reason={reason}, exit_price={exit_price}", file=sys.stderr)
                    logger.info(f"Strategy exit triggered for trade {trade_id} at candle {i}: {reason}")

                    # Build response with optional strategy-calculated stops
                    response = {
                        "should_exit": True,
                        "exit_price": exit_price,
                        "exit_reason": reason,
                        "exit_timestamp": current_candle_dict.get("timestamp"),
                        "current_price": exit_price,
                        "stop_updates": stop_updates,
                        "final_stops": simulated_stops
                    }

                    # For spread-based trades, include pair price from exit_details
                    if is_spread_based and "pair_price" in exit_details:
                        response["pair_exit_price"] = exit_details.get("pair_price")
                        pair_price_str = f", pair_price={exit_details.get('pair_price')}"
                        print(f"[Exit-Check] Step 4 DETAIL: current_price={exit_price}{pair_price_str}", file=sys.stderr)

                    # Include strategy-calculated stops if provided (for consistency with PositionMonitor)
                    if "stop_level" in exit_details:
                        response["stop_level"] = exit_details.get("stop_level")
                    if "tp_level" in exit_details:
                        response["tp_level"] = exit_details.get("tp_level")

                    return response
            except Exception as e:
                error_msg = f"Exception in candle {i}: {e}"
                print(f"[Exit-Check] Step 4 ERROR: Candle {i} processing failed: {error_msg}", file=sys.stderr)
                logger.error(f"ERROR: {error_msg} for trade {trade_id}", exc_info=True)
                log_error_to_db(trade_id, symbol, "candle_processing_error", error_msg, {
                    "candle_index": i,
                    "exception_type": type(e).__name__
                })
                continue

        # No exit condition met
        candles_checked = len(candles) - fill_candle_index
        print(f"[Exit-Check] Step 4 COMPLETE: No exit signal found after checking {candles_checked} candles (from index {fill_candle_index} to {len(candles)-1})", file=sys.stderr)
        logger.info(f"No exit condition met for trade {trade_id} after checking {candles_checked} candles")

        # Return response with optional strategy-calculated stops from last candle check
        # This allows strategies to provide dynamic stop/TP levels even when holding
        # CRITICAL: current_price is REQUIRED - must come from last candle
        if not candles:
            error_msg = f"No candles available to determine current_price for trade {trade_id}"
            logger.error(f"ERROR: {error_msg}")
            log_error_to_db(trade_id, symbol, "no_candles_for_current_price", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None
            }

        current_price = candles[-1].get("close")
        if current_price is None:
            error_msg = f"Last candle missing close price for trade {trade_id}"
            logger.error(f"ERROR: {error_msg}")
            log_error_to_db(trade_id, symbol, "last_candle_missing_close", error_msg)
            return {
                "success": False,
                "error": error_msg,
                "should_exit": False,
                "exit_price": None,
                "exit_reason": None,
                "exit_timestamp": None,
                "current_price": None
            }

        # For spread-based trades, also get pair price from last pair candle
        pair_price = None
        if is_spread_based and pair_candles and len(pair_candles) > 0:
            pair_price = pair_candles[-1].get("close")

        response = {
            "should_exit": False,
            "exit_price": None,
            "exit_reason": None,
            "exit_timestamp": None,
            "current_price": current_price,
            "stop_updates": stop_updates,  # Include audit trail of all stop/TP changes
            "final_stops": simulated_stops  # Include final simulated stops
        }

        # Add pair price for spread-based trades
        if is_spread_based and pair_price is not None:
            response["pair_current_price"] = pair_price

        print(f"[Exit-Check] Step 5: Returning no-exit response", file=sys.stderr)
        if is_spread_based and pair_price is not None:
            print(f"[Exit-Check] Step 5 DETAIL: current_price={current_price}, pair_price={pair_price}", file=sys.stderr)
        else:
            print(f"[Exit-Check] Step 5 DETAIL: current_price={current_price}", file=sys.stderr)

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
    # ============================================================================
    # STEP 0: Validate command-line arguments
    # ============================================================================

    if len(sys.argv) < 5:
        error_msg = "Usage: check_strategy_exit.py <trade_id> <strategy_name> <candles_json> <trade_data_json> [pair_candles_json]"
        print(json.dumps({
            "success": False,
            "error": error_msg,
            "should_exit": False,
            "exit_price": None,
            "exit_reason": None,
            "exit_timestamp": None,
            "current_price": None
        }))
        sys.exit(1)

    trade_id = sys.argv[1]
    strategy_name = sys.argv[2]
    candles_json = sys.argv[3]
    trade_data_json = sys.argv[4]
    pair_candles_json = sys.argv[5] if len(sys.argv) > 5 else "[]"

    # ============================================================================
    # STEP 1: Parse JSON inputs
    # ============================================================================

    try:
        candles = json.loads(candles_json)
        trade_data = json.loads(trade_data_json)
        pair_candles = json.loads(pair_candles_json)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in command-line arguments: {e}"
        logger.error(f"ERROR: {error_msg}")
        print(json.dumps({
            "success": False,
            "error": error_msg,
            "should_exit": False,
            "exit_price": None,
            "exit_reason": None,
            "exit_timestamp": None,
            "current_price": None
        }))
        sys.exit(1)

    # ============================================================================
    # STEP 2: COMPREHENSIVE VALIDATION - Exit early if ANY required values are missing
    # ============================================================================

    is_valid, validation_error, error_context = validate_input_parameters(
        trade_id, strategy_name, candles, trade_data, pair_candles
    )

    if not is_valid:
        # Log validation error
        logger.critical(f"VALIDATION FAILED: {validation_error}")
        print(f"[Exit-Check] VALIDATION FAILED: {validation_error}", file=sys.stderr)
        if error_context:
            print(f"[Exit-Check] Error context: {json.dumps(error_context, indent=2)}", file=sys.stderr)

        # Try to log to database
        try:
            symbol = trade_data.get("symbol", "unknown") if isinstance(trade_data, dict) else "unknown"
            if validation_error:  # validation_error is guaranteed to be a string if is_valid is False
                log_error_to_db(
                    trade_id,
                    symbol,
                    "validation_failed",
                    validation_error,
                    error_context
                )
        except Exception as db_error:
            logger.warning(f"Failed to log validation error to database: {db_error}")

        # Return error response
        print(json.dumps({
            "success": False,
            "error": validation_error,
            "should_exit": False,
            "exit_price": None,
            "exit_reason": None,
            "exit_timestamp": None,
            "current_price": None,
            "validation_error": True
        }))
        sys.exit(1)

    # ============================================================================
    # STEP 3: All validations passed - proceed with exit check
    # ============================================================================

    result = check_strategy_exit(trade_id, strategy_name, candles, trade_data, pair_candles)

    # Log result
    if result.get("should_exit"):
        print(f"[Exit-Check] ========== STRATEGY EXIT CHECK COMPLETED ==========", file=sys.stderr)
        print(f"[Exit-Check] Result: EXIT SIGNAL", file=sys.stderr)
        print(f"[Exit-Check] Reason: {result.get('exit_reason')}", file=sys.stderr)
        print(f"[Exit-Check] Exit Price: {result.get('exit_price')}", file=sys.stderr)
        print(f"{'='*80}\n", file=sys.stderr)
    else:
        print(f"[Exit-Check] ========== STRATEGY EXIT CHECK COMPLETED ==========", file=sys.stderr)
        print(f"[Exit-Check] Result: NO EXIT SIGNAL", file=sys.stderr)
        print(f"[Exit-Check] Current Price: {result.get('current_price')}", file=sys.stderr)
        print(f"{'='*80}\n", file=sys.stderr)

    print(json.dumps(result))

