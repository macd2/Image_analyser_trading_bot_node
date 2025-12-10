"""
Trade Tracker - Lifecycle tracking for trades from submission to close.
Tracks trade state transitions and calculates realized P&L.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

from trading_bot.core.state_manager import OrderState, ExecutionRecord
from trading_bot.db.client import execute

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """Trade lifecycle status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class TradeRecord:
    """Complete trade record."""
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    quantity: float
    status: TradeStatus
    order_id: Optional[str] = None
    fill_price: Optional[float] = None
    fill_quantity: Optional[float] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class TradeTracker:
    """
    Tracks trade lifecycle from submission to close.
    
    Features:
    - Real-time status updates from WebSocket
    - P&L calculation on close
    - Database persistence
    """
    
    def __init__(self, db_connection: Optional[sqlite3.Connection] = None):
        """
        Initialize trade tracker.
        
        Args:
            db_connection: SQLite connection for persistence
        """
        self._db = db_connection
        self._trades: Dict[str, TradeRecord] = {}  # trade_id -> TradeRecord
        self._order_to_trade: Dict[str, str] = {}  # order_id -> trade_id
    
    def register_trade(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        order_id: Optional[str] = None,
    ) -> TradeRecord:
        """Register a new trade for tracking."""
        trade = TradeRecord(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            status=TradeStatus.SUBMITTED if order_id else TradeStatus.PENDING,
            order_id=order_id,
            created_at=datetime.now(timezone.utc),
        )
        
        self._trades[trade_id] = trade
        
        if order_id:
            self._order_to_trade[order_id] = trade_id
        
        logger.debug(f"Trade registered: {trade_id} ({symbol})")
        return trade
    
    def on_order_update(self, order: OrderState) -> None:
        """Handle order update from WebSocket."""
        trade_id = self._order_to_trade.get(order.order_id)
        if not trade_id:
            return
        
        trade = self._trades.get(trade_id)
        if not trade:
            return
        
        # Update status based on order status
        status_map = {
            "New": TradeStatus.SUBMITTED,
            "PartiallyFilled": TradeStatus.PARTIALLY_FILLED,
            "Filled": TradeStatus.FILLED,
            "Cancelled": TradeStatus.CANCELLED,
            "Rejected": TradeStatus.ERROR,
        }
        
        new_status = status_map.get(order.status)
        if new_status:
            trade.status = new_status
        
        # Update fill info
        if order.filled_qty > 0:
            trade.fill_quantity = order.filled_qty
            trade.fill_price = order.avg_price
            
            if order.status == "Filled":
                trade.filled_at = datetime.now(timezone.utc)
        
        self._persist_trade(trade)
    
    def on_execution(self, execution: ExecutionRecord) -> None:
        """Handle execution from WebSocket."""
        trade_id = self._order_to_trade.get(execution.order_id)
        if not trade_id:
            return
        
        trade = self._trades.get(trade_id)
        if not trade:
            return
        
        # Update with execution details
        trade.fill_price = execution.exec_price
        trade.fill_quantity = (trade.fill_quantity or 0) + execution.exec_qty
        
        # Check if this is a closing execution (has PnL)
        if execution.exec_pnl != 0:
            trade.pnl = execution.exec_pnl
            trade.exit_price = execution.exec_price
            trade.status = TradeStatus.CLOSED
            trade.closed_at = datetime.now(timezone.utc)
            
            # Calculate P&L percent
            if trade.entry_price and trade.quantity:
                position_value = trade.entry_price * trade.quantity
                if position_value > 0:
                    trade.pnl_percent = round((trade.pnl / position_value) * 100, 3)
            
            logger.info(
                f"Trade closed: {trade.symbol} PnL: {trade.pnl:.2f} "
                f"({trade.pnl_percent:.2f}%)"
            )
            # Update run aggregates
            self._update_run_aggregates_on_trade_close(trade.trade_id, trade.pnl)
        
        self._persist_trade(trade)
    
    def _persist_trade(self, trade: TradeRecord) -> None:
        """Persist trade to database."""
        if not self._db:
            return
        
        try:
            execute(self._db, """
                UPDATE trades SET
                    status = ?,
                    fill_price = ?,
                    fill_quantity = ?,
                    exit_price = ?,
                    pnl = ?,
                    pnl_percent = ?,
                    filled_at = ?,
                    closed_at = ?
                WHERE id = ?
            """, (
                trade.status.value,
                trade.fill_price,
                trade.fill_quantity,
                trade.exit_price,
                trade.pnl,
                trade.pnl_percent,
                trade.filled_at.isoformat() if trade.filled_at else None,
                trade.closed_at.isoformat() if trade.closed_at else None,
                trade.trade_id,
            ))
            self._db.commit()
        except Exception as e:
            logger.error(f"Failed to persist trade: {e}")
    
    def _update_run_aggregates_on_trade_close(self, trade_id: str, pnl: float) -> None:
        """Update run aggregates (win_count, loss_count, total_pnl) when a trade closes."""
        if not self._db:
            return
        try:
            is_win = pnl > 0
            is_loss = pnl < 0
            execute(self._db, """
                UPDATE runs
                SET total_pnl = total_pnl + ?,
                    win_count = win_count + ?,
                    loss_count = loss_count + ?
                WHERE id = (
                    SELECT run_id FROM trades WHERE id = ?
                )
            """, (pnl, 1 if is_win else 0, 1 if is_loss else 0, trade_id))
            self._db.commit()
            logger.debug(f"Updated run aggregates for trade {trade_id} (pnl: {pnl})")
        except Exception as e:
            logger.error(f"Failed to update run aggregates: {e}")

    def get_trade(self, trade_id: str) -> Optional[TradeRecord]:
        """Get trade by ID."""
        return self._trades.get(trade_id)
    
    def get_open_trades(self) -> List[TradeRecord]:
        """Get all open trades."""
        return [
            t for t in self._trades.values()
            if t.status not in (TradeStatus.CLOSED, TradeStatus.CANCELLED, TradeStatus.ERROR)
        ]
