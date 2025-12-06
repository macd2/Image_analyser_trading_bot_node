"""
DEPRECATED: This file is deprecated and replaced by enhanced_position_monitor.py

Position Monitor - Event-driven position monitoring with SL tightening.
Monitors positions via WebSocket and applies RR-based stop loss tightening.

⚠️ DO NOT USE - Use EnhancedPositionMonitor instead!
The enhanced version includes all features from this monitor PLUS:
- TP proximity trailing stops
- Age-based tightening
- Age-based order cancellation
- Full audit trail logging with instance_id/run_id/trade_id

See: trading_bot/engine/enhanced_position_monitor.py
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from trading_bot.core.state_manager import PositionState
from trading_bot.engine.order_executor import OrderExecutor

logger = logging.getLogger(__name__)


@dataclass
class TighteningStep:
    """RR tightening step configuration."""
    threshold: float  # RR threshold to trigger (e.g., 2.0 = 2R profit)
    sl_position: float  # New SL position as RR (e.g., 1.2 = lock in 1.2R)


class PositionMonitor:
    """
    Event-driven position monitor with SL tightening.
    
    Features:
    - Real-time position monitoring via WebSocket callbacks
    - RR-based stop loss tightening
    - Trade lifecycle tracking
    """
    
    DEFAULT_TIGHTENING_STEPS = [
        TighteningStep(threshold=2.0, sl_position=1.2),
        TighteningStep(threshold=2.5, sl_position=2.0),
        TighteningStep(threshold=3.0, sl_position=2.5),
    ]
    
    def __init__(
        self,
        order_executor: OrderExecutor,
        tightening_enabled: bool = True,
        tightening_steps: Optional[List[TighteningStep]] = None,
    ):
        """
        Initialize position monitor.
        
        Args:
            order_executor: OrderExecutor for modifying stops
            tightening_enabled: Enable SL tightening
            tightening_steps: Custom tightening steps
        """
        self.executor = order_executor
        self.tightening_enabled = tightening_enabled
        self.tightening_steps = tightening_steps or self.DEFAULT_TIGHTENING_STEPS
        
        # Track position state for tightening
        self._position_state: Dict[str, Dict] = {}  # symbol -> state
    
    def on_position_update(self, position: PositionState) -> None:
        """
        Handle position update from WebSocket.
        Called by StateManager when position changes.
        """
        symbol = position.symbol
        
        # Skip empty positions
        if position.size == 0 or not position.side:
            if symbol in self._position_state:
                logger.info(f"Position closed: {symbol}")
                del self._position_state[symbol]
            return
        
        # Initialize or update position state
        if symbol not in self._position_state:
            self._position_state[symbol] = {
                "entry_price": position.entry_price,
                "original_sl": position.stop_loss,
                "current_sl": position.stop_loss,
                "side": position.side,
                "last_tightening_step": -1,
            }
            logger.info(f"Tracking new position: {symbol} {position.side}")
        
        # Check for tightening
        if self.tightening_enabled:
            self._check_tightening(position)
    
    def _check_tightening(self, position: PositionState) -> None:
        """Check if position qualifies for SL tightening."""
        symbol = position.symbol
        state = self._position_state.get(symbol)
        
        if not state or not state.get("entry_price"):
            return
        
        entry = state["entry_price"]
        original_sl = state.get("original_sl") or position.stop_loss
        current_price = position.mark_price
        
        if not all([entry, original_sl, current_price]):
            return
        
        # Calculate current RR
        risk = abs(entry - original_sl)
        if risk == 0:
            return
        
        # Calculate profit in R
        if position.side == "Buy":
            profit = current_price - entry
        else:
            profit = entry - current_price
        
        current_rr = profit / risk
        
        # Check each tightening step
        last_step = state.get("last_tightening_step", -1)
        
        for i, step in enumerate(self.tightening_steps):
            if i <= last_step:
                continue  # Already applied this step
            
            if current_rr >= step.threshold:
                # Calculate new SL
                new_sl = self._calculate_new_sl(
                    entry, original_sl, position.side, step.sl_position
                )
                
                # Apply tightening
                result = self._apply_tightening(symbol, new_sl, step)
                
                if result:
                    state["last_tightening_step"] = i
                    state["current_sl"] = new_sl
                    
                    logger.info(
                        f"🔒 SL TIGHTENED: {symbol} at {step.threshold}R -> "
                        f"SL moved to {step.sl_position}R ({new_sl:.4f})"
                    )
    
    def _calculate_new_sl(
        self,
        entry: float,
        original_sl: float,
        side: str,
        sl_position: float,
    ) -> float:
        """Calculate new SL price based on RR position."""
        risk = abs(entry - original_sl)
        
        if side == "Buy":
            # Long: SL is below entry
            return entry + (risk * sl_position)
        else:
            # Short: SL is above entry
            return entry - (risk * sl_position)
    
    def _apply_tightening(
        self,
        symbol: str,
        new_sl: float,
        step: TighteningStep,
    ) -> bool:
        """Apply SL tightening to position."""
        result = self.executor.set_trading_stop(
            symbol=symbol,
            stop_loss=new_sl,
        )
        
        if "error" in result:
            logger.error(f"Failed to tighten SL for {symbol}: {result['error']}")
            return False
        
        return True
    
    def get_position_state(self, symbol: str) -> Optional[Dict]:
        """Get tracked state for a position."""
        return self._position_state.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Dict]:
        """Get all tracked positions."""
        return self._position_state.copy()
