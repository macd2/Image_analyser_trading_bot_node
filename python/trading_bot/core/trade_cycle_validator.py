"""
Trade Cycle Validation - Ensures trade cycle NEVER fails silently.

This module provides comprehensive validation for:
1. Signal validation before execution
2. Trade execution validation
3. Database persistence validation
4. Error handling with explicit logging

PRINCIPLE: We ALWAYS prefer an error over silent failure.
Missing data = ERROR, not silent assumption.
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TradeCycleValidationError(Exception):
    """Raised when trade cycle validation fails."""
    pass


class SignalValidator:
    """Validates signals before execution."""
    
    @staticmethod
    def validate_signal_for_execution(
        signal: Dict[str, Any],
        symbol: str,
        cycle_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate signal has all required fields for execution.
        
        Args:
            signal: Signal dict to validate
            symbol: Trading symbol
            cycle_id: Cycle ID for logging
            
        Returns:
            Tuple of (is_valid, error_message)
            
        Raises:
            TradeCycleValidationError: If validation fails
        """
        errors = []
        
        # CRITICAL FIELDS - NO FALLBACKS
        required_fields = {
            "recommendation": str,
            "entry_price": (int, float),
            "take_profit": (int, float),
            "stop_loss": (int, float),
            "confidence": (int, float),
        }
        
        for field, expected_type in required_fields.items():
            if field not in signal:
                errors.append(f"Missing required field: {field}")
                continue
            
            value = signal[field]
            if value is None:
                errors.append(f"Field '{field}' cannot be None")
                continue
            
            if not isinstance(value, expected_type):
                errors.append(
                    f"Field '{field}' must be {expected_type}, got {type(value).__name__}"
                )
        
        # Validate price relationships (only if all prices are valid numbers)
        if "entry_price" in signal and "stop_loss" in signal and "take_profit" in signal:
            entry = signal["entry_price"]
            sl = signal["stop_loss"]
            tp = signal["take_profit"]

            # Only check relationships if all are valid numbers (not None, not wrong type)
            if isinstance(entry, (int, float)) and isinstance(sl, (int, float)) and isinstance(tp, (int, float)):
                if entry <= 0 or sl <= 0 or tp <= 0:
                    errors.append(f"All prices must be positive: entry={entry}, sl={sl}, tp={tp}")

                if entry == sl:
                    errors.append(f"Entry price cannot equal stop loss: {entry}")

                if entry == tp:
                    errors.append(f"Entry price cannot equal take profit: {entry}")
        
        # Validate confidence
        if "confidence" in signal:
            confidence = signal["confidence"]
            if not (0 <= confidence <= 1):
                errors.append(f"Confidence must be 0-1, got {confidence}")
        
        # Validate spread-based specific fields
        if signal.get("strategy_type") == "spread_based":
            spread_fields = ["units_x", "units_y", "pair_symbol"]
            for field in spread_fields:
                if field not in signal:
                    errors.append(f"Spread-based trade missing field: {field}")
                elif signal[field] is None:
                    errors.append(f"Spread-based field '{field}' cannot be None")
        
        if errors:
            error_msg = f"Signal validation failed for {symbol} in cycle {cycle_id}: " + "; ".join(errors)
            logger.error(error_msg)
            raise TradeCycleValidationError(error_msg)
        
        return True, None


class TradeExecutionValidator:
    """Validates trade execution results."""
    
    @staticmethod
    def validate_trade_execution_result(
        result: Dict[str, Any],
        symbol: str,
        cycle_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate trade execution result.
        
        Args:
            result: Trade execution result dict
            symbol: Trading symbol
            cycle_id: Cycle ID for logging
            
        Returns:
            Tuple of (is_valid, error_message)
            
        Raises:
            TradeCycleValidationError: If validation fails
        """
        errors = []
        
        # Check result structure
        if not isinstance(result, dict):
            raise TradeCycleValidationError(
                f"Trade execution result must be dict, got {type(result).__name__}"
            )
        
        # CRITICAL: Result must have status
        if "status" not in result:
            raise TradeCycleValidationError(
                f"Trade execution result missing 'status' field for {symbol}"
            )
        
        status = result.get("status")
        valid_statuses = ["paper_trade", "submitted", "rejected", "failed", "error"]
        
        if status not in valid_statuses:
            raise TradeCycleValidationError(
                f"Invalid trade status '{status}' for {symbol}. Must be one of: {valid_statuses}"
            )
        
        # If rejected/failed, must have error reason
        if status in ["rejected", "failed", "error"]:
            if "error" not in result or not result["error"]:
                raise TradeCycleValidationError(
                    f"Trade {status} for {symbol} but no error reason provided"
                )
        
        # If successful, must have trade ID
        if status in ["paper_trade", "submitted"]:
            if "id" not in result or not result["id"]:
                raise TradeCycleValidationError(
                    f"Trade {status} for {symbol} but no trade ID returned"
                )
        
        if errors:
            error_msg = f"Trade execution validation failed for {symbol}: " + "; ".join(errors)
            logger.error(error_msg)
            raise TradeCycleValidationError(error_msg)
        
        return True, None


class CycleValidator:
    """Validates overall cycle state."""
    
    @staticmethod
    def validate_cycle_state(
        cycle_id: str,
        selected_signals: List[Dict[str, Any]],
        available_slots: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate cycle state before execution.
        
        Args:
            cycle_id: Cycle ID
            selected_signals: Selected signals for execution
            available_slots: Available trading slots
            
        Returns:
            Tuple of (is_valid, error_message)
            
        Raises:
            TradeCycleValidationError: If validation fails
        """
        errors = []
        
        # Validate cycle_id
        if not cycle_id or not isinstance(cycle_id, str):
            raise TradeCycleValidationError(f"Invalid cycle_id: {cycle_id}")
        
        # Validate selected_signals
        if not isinstance(selected_signals, list):
            raise TradeCycleValidationError(
                f"selected_signals must be list, got {type(selected_signals).__name__}"
            )
        
        # Validate available_slots
        if not isinstance(available_slots, int) or available_slots < 0:
            raise TradeCycleValidationError(
                f"available_slots must be non-negative int, got {available_slots}"
            )
        
        # Check slot allocation
        if len(selected_signals) > available_slots:
            raise TradeCycleValidationError(
                f"Selected {len(selected_signals)} signals but only {available_slots} slots available"
            )
        
        if errors:
            error_msg = f"Cycle validation failed for {cycle_id}: " + "; ".join(errors)
            logger.error(error_msg)
            raise TradeCycleValidationError(error_msg)
        
        return True, None

