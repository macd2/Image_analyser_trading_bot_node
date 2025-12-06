"""
Position Sizer - Clean position sizing with confidence weighting.
Calculates optimal position size based on risk parameters.
"""

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional

from trading_bot.engine.order_executor import OrderExecutor

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Position sizing calculator with confidence weighting.
    
    Features:
    - Risk-based position sizing
    - Confidence score weighting
    - Minimum value enforcement
    - Instrument-aware quantity rounding
    """
    
    def __init__(
        self,
        order_executor: OrderExecutor,
        risk_percentage: float = 0.01,
        min_position_value: float = 10.0,
        confidence_weighting: bool = True,
        low_conf_threshold: float = 0.70,
        high_conf_threshold: float = 0.85,
        low_conf_weight: float = 0.8,
        high_conf_weight: float = 1.2,
    ):
        """
        Initialize position sizer.
        
        Args:
            order_executor: OrderExecutor for instrument info
            risk_percentage: Base risk per trade (0.01 = 1%)
            min_position_value: Minimum position value in USD
            confidence_weighting: Enable confidence-based sizing
            low_conf_threshold: Threshold for low confidence
            high_conf_threshold: Threshold for high confidence
            low_conf_weight: Weight multiplier for low confidence
            high_conf_weight: Weight multiplier for high confidence
        """
        self.executor = order_executor
        self.risk_percentage = risk_percentage
        self.min_position_value = min_position_value
        self.confidence_weighting = confidence_weighting
        self.low_conf_threshold = low_conf_threshold
        self.high_conf_threshold = high_conf_threshold
        self.low_conf_weight = low_conf_weight
        self.high_conf_weight = high_conf_weight
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        wallet_balance: float,
        confidence: float = 0.75,
        leverage: int = 1,
    ) -> Dict[str, Any]:
        """
        Calculate position size based on risk parameters.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price
            stop_loss: Stop loss price
            wallet_balance: Available wallet balance
            confidence: Confidence score (0-1)
            leverage: Leverage multiplier
            
        Returns:
            Dict with position_size, risk_amount, and calculation details
        """
        # Calculate risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return {"error": "Invalid stop loss - same as entry price"}
        
        # Calculate base risk amount
        base_risk_amount = wallet_balance * self.risk_percentage
        
        # Apply confidence weighting
        confidence_weight = self._get_confidence_weight(confidence)
        adjusted_risk = base_risk_amount * confidence_weight
        
        # Calculate raw position size
        raw_qty = adjusted_risk / risk_per_unit
        
        # Get instrument info for rounding
        instrument = self.executor.get_instrument_info(symbol)
        if "error" in instrument:
            logger.warning(f"Could not get instrument info: {instrument['error']}")
            # Use default rounding
            qty_step = 0.001
            min_qty = 0.001
        else:
            lot_filter = instrument.get("lotSizeFilter", {})
            qty_step = float(lot_filter.get("qtyStep", 0.001))
            min_qty = float(lot_filter.get("minOrderQty", 0.001))
        
        # Round down to valid quantity
        qty = self._round_qty(raw_qty, qty_step)
        
        # Enforce minimum quantity
        if qty < min_qty:
            qty = min_qty
        
        # Calculate position value
        position_value = qty * entry_price
        
        # Enforce minimum position value
        if position_value < self.min_position_value:
            min_qty_for_value = self.min_position_value / entry_price
            qty = self._round_qty(min_qty_for_value, qty_step)
            if qty < min_qty:
                qty = min_qty
            position_value = qty * entry_price
        
        # Calculate actual risk
        actual_risk = qty * risk_per_unit
        actual_risk_pct = actual_risk / wallet_balance if wallet_balance > 0 else 0
        
        return {
            "position_size": qty,
            "position_value": position_value,
            "risk_amount": actual_risk,
            "risk_percentage": actual_risk_pct,
            "confidence_weight": confidence_weight,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "risk_per_unit": risk_per_unit,
        }
    
    def _get_confidence_weight(self, confidence: float) -> float:
        """Calculate confidence weight multiplier."""
        if not self.confidence_weighting:
            return 1.0
        
        if confidence <= self.low_conf_threshold:
            return self.low_conf_weight
        elif confidence >= self.high_conf_threshold:
            return self.high_conf_weight
        else:
            # Linear interpolation
            range_size = self.high_conf_threshold - self.low_conf_threshold
            position = (confidence - self.low_conf_threshold) / range_size
            return self.low_conf_weight + position * (self.high_conf_weight - self.low_conf_weight)
    
    def _round_qty(self, qty: float, step: float) -> float:
        """Round quantity down to valid step size."""
        if step <= 0:
            return qty
        decimal_qty = Decimal(str(qty))
        decimal_step = Decimal(str(step))
        rounded = (decimal_qty / decimal_step).to_integral_value(rounding=ROUND_DOWN) * decimal_step
        return float(rounded)
