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

from trading_bot.db.client import get_connection, query, DB_TYPE

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
        # Use DB-specific dry_run comparison (boolean for PostgreSQL, integer for SQLite)
        dry_run_value = 'true' if DB_TYPE == 'postgres' else '1'

        rows = query(conn, f"""
            SELECT * FROM trades
            WHERE dry_run = {dry_run_value}
            AND status IN ('paper_trade', 'pending_fill', 'filled')
            AND pnl IS NULL
            ORDER BY created_at DESC
        """)

        # Convert rows to list of dicts
        trades = []
        for row in rows:
            if DB_TYPE == 'postgres':
                # PostgreSQL returns Row objects with column names
                trades.append(dict(row))
            else:
                # SQLite returns tuples - need to get column names from cursor description
                # For now, just convert to dict assuming row is already dict-like
                trades.append(dict(row) if hasattr(row, 'keys') else row)

        conn.close()
        return trades
    
    def update_trade_status(self, trade_id: str, updates: Dict[str, Any]) -> bool:
        """Update trade with simulation results"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            set_clauses = []
            values = []
            
            for key, value in updates.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)
            
            values.append(trade_id)
            query = f"UPDATE trades SET {', '.join(set_clauses)} WHERE id = ?"
            
            cursor.execute(query, values)
            conn.commit()
            
            return cursor.rowcount > 0
        finally:
            conn.close()
    
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

