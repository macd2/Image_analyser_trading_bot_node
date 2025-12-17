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

from trading_bot.db.client import get_connection, release_connection, query, execute as db_execute

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

    def _validate_trade_timestamps(
        self,
        trade_id: str,
        created_at: str,
        filled_at: Optional[str],
        closed_at: Optional[str]
    ) -> Optional[str]:
        """
        SANITY CHECK: Validate timestamp ordering for trade lifecycle
        Returns error message if validation fails, None if valid
        CRITICAL: A trade must follow this timeline: created_at <= filled_at <= closed_at
        """
        try:
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

            if filled_at:
                filled_dt = datetime.fromisoformat(filled_at.replace('Z', '+00:00'))
                if filled_dt < created_dt:
                    return f"CRITICAL: filled_at ({filled_at}) is BEFORE created_at ({created_at})"

                if closed_at:
                    closed_dt = datetime.fromisoformat(closed_at.replace('Z', '+00:00'))
                    if closed_dt < created_dt:
                        return f"CRITICAL: closed_at ({closed_at}) is BEFORE created_at ({created_at})"
                    if closed_dt < filled_dt:
                        return f"CRITICAL: closed_at ({closed_at}) is BEFORE filled_at ({filled_at})"
            elif closed_at:
                # Trade is closed but never filled - this is invalid
                return "CRITICAL: Trade has closed_at but no filled_at - a trade cannot close without being filled first"

            return None  # All validations passed
        except Exception as e:
            return f"Timestamp validation error: {e}"

    def _log_simulator_error(
        self,
        trade_id: str,
        error_type: str,
        error_message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log error to database for audit trail
        Stores errors in a way that can be queried later for debugging
        """
        self.logger.error(
            f"[SIMULATOR ERROR] Trade {trade_id} - {error_type}: {error_message}",
            extra={"metadata": metadata or {}}
        )
        # TODO: Consider adding a simulator_errors table for persistent error tracking

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

        release_connection(conn)
        return trades
    
    def update_trade_status(self, trade_id: str, updates: Dict[str, Any]) -> bool:
        """Update trade with simulation results"""
        conn = self.get_connection()

        try:
            # SANITY CHECK: Validate timestamps before updating database
            # Get current trade data to check created_at
            current_trade = query(conn, "SELECT created_at, filled_at, closed_at FROM trades WHERE id = ?", (trade_id,))
            if current_trade:
                current_trade = dict(current_trade[0])
                created_at = current_trade.get('created_at')
                filled_at = updates.get('filled_at') or current_trade.get('filled_at')
                closed_at = updates.get('closed_at') or current_trade.get('closed_at')

                # Convert to string if datetime objects
                if created_at and not isinstance(created_at, str):
                    created_at = created_at.isoformat()
                if filled_at and not isinstance(filled_at, str):
                    filled_at = filled_at.isoformat()
                if closed_at and not isinstance(closed_at, str):
                    closed_at = closed_at.isoformat()

                validation_error = self._validate_trade_timestamps(
                    trade_id,
                    created_at,
                    filled_at,
                    closed_at
                )

                if validation_error:
                    self._log_simulator_error(
                        trade_id,
                        'TIMESTAMP_VIOLATION_ON_UPDATE',
                        validation_error,
                        {
                            'updates': updates,
                            'current_trade': current_trade
                        }
                    )
                    self.logger.error(f"SANITY CHECK FAILED for trade {trade_id}: {validation_error}")
                    release_connection(conn)
                    return False  # Do not update database with invalid data

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
            release_connection(conn)
    
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
    
    def simulate_trade(self, trade: Dict[str, Any], candles: List[Candle], strategy: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """
        Simulate a single paper trade through its lifecycle.
        Returns updated trade data or None if no update needed.

        If strategy is provided, uses strategy.should_exit() for strategy-specific exit logic.
        Otherwise falls back to price-level checks (TP/SL).
        """
        if not candles:
            return None

        # CRITICAL: Filter candles to only include those at or after trade creation time
        # A trade cannot be filled before it was created!
        created_at_str = trade.get('created_at')
        if created_at_str:
            # Parse created_at timestamp (could be ISO string or datetime object)
            if isinstance(created_at_str, str):
                created_at_dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            else:
                created_at_dt = created_at_str

            created_at_ms = int(created_at_dt.timestamp() * 1000)

            # Filter to only candles at or after creation time
            candles_after_creation = [c for c in candles if c.timestamp >= created_at_ms]

            if not candles_after_creation:
                # No candles after trade creation - cannot simulate
                logger.debug(f"No candles after trade creation for {trade.get('symbol', 'unknown')}")
                return None

            candles = candles_after_creation

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
                fill_time = datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc).isoformat()
                break

        if not fill_candle:
            # Trade not filled yet
            return None

        # Trade was filled, now check for exit using strategy-specific logic
        candle_idx = candles.index(fill_candle)
        remaining_candles = candles[candle_idx + 1:]

        exit_price = None
        exit_reason = None
        exit_time = None
        exit_details = None
        pnl = None
        pnl_percent = None

        # Use strategy-specific exit logic if available
        if strategy:
            exit_result = self._check_strategy_exit_with_should_exit(trade, remaining_candles, strategy)
            if exit_result:
                exit_price = exit_result["exit_price"]
                exit_reason = exit_result["exit_reason"]
                exit_time = exit_result["exit_time"]
                exit_details = exit_result.get("exit_details")
        else:
            # Fallback to price-level checks (TP/SL)
            for candle in remaining_candles:
                # Check SL
                if self._price_touched(candle, trade['stop_loss'], side):
                    exit_price = trade['stop_loss']
                    exit_reason = 'sl_hit'
                    exit_time = datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc).isoformat()
                    break

                # Check TP
                if self._price_touched(candle, trade['take_profit'], side):
                    exit_price = trade['take_profit']
                    exit_reason = 'tp_hit'
                    exit_time = datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc).isoformat()
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
            'status': 'closed' if exit_price else 'filled',
            'exit_details': exit_details,
        }
    
    def _check_strategy_exit_with_should_exit(self, trade: Dict[str, Any], candles: List[Candle], strategy: Any) -> Optional[Dict[str, Any]]:
        """
        Check for strategy-specific exit conditions using strategy.should_exit().

        For each candle after fill, calls strategy.should_exit() to check if trade should exit.
        Returns exit details when should_exit returns True.
        """
        try:
            # For spread-based strategies, we need pair candles
            # Get pair symbol from strategy_metadata if available
            metadata = trade.get("strategy_metadata", {})
            pair_symbol = metadata.get("pair_symbol")

            for candle in candles:
                # Convert Candle object to dict for strategy
                current_candle_dict = {
                    "timestamp": candle.timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                }

                # For spread-based strategies, fetch pair candle
                pair_candle_dict = None
                if pair_symbol:
                    # TODO: Fetch pair candle from CandleAdapter
                    # For now, we'll pass None and let strategy handle it
                    pair_candle_dict = None

                # Call strategy.should_exit()
                exit_result = strategy.should_exit(
                    trade=trade,
                    current_candle=current_candle_dict,
                    pair_candle=pair_candle_dict,
                )

                # Check if should exit
                if exit_result.get("should_exit"):
                    exit_details = exit_result.get("exit_details", {})
                    reason = exit_details.get("reason", "strategy_exit")

                    return {
                        "exit_price": current_candle_dict["close"],
                        "exit_reason": reason,
                        "exit_time": datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc).isoformat(),
                        "exit_details": exit_details,
                    }

            return None

        except Exception as e:
            logger.error(f"Error in strategy exit check: {e}")
            return None

    @staticmethod
    def _price_touched(candle: Candle, price: float, side: str) -> bool:
        """Check if price was touched in candle"""
        return candle.low <= price <= candle.high

