#!/usr/bin/env python3
"""
Validation for closing logic - validates all data fetched from database for closing trades.

This module validates that all required fields are present and valid for:
1. Open trades fetched from database
2. Candles fetched for each trade
3. Exit conditions and P&L calculations

Usage:
    from validate_closing_trades import validate_trade_for_closing, validate_candles_for_closing
    
    is_valid, error, context = validate_trade_for_closing(trade_data)
    if not is_valid:
        logger.error(f"Trade validation failed: {error}")
        return
"""

import sys
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def validate_trade_for_closing(trade: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    COMPREHENSIVE VALIDATION: Validate a trade fetched from database for closing.
    
    Checks:
    1. Trade exists and has all required fields
    2. Trade status is valid (paper_trade, pending_fill, filled)
    3. Trade has not already been closed (pnl is None)
    4. All required price fields are present and valid
    5. Trade has valid timestamps
    6. Strategy metadata is complete (for spread-based trades)
    
    Returns:
        Tuple of (is_valid, error_message, error_context)
    """
    
    if not trade:
        return False, "Trade data is None or empty", None
    
    if not isinstance(trade, dict):
        return False, f"Trade must be a dict, got {type(trade).__name__}", None
    
    # ============================================================================
    # STEP 1: Validate REQUIRED trade fields
    # ============================================================================
    
    required_fields = ["id", "symbol", "side", "status", "created_at"]
    for field in required_fields:
        if field not in trade:
            return False, f"Trade missing required field '{field}'", {
                "trade_id": trade.get("id", "unknown"),
                "missing_field": field,
                "trade_keys": list(trade.keys())
            }
        
        value = trade[field]
        if value is None:
            return False, f"Trade field '{field}' cannot be None", {
                "trade_id": trade.get("id", "unknown"),
                "field": field
            }
    
    trade_id = trade.get("id")
    symbol = trade.get("symbol")
    
    # ============================================================================
    # STEP 2: Validate trade status
    # ============================================================================
    
    status = trade.get("status")
    valid_statuses = ["paper_trade", "pending_fill", "filled"]
    if status not in valid_statuses:
        return False, f"Trade status must be one of {valid_statuses}, got '{status}'", {
            "trade_id": trade_id,
            "symbol": symbol,
            "status": status
        }
    
    # ============================================================================
    # STEP 3: Validate trade is not already closed
    # ============================================================================
    
    pnl = trade.get("pnl")
    if pnl is not None:
        return False, f"Trade is already closed (pnl={pnl}), cannot close again", {
            "trade_id": trade_id,
            "symbol": symbol,
            "pnl": pnl
        }
    
    # ============================================================================
    # STEP 4: Validate price fields
    # ============================================================================
    
    required_price_fields = ["entry_price", "stop_loss", "take_profit"]
    for field in required_price_fields:
        value = trade.get(field)
        
        if value is None:
            return False, f"Trade field '{field}' is required and cannot be None", {
                "trade_id": trade_id,
                "symbol": symbol,
                "field": field
            }
        
        if not isinstance(value, (int, float)):
            return False, f"Trade field '{field}' must be numeric, got {type(value).__name__}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "field": field,
                "value_type": type(value).__name__
            }
        
        if value <= 0:
            return False, f"Trade field '{field}' must be positive, got {value}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "field": field,
                "value": value
            }
    
    # ============================================================================
    # STEP 5: Validate side
    # ============================================================================
    
    side = trade.get("side")
    valid_sides = ["Buy", "Sell", "buy", "sell", "LONG", "SHORT", "long", "short"]
    if side not in valid_sides:
        return False, f"Trade side must be one of {valid_sides}, got '{side}'", {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side
        }
    
    # ============================================================================
    # STEP 6: Validate timestamps
    # ============================================================================
    
    created_at = trade.get("created_at")
    if not created_at:
        return False, "Trade created_at timestamp is required", {
            "trade_id": trade_id,
            "symbol": symbol
        }
    
    # ============================================================================
    # STEP 7: Validate strategy metadata for spread-based trades
    # ============================================================================
    
    strategy_type = trade.get("strategy_type")
    if strategy_type == "spread_based":
        strategy_metadata = trade.get("strategy_metadata")
        
        if not strategy_metadata:
            return False, "strategy_metadata is required for spread_based trades", {
                "trade_id": trade_id,
                "symbol": symbol,
                "strategy_type": strategy_type
            }
        
        # Parse if JSON string
        if isinstance(strategy_metadata, str):
            try:
                strategy_metadata = json.loads(strategy_metadata)
            except json.JSONDecodeError as e:
                return False, f"strategy_metadata is not valid JSON: {e}", {
                    "trade_id": trade_id,
                    "symbol": symbol
                }
        
        if not isinstance(strategy_metadata, dict):
            return False, f"strategy_metadata must be a dict, got {type(strategy_metadata).__name__}", {
                "trade_id": trade_id,
                "symbol": symbol
            }
        
        # Verify required fields
        required_metadata = ["beta", "spread_mean", "spread_std", "z_exit_threshold", "pair_symbol"]
        for field in required_metadata:
            if field not in strategy_metadata:
                return False, f"strategy_metadata missing required field '{field}'", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "missing_field": field
                }
    
    return True, None, None


def validate_candles_for_closing(
    trade_id: str,
    symbol: str,
    candles: List[Dict[str, Any]],
    min_candles: int = 1
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validate candles fetched from database for closing logic.
    
    Checks:
    1. Candles list is not empty
    2. Each candle has required OHLCV fields
    3. All prices are valid numbers
    4. Candles are in chronological order
    5. Minimum candles requirement is met
    
    Returns:
        Tuple of (is_valid, error_message, error_context)
    """
    
    if not candles:
        return False, f"No candles available for {symbol} - cannot check exit conditions", {
            "trade_id": trade_id,
            "symbol": symbol,
            "candles_count": 0,
            "min_required": min_candles
        }
    
    if len(candles) < min_candles:
        return False, f"Insufficient candles for {symbol}: have {len(candles)}, need {min_candles}", {
            "trade_id": trade_id,
            "symbol": symbol,
            "candles_count": len(candles),
            "min_required": min_candles
        }
    
    # Validate each candle
    required_fields = ["timestamp", "open", "high", "low", "close"]
    for i, candle in enumerate(candles):
        if not isinstance(candle, dict):
            return False, f"Candle {i} is not a dict, got {type(candle).__name__}", {
                "trade_id": trade_id,
                "symbol": symbol,
                "candle_index": i
            }
        
        for field in required_fields:
            if field not in candle:
                return False, f"Candle {i} missing required field '{field}'", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "candle_index": i,
                    "missing_field": field
                }
            
            value = candle[field]
            if value is None:
                return False, f"Candle {i} field '{field}' is None", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "candle_index": i,
                    "field": field
                }
            
            # Validate numeric fields
            if field in ["open", "high", "low", "close"]:
                if not isinstance(value, (int, float)):
                    return False, f"Candle {i} field '{field}' must be numeric, got {type(value).__name__}", {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "candle_index": i,
                        "field": field
                    }
                
                if value < 0:
                    return False, f"Candle {i} field '{field}' cannot be negative: {value}", {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "candle_index": i,
                        "field": field,
                        "value": value
                    }
    
    # Validate chronological order
    for i in range(1, len(candles)):
        prev_ts = candles[i-1].get("timestamp")
        curr_ts = candles[i].get("timestamp")
        
        if prev_ts and curr_ts:
            try:
                if isinstance(prev_ts, str):
                    prev_dt = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
                    prev_sec = prev_dt.timestamp()
                else:
                    prev_sec = prev_ts / 1000 if prev_ts > 10000000000 else prev_ts
                
                if isinstance(curr_ts, str):
                    curr_dt = datetime.fromisoformat(curr_ts.replace("Z", "+00:00"))
                    curr_sec = curr_dt.timestamp()
                else:
                    curr_sec = curr_ts / 1000 if curr_ts > 10000000000 else curr_ts
                
                if curr_sec < prev_sec:
                    return False, f"Candles not in chronological order: candle {i-1} ts={prev_ts}, candle {i} ts={curr_ts}", {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "prev_index": i-1,
                        "curr_index": i
                    }
            except Exception as e:
                return False, f"Error validating candle timestamps: {e}", {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "error": str(e)
                }
    
    return True, None, None

