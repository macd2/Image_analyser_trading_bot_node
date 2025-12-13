#!/usr/bin/env python3
"""
Clean Trading Bot Entry Point.
Starts the WebSocket-based trading engine with real-time state management.

Usage:
    python run_bot.py                    # Paper trading (default)
    python run_bot.py --live             # Live trading
    python run_bot.py --testnet          # Use testnet
    python run_bot.py --live --testnet   # Live trading on testnet
"""

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from trading_bot.config.settings_v2 import ConfigV2
from trading_bot.engine.trading_engine import TradingEngine
from trading_bot.engine.trading_cycle import TradingCycle
from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, MonitorMode
from trading_bot.engine.trade_tracker import TradeTracker
from trading_bot.core.utils import seconds_until_next_boundary, get_current_cycle_boundary, get_next_cycle_boundary
from trading_bot.core.error_logger import setup_error_logging, set_run_id, set_cycle_id, clear_cycle_id
from trading_bot.core.event_emitter import get_event_emitter, BotEvent
from trading_bot.db.init_trading_db import init_database, get_connection
from trading_bot.db.client import execute, query, query_one, release_connection

# Configure logging
# Force unbuffered output to ensure logs appear immediately in Railway/Docker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,  # Explicitly use stderr
    force=True,  # Override any existing configuration
)
logger = logging.getLogger(__name__)

# Ensure stderr is unbuffered for immediate log visibility
sys.stderr.reconfigure(line_buffering=True)


class TradingBot:
    """
    Main trading bot orchestrator.
    Integrates all components for a complete trading system.
    """

    def __init__(
        self,
        paper_trading: bool = True,
        testnet: bool = False,
        instance_id: str = None,
    ):
        """
        Initialize trading bot.

        Args:
            paper_trading: Paper trading mode if True
            testnet: Use testnet if True
            instance_id: REQUIRED - Instance ID to run (loads config from instance settings)
        """
        if not instance_id:
            raise ValueError("instance_id is required. The bot must be started with a specific instance.")

        self._running = False
        self.instance_id = instance_id

        # Load configuration from instance settings
        logger.info(f"Loading config from instance: {instance_id}")
        self.config = ConfigV2.from_instance(instance_id)

        # Initialize database
        init_database()
        self._db = get_connection()

        # Setup error logging to database
        db_path = Path(__file__).parent / "trading_bot" / "data" / "trading.db"
        self._error_handler = setup_error_logging(str(db_path))

        # Clean up stale runs from previous crashes
        self._cleanup_stale_runs()

        # Load instance configuration (prompt_name)
        self.instance_prompt_name: Optional[str] = None
        if self.instance_id:
            row = query_one(self._db,
                "SELECT prompt_name FROM instances WHERE id = ?",
                (self.instance_id,)
            )
            if row and row['prompt_name']:
                self.instance_prompt_name = row['prompt_name']
                logger.info(f"📋 Instance prompt: {self.instance_prompt_name}")

        # Command line arguments always take precedence over database config
        # The caller (main()) passes explicit values based on --live and --testnet flags
        self.paper_trading = paper_trading
        self.testnet = testnet

        # Create new run for this bot session
        self.run_id = self._create_run()

        # Set run_id for error correlation
        set_run_id(self.run_id)

        logger.info(f"📋 Configuration loaded from database:")
        logger.info(f"   Run ID: {self.run_id}")
        logger.info(f"   Paper Trading: {self.paper_trading}")
        logger.info(f"   Testnet: {self.testnet}")

        # Initialize trading engine
        self.engine = TradingEngine(
            config=self.config,
            testnet=self.testnet,
            paper_trading=self.paper_trading,
            run_id=self.run_id,  # Pass run_id for audit trail
            instance_id=self.instance_id,  # Pass instance_id for StateManager paper trading support
        )

        # Initialize trading cycle (chart capture + analysis)
        self.trading_cycle = TradingCycle(
            config=self.config,
            execute_signal_callback=self.engine.execute_signal,
            testnet=self.testnet,
            run_id=self.run_id,  # Pass run_id for audit trail
            prompt_name=self.instance_prompt_name,  # Pass instance prompt
            paper_trading=self.paper_trading,  # Pass paper trading mode
            instance_id=self.instance_id,  # Pass instance ID for DB queries
        )

        # Enhanced position monitor for stop-loss tightening, TP proximity, age-based features
        self.position_monitor = EnhancedPositionMonitor.from_config(
            config=self.config.trading,
            executor=self.engine.order_executor,
            mode=MonitorMode.EVENT_DRIVEN,  # Use event-driven for live/paper trading
            poll_interval=5.0,
            db_connection=self._db,
        )

        # Trade tracker for WebSocket updates
        self.trade_tracker = TradeTracker(db_connection=self._db)

        # Wire up callbacks
        self._setup_callbacks()

    def _cleanup_stale_runs(self) -> None:
        """Mark any 'running' runs as 'crashed' - they're from previous sessions."""
        try:
            stale_runs = query(self._db,
                "SELECT id FROM runs WHERE status = 'running'"
            )

            if stale_runs:
                execute(self._db, """
                    UPDATE runs
                    SET status = 'crashed',
                        stop_reason = 'stale_cleanup',
                        ended_at = ?
                    WHERE status = 'running'
                """, (datetime.now(timezone.utc).isoformat(),))
                self._db.commit()
                logger.info(f"🧹 Cleaned up {len(stale_runs)} stale run(s) from previous crashes")
        except Exception as e:
            logger.warning(f"Could not cleanup stale runs: {e}")

    def _create_run(self) -> str:
        """Create a new run record for this bot session."""
        run_id = str(uuid.uuid4())[:12]  # Short UUID for readability

        # Get timeframe from instance config (already loaded)
        timeframe = self.config.trading.timeframe

        # Build config snapshot for reproducibility
        config_snapshot = {
            "trading": {
                "paper_trading": self.paper_trading,
                "timeframe": timeframe,
                "min_confidence_threshold": self.config.trading.min_confidence_threshold,
                "min_rr": self.config.trading.min_rr,
                "risk_percentage": self.config.trading.risk_percentage,
                "leverage": self.config.trading.leverage,
                "max_concurrent_trades": self.config.trading.max_concurrent_trades,
            },
            "bybit": {
                "testnet": self.testnet,
            },
            "openai": {
                "model": self.config.openai.model,
                "assistant_id": self.config.openai.assistant_id,
            },
        }

        execute(self._db, """
            INSERT INTO runs (
                id, instance_id, started_at, status, timeframe, paper_trading,
                min_confidence, max_leverage, config_snapshot
            ) VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?)
        """, (
            run_id,
            self.instance_id,  # Link to parent instance
            datetime.now(timezone.utc).isoformat(),
            timeframe,
            self.paper_trading,  # Pass boolean directly (works for both SQLite and PostgreSQL)
            self.config.trading.min_confidence_threshold,
            self.config.trading.leverage,
            json.dumps(config_snapshot),
        ))
        self._db.commit()

        logger.info(f"📦 Created new run: {run_id}" + (f" (instance: {self.instance_id})" if self.instance_id else ""))
        return run_id

    def _end_run(self, status: str = "stopped", reason: str = None) -> None:
        """Mark run as ended."""
        try:
            execute(self._db, """
                UPDATE runs
                SET ended_at = ?, status = ?, stop_reason = ?
                WHERE id = ?
            """, (
                datetime.now(timezone.utc).isoformat(),
                status,
                reason,
                self.run_id,
            ))
            self._db.commit()
            logger.info(f"📦 Run {self.run_id} ended: {status}")
        except Exception as e:
            logger.error(f"Failed to end run: {e}")

    def _setup_callbacks(self) -> None:
        """Set up component callbacks."""
        # Position monitor receives position updates (with instance/run context)
        def position_update_wrapper(position):
            # Get current trade_id from trade_tracker if available
            trade_id = None
            open_trades = self.trade_tracker.get_open_trades()
            for trade in open_trades:
                if trade.symbol == position.symbol:
                    trade_id = trade.trade_id
                    break

            self.position_monitor.on_position_update(
                position=position,
                instance_id=self.instance_id,
                run_id=self.run_id,
                trade_id=trade_id,
            )

        self.engine.state_manager.set_on_position_update(position_update_wrapper)

        # Order updates go to both trade tracker AND position monitor (for age-based cancellation)
        def order_update_wrapper(order):
            # Forward to trade tracker
            self.trade_tracker.on_order_update(order)

            # Forward to position monitor with context
            self.position_monitor.on_order_update(
                order=order,
                instance_id=self.instance_id,
                run_id=self.run_id,
                timeframe=self.trading_cycle.timeframe,
            )

        self.engine.state_manager.set_on_order_update(order_update_wrapper)

        # Execution updates go to trade tracker
        self.engine.state_manager.set_on_fill(
            self.trade_tracker.on_execution
        )

    def start(self) -> bool:
        """Start the trading bot."""
        logger.info("=" * 70)
        logger.info("🤖 TRADING BOT STARTING")
        logger.info(f"   Mode: {'PAPER TRADING' if self.paper_trading else '🔴 LIVE TRADING'}")
        logger.info(f"   Network: {'TESTNET' if self.testnet else 'MAINNET'}")
        logger.info(f"   Max Trades: {self.config.trading.max_concurrent_trades}")
        logger.info(f"   Risk: {self.config.trading.risk_percentage * 100:.1f}%")
        logger.info(f"   Symbols: From TradingView watchlist")
        logger.info(f"   Timeframe: {self.trading_cycle.timeframe}")
        logger.info("=" * 70)

        if not self.engine.start():
            logger.error("Failed to start trading engine")
            return False

        self.trading_cycle.start()
        self._running = True
        logger.info("✅ Trading bot started successfully")
        return True

    def stop(self, reason: str = "user_stop") -> None:
        """Stop the trading bot."""
        logger.info("Stopping trading bot...")
        self._running = False
        self.trading_cycle.stop()
        self.engine.stop()
        self.position_monitor.stop()  # Stop position monitor

        # End the run
        self._end_run(status="stopped", reason=reason)

        # Release database connection back to pool (PostgreSQL) or close (SQLite)
        if self._db:
            release_connection(self._db)
            self._db = None

        logger.info("Trading bot stopped")

    def run(self) -> None:
        """Run the main bot loop with trading cycles."""
        if not self.start():
            return

        try:
            # Run async event loop
            asyncio.run(self._run_async())
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self.stop()

    async def _run_async(self) -> None:
        """Async main loop that runs trading cycles at boundaries."""
        timeframe = self.trading_cycle.timeframe
        self._pause_reason = None  # Track why bot is paused

        # Run initial cycle immediately
        logger.info("🚀 Running initial cycle immediately...")
        await self.trading_cycle.run_cycle_async()

        while self._running:
            # Calculate time until next boundary
            next_boundary = get_next_cycle_boundary(timeframe)
            wait_seconds = (next_boundary - datetime.now(timezone.utc)).total_seconds()
            total_wait_seconds = wait_seconds
            initial_wait_seconds = wait_seconds

            logger.info(f"\n⏰ Next cycle at {next_boundary.strftime('%H:%M:%S')} UTC")
            logger.info(f"   Waiting {wait_seconds:.0f} seconds...")

            # Emit waiting start event
            emitter = get_event_emitter()
            emitter.emit_waiting_start(total_wait_seconds, next_boundary, timeframe)

            # Calculate 10% interval for progress updates
            progress_interval = total_wait_seconds / 10.0
            last_progress_milestone = 0

            # Wait until next boundary (with periodic checks)
            # Use the SAME target boundary throughout the wait, don't recalculate
            while self._running:
                now = datetime.now(timezone.utc)
                wait_seconds = (next_boundary - now).total_seconds()

                # Exit if we've reached or passed the boundary
                if wait_seconds <= 0:
                    break

                sleep_time = min(wait_seconds, 30)  # Check every 30s
                await asyncio.sleep(sleep_time)

                # Calculate elapsed time and progress
                elapsed_seconds = initial_wait_seconds - wait_seconds
                progress_percent = (elapsed_seconds / initial_wait_seconds) * 100 if initial_wait_seconds > 0 else 0

                # Emit progress update every 10%
                current_milestone = int(progress_percent / 10)
                if current_milestone > last_progress_milestone and current_milestone <= 10:
                    emitter.emit_waiting_progress(elapsed_seconds, initial_wait_seconds, progress_percent)
                    remaining_minutes = wait_seconds / 60
                    logger.info(f"⏳ Waiting for next cycle: {progress_percent:.0f}% | Remaining: {remaining_minutes:.1f} minutes ({wait_seconds:.0f}s)")
                    last_progress_milestone = current_milestone

            # Log why we exited the wait loop
            if not self._running:
                logger.info("⏹️ Bot stopped during wait - exiting loop")
                break
            else:
                logger.info(f"✅ Wait loop completed - wait_seconds={wait_seconds:.2f}, _running={self._running}")

            # Emit waiting end event
            emitter.emit_waiting_end(total_wait_seconds)

            # Log wake-up and cycle start
            logger.info(f"\n{'='*60}")
            logger.info(f"⏰ BOUNDARY REACHED - WAKING UP!")
            logger.info(f"   Current time: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
            logger.info(f"   Timeframe: {timeframe}")
            logger.info(f"   Starting trading cycle...")
            logger.info(f"{'='*60}\n")

            # Flush logs to ensure they appear immediately
            sys.stderr.flush()

            # Run trading cycle
            try:
                logger.info("🔄 Calling trading_cycle.run_cycle_async()...")
                await self.trading_cycle.run_cycle_async()
                logger.info("✅ Trading cycle completed successfully")
            except Exception as e:
                logger.error(f"❌ Cycle error: {e}", exc_info=True)
                logger.error(f"   Error type: {type(e).__name__}")
                logger.error(f"   Continuing to next cycle...")
                # Continue to next cycle

            # Check for critical OpenAI rate limit errors
            if self._check_for_openai_rate_limit_error():
                logger.error("🛑 OpenAI rate limit (429) detected - PAUSING BOT")
                logger.error("   Waiting for user confirmation via UI banner...")
                self._pause_reason = "openai_rate_limit"
                await self._wait_for_user_confirmation()
                logger.info("✅ User confirmed recharge - resuming bot")
                self._pause_reason = None

            # Small buffer before next wait calculation
            await asyncio.sleep(2)

    def _check_for_openai_rate_limit_error(self) -> bool:
        """
        Check if recent error logs contain OpenAI 429 rate limit error.
        Returns True if found and not yet acknowledged.
        """
        conn = None
        try:
            from trading_bot.db import get_connection, query_one, release_connection

            conn = get_connection()
            # Check for recent OpenAI 429 error (last 5 minutes)
            error = query_one(conn, """
                SELECT id, message FROM error_logs
                WHERE message LIKE '%OpenAI API rate limit exceeded (429)%'
                  AND timestamp > datetime('now', '-5 minutes')
                  AND (SELECT COUNT(*) FROM error_logs el2
                       WHERE el2.message LIKE '%OpenAI rate limit acknowledged%'
                       AND el2.timestamp > ?) = 0
                ORDER BY timestamp DESC
                LIMIT 1
            """, (datetime.now(timezone.utc).isoformat(),))

            return error is not None

        except Exception as e:
            logger.error(f"Failed to check for OpenAI rate limit error: {e}")
            return False
        finally:
            # Always release connection back to pool (PostgreSQL) or close (SQLite)
            if conn is not None:
                release_connection(conn)

    async def _wait_for_user_confirmation(self, timeout_seconds: int = 3600) -> None:
        """
        Wait for user to confirm via API endpoint that credits have been recharged.
        Polls /api/bot/pause-state every 5 seconds.

        Args:
            timeout_seconds: Maximum time to wait (default 1 hour)
        """
        import aiohttp

        start_time = datetime.now(timezone.utc)
        poll_interval = 5  # seconds

        logger.info(f"⏸️  Bot paused - waiting for user confirmation (timeout: {timeout_seconds}s)")

        while self._running:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            if elapsed > timeout_seconds:
                logger.warning(f"⏱️  Pause timeout after {timeout_seconds}s - resuming anyway")
                break

            try:
                # Poll the pause state endpoint
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"http://localhost:3000/api/bot/pause-state?instance_id={self.instance_id}",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("user_confirmed"):
                                logger.info("✅ User confirmed recharge - resuming bot")
                                return
            except Exception as e:
                logger.debug(f"Pause state check failed (will retry): {e}")

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    def get_status(self) -> dict:
        """Get bot status."""
        return {
            "running": self._running,
            "paper_trading": self.paper_trading,
            "testnet": self.testnet,
            "paused_reason": self._pause_reason,
            "engine": self.engine.get_status(),
            "cycle": self.trading_cycle.get_status(),
            "open_trades": len(self.trade_tracker.get_open_trades()),
            "monitored_positions": len(self.position_monitor.get_all_positions()),
        }


def main():
    """Main entry point."""
    # Print startup banner to stderr immediately
    print("=" * 70, file=sys.stderr, flush=True)
    print("🤖 TRADING BOT STARTING UP", file=sys.stderr, flush=True)
    print(f"   Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC", file=sys.stderr, flush=True)
    print("=" * 70, file=sys.stderr, flush=True)

    parser = argparse.ArgumentParser(description="Trading Bot")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live trading (default: paper trading)",
    )
    parser.add_argument(
        "--testnet",
        action="store_true",
        help="Use testnet (default: mainnet)",
    )
    parser.add_argument(
        "--instance",
        type=str,
        required=True,
        help="REQUIRED: Instance ID to run (loads config from instance settings)",
    )
    args = parser.parse_args()

    # Validate instance_id is provided
    if not args.instance:
        print("❌ ERROR: --instance is required. The bot must be started with a specific instance.", file=sys.stderr, flush=True)
        print("   Example: python run_bot.py --instance <instance_id>", file=sys.stderr, flush=True)
        return

    # Safety check for live trading
    if args.live and not args.testnet:
        print("\n⚠️  WARNING: You are about to start LIVE TRADING on MAINNET!", file=sys.stderr, flush=True)
        print("   This will use REAL MONEY.", file=sys.stderr, flush=True)
        confirm = input("   Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Aborted.", file=sys.stderr, flush=True)
            return

    bot = TradingBot(
        paper_trading=not args.live,
        testnet=args.testnet,
        instance_id=args.instance,
    )
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    bot.run()


if __name__ == "__main__":
    main()

