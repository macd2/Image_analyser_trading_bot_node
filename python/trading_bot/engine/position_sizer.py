"""
Position Sizer - Clean position sizing with confidence weighting and Kelly Criterion.
Calculates optimal position size based on risk parameters.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, List

import numpy as np

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
        max_loss_usd: float = 0.0,
        confidence_weighting: bool = True,
        low_conf_threshold: float = 0.70,
        high_conf_threshold: float = 0.85,
        low_conf_weight: float = 0.8,
        high_conf_weight: float = 1.2,
        use_kelly_criterion: bool = False,
        kelly_fraction: float = 0.3,
        kelly_window: int = 30,
    ):
        """
        Initialize position sizer.

        Args:
            order_executor: OrderExecutor for instrument info
            risk_percentage: Base risk per trade (0.01 = 1%)
            min_position_value: Minimum position value in USD
            max_loss_usd: Maximum USD risk per trade (0 = disabled)
            confidence_weighting: Enable confidence-based sizing
            low_conf_threshold: Threshold for low confidence
            high_conf_threshold: Threshold for high confidence
            low_conf_weight: Weight multiplier for low confidence
            high_conf_weight: Weight multiplier for high confidence
            use_kelly_criterion: Enable Kelly Criterion for dynamic sizing
            kelly_fraction: Fractional Kelly multiplier (0.3 = 30% of full Kelly)
            kelly_window: Number of recent trades to analyze for Kelly
        """
        self.executor = order_executor
        self.risk_percentage = risk_percentage
        self.min_position_value = min_position_value
        self.max_loss_usd = max_loss_usd
        self.confidence_weighting = confidence_weighting
        self.low_conf_threshold = low_conf_threshold
        self.high_conf_threshold = high_conf_threshold
        self.low_conf_weight = low_conf_weight
        self.high_conf_weight = high_conf_weight
        self.use_kelly_criterion = use_kelly_criterion
        self.kelly_fraction = kelly_fraction
        self.kelly_window = kelly_window
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        wallet_balance: float,
        confidence: float = 0.75,
        leverage: int = 1,
        trade_history: Optional[List[Dict[str, Any]]] = None,
        strategy: Optional[Any] = None,
        position_size_multiplier: float = 1.0,
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
            trade_history: Optional list of closed trades for Kelly Criterion
            strategy: Optional strategy instance for strategy-specific risk metrics
            position_size_multiplier: Position size multiplier (0.5-1.5) from strategy

        Returns:
            Dict with position_size, risk_amount, and calculation details
        """
        # Calculate risk per unit using strategy-specific method if available
        if strategy:
            # Create a minimal signal dict for strategy risk calculation
            signal = {
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "recommendation": "LONG",  # Placeholder, will be overridden by actual signal
            }
            risk_metrics = strategy.calculate_risk_metrics(signal)
            if "error" in risk_metrics:
                return risk_metrics
            risk_per_unit = risk_metrics.get("risk_per_unit", abs(entry_price - stop_loss))
        else:
            # Fallback to basic calculation
            risk_per_unit = abs(entry_price - stop_loss)

        if risk_per_unit == 0:
            return {"error": "Invalid stop loss - same as entry price"}

        # Determine risk percentage (Kelly or fixed)
        kelly_metrics = None
        if self.use_kelly_criterion and trade_history:
            risk_pct = self.calculate_kelly_fraction(trade_history)
            sizing_method = "kelly"
            # Capture kelly metrics for traceability
            kelly_metrics = self._calculate_kelly_metrics(trade_history)
        else:
            risk_pct = self.risk_percentage
            sizing_method = "fixed"

        # Calculate base risk amount
        base_risk_amount = wallet_balance * risk_pct

        # Apply confidence weighting
        confidence_weight = self._get_confidence_weight(confidence)

        # Apply position size multiplier (0.5-1.5 range)
        # Clamp to valid range for safety
        clamped_multiplier = max(0.5, min(1.5, position_size_multiplier))

        # Combine both adjustments
        adjusted_risk = base_risk_amount * confidence_weight * clamped_multiplier
        
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

        # Enforce maximum loss cap (if enabled, i.e., > 0)
        if self.max_loss_usd > 0 and actual_risk > self.max_loss_usd:
            logger.info(f"Risk capped: ${actual_risk:.2f} → ${self.max_loss_usd:.2f} (max_loss_usd)")
            # Recalculate quantity based on max loss cap
            qty = self._round_qty(self.max_loss_usd / risk_per_unit, qty_step)
            if qty < min_qty:
                qty = min_qty
            position_value = qty * entry_price
            actual_risk = qty * risk_per_unit
            actual_risk_pct = actual_risk / wallet_balance if wallet_balance > 0 else 0

        result = {
            "position_size": float(qty),
            "position_value": float(position_value),
            "risk_amount": float(actual_risk),
            "risk_percentage": float(actual_risk_pct),
            "confidence_weight": float(confidence_weight),
            "entry_price": float(entry_price),
            "stop_loss": float(stop_loss),
            "risk_per_unit": float(risk_per_unit),
            "sizing_method": sizing_method,
            "risk_pct_used": float(risk_pct),
        }

        # Add kelly metrics if available for traceability
        if kelly_metrics:
            result["kelly_metrics"] = kelly_metrics

        return result
    
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

    def _calculate_kelly_metrics(self, trade_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate kelly metrics for traceability.

        Args:
            trade_history: List of closed trades with 'pnl_percent' field

        Returns:
            Dict with kelly metrics for storage
        """
        if not trade_history or len(trade_history) < 10:
            return {
                "kelly_fraction_used": self.risk_percentage,
                "win_rate": 0,
                "avg_win_percent": 0,
                "avg_loss_percent": 0,
                "trade_history_count": len(trade_history) if trade_history else 0,
                "kelly_calculation_timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Get recent trades within window
        recent = trade_history[-self.kelly_window:]

        # Separate wins and losses
        wins = [t for t in recent if t.get('pnl_percent', 0) > 0]
        losses = [t for t in recent if t.get('pnl_percent', 0) < 0]

        # Calculate metrics
        win_rate = len(wins) / len(recent) if recent else 0
        avg_win = float(np.mean([t.get('pnl_percent', 0) for t in wins])) if wins else 0
        avg_loss = float(abs(np.mean([t.get('pnl_percent', 0) for t in losses]))) if losses else 0

        return {
            "kelly_fraction_used": self.kelly_fraction,
            "win_rate": float(win_rate),
            "avg_win_percent": float(avg_win),
            "avg_loss_percent": float(avg_loss),
            "trade_history_count": len(recent),
            "kelly_calculation_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def calculate_kelly_fraction(self, trade_history: List[Dict[str, Any]]) -> float:
        """
        Calculate Kelly Criterion fraction from trade history.

        Kelly Criterion formula: f* = (b*p - q) / b
        where:
            p = win probability
            q = loss probability (1 - p)
            b = average win / average loss ratio
            f* = optimal fraction of capital to risk

        Args:
            trade_history: List of closed trades with 'pnl_percent' field

        Returns:
            Kelly fraction (0-0.5), or fallback risk_percentage if insufficient data
        """
        if not trade_history or len(trade_history) < 10:
            logger.info(f"Kelly Criterion: Insufficient trade history ({len(trade_history) if trade_history else 0} trades), falling back to fixed risk ({self.risk_percentage:.2%})")
            return self.risk_percentage

        # Get recent trades within window
        recent = trade_history[-self.kelly_window:]

        # Separate wins and losses
        wins = [t for t in recent if t.get('pnl_percent', 0) > 0]
        losses = [t for t in recent if t.get('pnl_percent', 0) < 0]

        # Need at least some wins and losses for meaningful calculation
        if not wins or not losses:
            logger.info(f"Kelly Criterion: No wins or losses in recent {len(recent)} trades, falling back to fixed risk ({self.risk_percentage:.2%})")
            return self.risk_percentage

        # Calculate probabilities
        p = len(wins) / len(recent)  # Win probability
        q = 1 - p  # Loss probability

        # Calculate average win/loss (as percentages)
        avg_win = float(np.mean([t.get('pnl_percent', 0) for t in wins]))
        avg_loss = float(abs(np.mean([t.get('pnl_percent', 0) for t in losses])))

        # Avoid division by zero
        if avg_loss <= 0:
            logger.info("Kelly Criterion: Average loss is zero or negative, falling back to fixed risk")
            return self.risk_percentage

        # Calculate win/loss ratio
        b = avg_win / avg_loss

        # Calculate full Kelly fraction
        f_star = (b * p - q) / b

        # Clip to safe range (0 to 50%) and convert to Python float
        f_star = float(np.clip(f_star, 0, 0.5))

        # Apply fractional Kelly for safety and convert to Python float
        kelly_risk = float(self.kelly_fraction * f_star)

        logger.info(
            f"Kelly Criterion Calculation: "
            f"Trades={len(recent)}, Wins={len(wins)}, Losses={len(losses)}, "
            f"WinRate={p:.2%}, AvgWin={avg_win:.2f}%, AvgLoss={avg_loss:.2f}%, "
            f"WinLossRatio={b:.2f}, FullKelly={f_star:.2%}, "
            f"FractionalKelly({self.kelly_fraction})={kelly_risk:.2%}"
        )

        return kelly_risk
