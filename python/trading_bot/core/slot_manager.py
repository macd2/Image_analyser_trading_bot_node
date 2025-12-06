"""
Unified Slot Management System for Trading Bot.

This module provides a centralized, consistent slot management system that:
- Defines clear slot counting logic
- Provides cycle-level slot checking
- Manages slot optimization for trade placement
- Ensures consistent slot validation across the entire codebase
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from trading_bot.core.utils import count_open_positions_and_orders


class SlotManager:
    """
    Unified slot management system for consistent slot handling across the bot.

    Slot Definitions:
    - Position slots: Actual open positions that consume trading slots
    - Order slots: Available slots for new entry orders
    - Total occupied slots: position_slots + entry_order_slots
    - Available slots: max_concurrent_trades - occupied_slots
    """

    def __init__(self, trader, data_agent, config):
        """
        Initialize SlotManager with required dependencies.

        Args:
            trader: TradeExecutor instance for API access
            data_agent: DataAgent instance for database access
            config: Configuration object with trading settings
        """
        self.trader = trader
        self.data_agent = data_agent
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Get max concurrent trades from config
        if config.trading is None:
            raise ValueError("Config.trading is None - cannot initialize SlotManager")
        self.max_concurrent_trades = getattr(config.trading, 'max_concurrent_trades')
        if self.max_concurrent_trades is None:
            raise ValueError("max_concurrent_trades is None in config.trading - check config.yaml")
        self.logger.info(f"Initialized SlotManager with max_concurrent_trades: {self.max_concurrent_trades}")

    def get_current_slot_status(self) -> Dict[str, Any]:
        """
        Get comprehensive current slot status using unified counting logic.

        Returns:
            Dict with detailed slot status:
            - max_slots: Maximum allowed concurrent trades
            - occupied_slots: Currently occupied slots (positions + entry orders)
            - available_slots: Available slots for new trades
            - open_positions: Number of open positions
            - entry_orders: Number of open entry orders
            - tp_sl_orders: Number of TP/SL orders (informational only)
            - slot_breakdown: Detailed breakdown of slot usage
        """
        try:
            # Use the centralized counting function for consistency
            count_result = count_open_positions_and_orders(trader=self.trader)

            # Extract counts
            open_positions = count_result.get('active_positions_count',0)
            entry_orders = count_result.get('open_entry_orders_count',0)
            tp_sl_orders = count_result.get('take_profit_orders',0) + count_result.get('stop_loss_orders',0)

            # Calculate slot usage - BOTH positions AND entry orders consume slots
            occupied_slots = open_positions + entry_orders
            available_slots = self.max_concurrent_trades - occupied_slots

            slot_status = {
                "max_slots": self.max_concurrent_trades,
                "occupied_slots": occupied_slots,
                "available_slots": available_slots,
                "open_positions": open_positions,
                "entry_orders": entry_orders,
                "tp_sl_orders": tp_sl_orders,
                "slot_breakdown": {
                    "positions": open_positions,
                    "entry_orders": entry_orders,
                    "tp_sl_orders": tp_sl_orders,
                    "total_occupied": occupied_slots,
                    "total_available": available_slots
                },
                "utilization_percentage": (occupied_slots / self.max_concurrent_trades) * 100 if self.max_concurrent_trades > 0 else 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            self.logger.debug(f"Slot status: {occupied_slots}/{self.max_concurrent_trades} occupied, {available_slots} available")
            return slot_status

        except Exception as e:
            self.logger.error(f"Error getting current slot status: {e}")
            # Return safe fallback values
            return {
                "max_slots": self.max_concurrent_trades,
                "occupied_slots": self.max_concurrent_trades,  # Assume fully occupied on error
                "available_slots": 0,
                "open_positions": 0,
                "entry_orders": 0,
                "tp_sl_orders": 0,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def should_skip_cycle_due_to_slots(self, timeframe: str, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if we should skip the entire cycle due to slot exhaustion.

        This implements the core logic requested:
        1. Check if analyzer data exists in DB for current cycle
        2. If yes, check if open positions >= max_concurrent_trades
        3. If slots are full, skip the entire cycle
        4. If not, run the cycle

        Args:
            timeframe: Trading timeframe (e.g., "15m", "1h", "4h")
            current_time: Current UTC time (default: now)

        Returns:
            Tuple of (should_skip: bool, reason: str)
        """
        try:
            # STEP 2: Get current slot status
            slot_status = self.get_current_slot_status()
            open_positions = slot_status.get('open_positions', 0)
            entry_orders = slot_status.get('entry_orders', 0)
            available_slots = slot_status.get('available_slots', 0)

            # STEP 3: Check if slots are exhausted using correct logic:
            # 1. If open_positions = max_concurrent_trades → No new trades, skip cycle
            # 2. If open_positions + open_entry_orders > max_concurrent_trades → No new orders and cancel existing entry orders

            total_occupied = open_positions + entry_orders

            if open_positions >= self.max_concurrent_trades:
                reason = f"Position limit reached: {open_positions}/{self.max_concurrent_trades} positions open, no new trades allowed"
                self.logger.warning(f"🚫 SKIPPING CYCLE: {reason}")
                return True, reason

            if total_occupied > self.max_concurrent_trades:
                reason = f"Total occupied slots exceeded: {total_occupied}/{self.max_concurrent_trades} (positions + entry orders)"
                self.logger.warning(f"🚫 SKIPPING CYCLE: {reason}")
                return True, reason

            # STEP 4: Check if we can still replace orders (different from available slots for new orders)
            can_replace_orders = total_occupied <= self.max_concurrent_trades

            if can_replace_orders:
                # We can replace orders - proceed with cycle to allow intelligent replacement
                self.logger.info(f"✅ CAN REPLACE ORDERS: {total_occupied}/{self.max_concurrent_trades} occupied - proceeding with cycle for order replacement")
                return False, f"Can replace orders ({total_occupied}/{self.max_concurrent_trades} occupied) - proceeding with cycle"
            else:
                # Should not reach here due to check above, but being safe
                reason = f"Cannot replace orders: {total_occupied}/{self.max_concurrent_trades} occupied"
                self.logger.warning(f"🚫 SKIPPING CYCLE: {reason}")
                return True, reason

        except Exception as e:
            self.logger.error(f"Error checking cycle slot status: {e}")
            # On error, be conservative and skip the cycle to prevent over-trading
            return True, f"Error checking slot status: {str(e)} - skipping cycle for safety"

    def get_available_order_slots(self) -> Tuple[int, Dict[str, Any]]:
        """
        Get the number of available order slots for new trades.

        Available order slots = max_concurrent_trades - open_positions
        This represents slots available for new entry orders.

        Returns:
            Tuple of (available_order_slots: int, slot_details: dict)
        """
        try:
            slot_status = self.get_current_slot_status()
            open_positions = slot_status.get('open_positions', 0)

            # Available order slots = max_concurrent_trades - open_positions
            # This is different from available_slots which includes entry orders
            available_order_slots = max(0, self.max_concurrent_trades - open_positions)

            slot_details = {
                "max_concurrent_trades": self.max_concurrent_trades,
                "open_positions": open_positions,
                "available_order_slots": available_order_slots,
                "current_entry_orders": slot_status.get('entry_orders', 0),
                "total_occupied_slots": slot_status.get('occupied_slots', 0),
                "slot_breakdown": slot_status.get('slot_breakdown', {})
            }

            self.logger.debug(f"Available order slots: {available_order_slots}/{self.max_concurrent_trades} (open positions: {open_positions})")
            return available_order_slots, slot_details

        except Exception as e:
            self.logger.error(f"Error getting available order slots: {e}")
            return 0, {"error": str(e)}

    def validate_slot_availability_for_trade(self, symbol: str, timeframe: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate if a trade can be placed based on slot availability.

        Args:
            symbol: Trading symbol
            timeframe: Trading timeframe

        Returns:
            Tuple of (can_trade: bool, reason: str, slot_info: dict)
        """
        try:
            slot_status = self.get_current_slot_status()
            available_slots = slot_status.get('available_slots', 0)
            open_positions = slot_status.get('open_positions', 0)

            # DEBUG: Log current state for duplicate investigation
            self.logger.info(f"🔍 SLOT VALIDATION for {symbol}: positions={open_positions}, available={available_slots}")

            # Check if symbol already has an open position
            has_position = self._symbol_has_open_position(symbol)
            self.logger.info(f"🔍 POSITION CHECK for {symbol}: has_open_position={has_position}")

            if has_position:
                self.logger.warning(f"🚫 DUPLICATE PREVENTION: Symbol {symbol} already has an open position")
                return False, f"Symbol {symbol} already has an open position", slot_status

            # Check if slots are available
            if available_slots <= 0:
                self.logger.warning(f"🚫 SLOT EXHAUSTION: No slots available ({slot_status.get('occupied_slots', 0)}/{self.max_concurrent_trades} occupied)")
                return False, f"No slots available ({slot_status.get('occupied_slots', 0)}/{self.max_concurrent_trades} occupied)", slot_status

            self.logger.info(f"✅ SLOT AVAILABLE for {symbol}: {available_slots}/{self.max_concurrent_trades} slots free")
            return True, f"Slot available ({available_slots}/{self.max_concurrent_trades} available)", slot_status

        except Exception as e:
            self.logger.error(f"Error validating slot availability for {symbol}: {e}")
            return False, f"Error validating slots: {str(e)}", {}

    def _symbol_has_open_position(self, symbol: str) -> bool:
        """
        Check if a symbol already has an open position.

        Args:
            symbol: Trading symbol to check

        Returns:
            True if symbol has open position, False otherwise
        """
        try:
            # Use the trader's position checking method
            return self.trader.has_open_position(symbol)
        except Exception as e:
            self.logger.error(f"Error checking position for {symbol}: {e}")
            return False

    def log_slot_status_summary(self, context: str = "") -> None:
        """
        Log a comprehensive slot status summary.

        Args:
            context: Optional context string for logging
        """
        try:
            slot_status = self.get_current_slot_status()

            context_str = f" [{context}]" if context else ""
            self.logger.info(f"📊 SLOT STATUS SUMMARY{context_str}:")
            self.logger.info(f"   Max Concurrent Trades: {slot_status.get('max_slots', 0)}")
            self.logger.info(f"   Occupied Slots: {slot_status.get('occupied_slots', 0)}")
            self.logger.info(f"   Available Slots: {slot_status.get('available_slots', 0)}")
            self.logger.info(f"   Open Positions: {slot_status.get('open_positions', 0)}")
            self.logger.info(f"   Entry Orders: {slot_status.get('entry_orders', 0)}")
            self.logger.info(f"   TP/SL Orders: {slot_status.get('tp_sl_orders', 0)}")
            self.logger.info(f"   Utilization: {slot_status.get('utilization_percentage', 0):.1f}%")

        except Exception as e:
            self.logger.error(f"Error logging slot status summary: {e}")

    def get_slot_optimization_info(self) -> Dict[str, Any]:
        """
        Get information needed for slot optimization decisions.

        Returns:
            Dict with slot optimization data:
            - available_order_slots: Slots available for new orders
            - current_positions: Current open positions
            - current_entry_orders: Current entry orders
            - slot_pressure: How close we are to slot limits
        """
        try:
            slot_status = self.get_current_slot_status()
            available_order_slots, order_slot_details = self.get_available_order_slots()

            slot_pressure = "low"
            if slot_status.get('utilization_percentage', 0) >= 80:
                slot_pressure = "high"
            elif slot_status.get('utilization_percentage', 0) >= 60:
                slot_pressure = "medium"

            return {
                "available_order_slots": available_order_slots,
                "current_positions": slot_status.get('open_positions', 0),
                "current_entry_orders": slot_status.get('entry_orders', 0),
                "slot_pressure": slot_pressure,
                "utilization_percentage": slot_status.get('utilization_percentage', 0),
                "max_concurrent_trades": self.max_concurrent_trades,
                "slot_details": order_slot_details
            }

        except Exception as e:
            self.logger.error(f"Error getting slot optimization info: {e}")
            return {
                "available_order_slots": 0,
                "current_positions": 0,
                "current_entry_orders": 0,
                "slot_pressure": "unknown",
                "error": str(e)
            }
