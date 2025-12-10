"""
Paper Trade Simulator - Simulates paper trades by checking candle data
and updating trade outcomes as if they were live trades.

This module:
1. Fetches all paper trades from the database
2. For each paper trade, checks if it would have been filled at entry price
3. Tracks the trade through its lifecycle (entry -> exit)
4. Updates trade data with fill prices, exit prices, and P&L
5. Runs as a background process checking on each candle interval
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

from trading_bot.db.client import get_connection, query, execute as db_execute

logger = logging.getLogger(__name__)


class TradeSimulationStatus(Enum):
    """Status of a simulated trade"""
    PENDING_FILL = "pending_fill"  # Waiting for entry price to be hit
    FILLED = "filled"  # Entry price was hit, now tracking exit
    CLOSED = "closed"  # Trade closed (TP/SL hit)
    CANCELLED = "cancelled"  # Trade cancelled


@dataclass
class Candle:
    """OHLC candle data"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class PaperTradeSimulator:
    """Simulates paper trades using historical candle data"""

    def __init__(self, db_path: str = None):
        # Note: db_path parameter kept for backward compatibility but ignored
        # We now use centralized database client
        self.logger = logger

    def get_connection(self):
        """Get database connection using centralized client"""
        return get_connection()
    
    def get_paper_trades(self) -> List[Dict[str, Any]]:
        """Get all paper trades that need simulation"""
        conn = self.get_connection()

        # Get paper trades that are still open (status = 'paper_trade' or 'pending_fill')
        # Both SQLite and PostgreSQL now accept boolean values directly
        rows = query(conn, """
            SELECT * FROM trades
            WHERE dry_run = ?
            AND status IN ('paper_trade', 'pending_fill', 'filled')
            AND pnl IS NULL
            ORDER BY created_at DESC
        """, (True,))

        # Convert rows to list of dicts (both databases return dict-like rows)
        trades = [dict(row) for row in rows]

        conn.close()
        return trades
    
    def update_trade_status(self, trade_id: str, updates: Dict[str, Any]) -> bool:
        """Update trade with simulation results"""
        conn = self.get_connection()

        try:
            set_clauses = []
            values = []

            for key, value in updates.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)

            values.append(trade_id)
            query_str = f"UPDATE trades SET {', '.join(set_clauses)} WHERE id = ?"

            # Use centralized db_execute to handle SQLite/PostgreSQL placeholder conversion
            rows_affected = db_execute(conn, query_str, tuple(values))
            
            # If trade is being closed (status = 'closed' and pnl is set), update run aggregates
            if updates.get('status') == 'closed' and updates.get('pnl') is not None:
                self._update_run_aggregates_on_trade_close(conn, trade_id, updates['pnl'])
            
            conn.commit()

            return rows_affected > 0
        finally:
            conn.close()
    
    def _update_run_aggregates_on_trade_close(self, conn, trade_id: str, pnl: float) -> None:
        """Update run aggregates (win_count, loss_count, total_pnl) when a paper trade closes."""
        try:
            is_win = pnl > 0
            is_loss = pnl < 0
            db_execute(conn, """
                UPDATE runs
                SET total_pnl = total_pnl + ?,
                    win_count = win_count + ?,
                    loss_count = loss_count + ?
                WHERE id = (
                    SELECT run_id FROM trades WHERE id = ?
                )
            """, (pnl, 1 if is_win else 0, 1 if is_loss else 0, trade_id))
            # No commit here, let the caller commit
            logger.debug(f"Updated run aggregates for paper trade {trade_id} (pnl: {pnl})")
        except Exception as e:
            logger.error(f"Failed to update run aggregates for paper trade: {e}")
    
    def simulate_trade(self, trade: Dict[str, Any], candles: List[Candle]) -> Optional[Dict[str, Any]]:
        """
        Simulate a single paper trade through its lifecycle.
        Returns updated trade data or None if no update needed.
        """
        if not candles:
            return None
        
        # Check if trade was filled
        entry_price = trade['entry_price']
        side = trade['side']
        
        # Find fill candle (first candle where price touches entry)
        fill_candle = None
        fill_price = None
        fill_time = None
        
        for candle in candles:
            if self._price_touched(candle, entry_price, side):
                fill_candle = candle
                fill_price = entry_price
                fill_time = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc).isoformat()
                break
        
        if not fill_candle:
            # Trade not filled yet
            return None
        
        # Trade was filled, now check for exit (TP/SL)
        candle_idx = candles.index(fill_candle)
        remaining_candles = candles[candle_idx + 1:]
        
        exit_price = None
        exit_reason = None
        exit_time = None
        pnl = None
        pnl_percent = None
        
        for candle in remaining_candles:
            # Check SL
            if self._price_touched(candle, trade['stop_loss'], side):
                exit_price = trade['stop_loss']
                exit_reason = 'sl_hit'
                exit_time = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc).isoformat()
                break
            
            # Check TP
            if self._price_touched(candle, trade['take_profit'], side):
                exit_price = trade['take_profit']
                exit_reason = 'tp_hit'
                exit_time = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc).isoformat()
                break
        
        # Calculate P&L if trade closed
        if exit_price:
            qty = trade.get('quantity', 1)
            if side == 'Buy':
                pnl = (exit_price - fill_price) * qty
            else:  # Sell
                pnl = (fill_price - exit_price) * qty
            
            pnl_percent = (pnl / (fill_price * qty)) * 100 if fill_price > 0 else 0
        
        return {
            'fill_price': fill_price,
            'fill_time': fill_time,
            'filled_at': fill_time,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'exit_time': exit_time,
            'closed_at': exit_time,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'status': 'closed' if exit_price else 'filled'
        }
    
    @staticmethod
    def _price_touched(candle: Candle, price: float, side: str) -> bool:
        """Check if price was touched in candle"""
        return candle.low <= price <= candle.high

