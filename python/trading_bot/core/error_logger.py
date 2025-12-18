"""
Error Logger - Stores ERROR and CRITICAL logs to database for debugging.
Only captures failures to keep the log trail focused and queryable.
"""

import logging
import traceback
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from contextvars import ContextVar

# Import centralized database client
from trading_bot.db.client import get_connection, release_connection, execute, DB_TYPE

# Context variables for correlation IDs
_current_run_id: ContextVar[Optional[str]] = ContextVar('run_id', default=None)
_current_cycle_id: ContextVar[Optional[str]] = ContextVar('cycle_id', default=None)


def set_run_id(run_id: str) -> None:
    """Set the current run ID for error correlation."""
    _current_run_id.set(run_id)


def set_cycle_id(cycle_id: str) -> None:
    """Set the current cycle ID for error correlation."""
    _current_cycle_id.set(cycle_id)


def clear_cycle_id() -> None:
    """Clear cycle ID after cycle completes."""
    _current_cycle_id.set(None)


class DatabaseErrorHandler(logging.Handler):
    """
    Logging handler that stores ERROR, WARNING, and CRITICAL logs to database.
    Uses centralized database client (auto-detects SQLite/PostgreSQL).
    Captures stack traces and context for debugging.
    """

    def __init__(self, db_path: str):
        super().__init__(level=logging.WARNING)  # WARNING and above (ERROR, CRITICAL)
        self.db_path = Path(db_path)

    def emit(self, record: logging.LogRecord) -> None:
        """Store error log to database with defensive error handling."""
        conn = None
        try:
            # Extract context if provided via extra
            context = getattr(record, 'context', None)
            event = getattr(record, 'event', None)
            symbol = getattr(record, 'symbol', None)
            trade_id = getattr(record, 'trade_id', None)
            cycle_id_override = getattr(record, 'cycle_id', None)

            # Get stack trace for errors
            stack_trace = None
            if record.exc_info:
                stack_trace = ''.join(traceback.format_exception(*record.exc_info))

            # Build log entry
            log_id = str(uuid.uuid4())[:12]
            timestamp = datetime.now(timezone.utc).isoformat()
            run_id = _current_run_id.get()
            cycle_id = cycle_id_override or _current_cycle_id.get()
            component = record.name.split('.')[-1]  # Last part of logger name
            message = record.getMessage()
            context_json = json.dumps(context) if context else None

            # Use centralized database client (auto-handles SQLite/PostgreSQL)
            # Use shorter timeout for logging to fail fast if pool exhausted
            try:
                conn = get_connection(timeout_seconds=5.0)
            except TimeoutError as timeout_err:
                # Pool exhausted - log to stderr instead of database
                # This prevents cascade failure where logging errors prevent visibility
                import sys
                print(f"[ErrorLogger] ⚠️  Connection pool exhausted, logging to stderr instead", file=sys.stderr)
                print(f"[ErrorLogger] {record.levelname}: {message}", file=sys.stderr)
                if stack_trace:
                    print(f"[ErrorLogger] Stack trace:\n{stack_trace}", file=sys.stderr)
                return

            # Use auto_commit=True to let centralized layer handle transactions
            execute(conn, """
                INSERT INTO error_logs (
                    id, timestamp, level, run_id, cycle_id, trade_id, symbol,
                    component, event, message, stack_trace, context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_id,
                timestamp,
                record.levelname,
                run_id,
                cycle_id,
                trade_id,
                symbol,
                component,
                event,
                message,
                stack_trace,
                context_json,
            ), auto_commit=True)

            # DEBUG: Log successful database write
            import sys
            print(f"[ErrorLogger] ✅ Stored {record.levelname} to DB: {message[:80]}", file=sys.stderr)

        except Exception as e:
            # Don't let logging errors break the app
            # Print to stderr for debugging (fallback when database unavailable)
            import sys
            print(f"[ErrorLogger] ❌ Failed to log error: {e}", file=sys.stderr)
            print(f"[ErrorLogger] Original message: {record.getMessage()[:100]}", file=sys.stderr)
            if hasattr(e, '__traceback__'):
                print(f"[ErrorLogger] Error traceback: {traceback.format_exc()}", file=sys.stderr)
        finally:
            # Always release connection back to pool (PostgreSQL) or close (SQLite)
            if conn is not None:
                release_connection(conn)


def log_error(
    logger: logging.Logger,
    message: str,
    event: Optional[str] = None,
    symbol: Optional[str] = None,
    trade_id: Optional[str] = None,
    cycle_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    exc_info: bool = False,
) -> None:
    """
    Log an error with structured context for debugging.
    
    Args:
        logger: The logger instance
        message: Error message
        event: Event type (e.g., 'login_failed', 'capture_failed')
        symbol: Trading symbol if relevant
        trade_id: Trade ID if relevant
        cycle_id: Cycle ID override (uses context var if not provided)
        context: Additional debugging context as dict
        exc_info: Whether to include exception info
    """
    logger.error(
        message,
        exc_info=exc_info,
        extra={
            'event': event,
            'symbol': symbol,
            'trade_id': trade_id,
            'cycle_id': cycle_id,
            'context': context,
        }
    )


def setup_error_logging(db_path: str) -> DatabaseErrorHandler:
    """
    Add database error handler to root logger.
    
    Args:
        db_path: Path to the trading.db file
        
    Returns:
        The handler instance (for cleanup if needed)
    """
    handler = DatabaseErrorHandler(db_path)
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    # Add to root logger so all loggers capture errors
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    return handler

