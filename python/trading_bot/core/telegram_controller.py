#!/usr/bin/env python3
"""
Telegram Controller for Trading Bot
Provides /commands to start, stop, and monitor the trading bot via Telegram.
"""
import asyncio
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Any

try:
    from telegram import Update, Bot
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
except ImportError:
    raise ImportError("python-telegram-bot is required. Install with: pip install python-telegram-bot")

from trading_bot.core.telegram_bot import get_telegram_config
from trading_bot.core.utils import format_utc_time_for_display, get_utc_now

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class TradingBotController:
    """Controller class for managing the trading bot via Telegram commands."""

    def __init__(self):
        self.bot_token, self.chat_id_str = get_telegram_config()
        if not self.bot_token or not self.chat_id_str:
            raise ValueError("Telegram configuration missing")

        try:
            self.chat_id = int(self.chat_id_str)
        except ValueError:
            raise ValueError("TELEGRAM_CHAT_ID must be a valid integer")

        self.bot = Bot(token=self.bot_token)
        self.application = Application.builder().token(self.bot_token).build()

        # Bot state
        self.bot_process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.last_start_time: Optional[datetime] = None
        self.current_timeframe = "30m"  # Default timeframe

        # Setup handlers
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup Telegram command handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("stop", self.cmd_stop))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("restart", self.cmd_restart))
        self.application.add_handler(CommandHandler("timeframe", self.cmd_timeframe))
        self.application.add_handler(CommandHandler("logs", self.cmd_logs))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        # Message handler for unknown commands
        self.application.add_handler(MessageHandler(filters.COMMAND, self.cmd_unknown))

    async def send_message(self, text: str) -> bool:
        """Send message to configured chat."""
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode='Markdown')
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    def _is_bot_process_running(self) -> bool:
        """Check if the bot process is actually running."""
        if self.bot_process and self.bot_process.poll() is None:
            return True
        return False

    def _start_bot_process(self, timeframe: str = "30m") -> bool:
        """Start the trading bot process."""
        try:
            if self._is_bot_process_running():
                return False

            # Start the bot in a subprocess
            cmd = [sys.executable, "run_autotrader.py", timeframe]
            self.bot_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.getcwd()
            )

            self.is_running = True
            self.last_start_time = get_utc_now()
            self.current_timeframe = timeframe

            logger.info(f"Trading bot started with timeframe {timeframe}")
            return True

        except Exception as e:
            logger.error(f"Failed to start bot process: {e}")
            return False

    def _stop_bot_process(self) -> bool:
        """Stop the trading bot process."""
        try:
            if not self._is_bot_process_running():
                return False

            # Send SIGTERM first
            if self.bot_process:
                self.bot_process.terminate()

                # Wait for graceful shutdown
                try:
                    self.bot_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't respond
                    self.bot_process.kill()
                    self.bot_process.wait()

            self.is_running = False
            self.bot_process = None

            logger.info("Trading bot stopped")
            return True

        except Exception as e:
            logger.error(f"Failed to stop bot process: {e}")
            return False

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.effective_chat or update.effective_chat.id != self.chat_id:
            return

        if not update.message:
            return

        # Check if already running
        if self._is_bot_process_running():
            start_time_str = format_utc_time_for_display(self.last_start_time) if self.last_start_time else "Unknown"
            await update.message.reply_text(
                f"🤖 Bot is already running!\n"
                f"⏰ Started: {start_time_str}\n"
                f"📊 Timeframe: {self.current_timeframe}"
            )
            return

        # Get timeframe from command arguments
        timeframe = context.args[0] if context.args else self.current_timeframe

        # Validate timeframe
        valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
        if timeframe not in valid_timeframes:
            await update.message.reply_text(
                f"❌ Invalid timeframe: {timeframe}\n"
                f"📋 Valid timeframes: {', '.join(valid_timeframes)}"
            )
            return

        # Start the bot
        if self._start_bot_process(timeframe):
            start_time_str = format_utc_time_for_display(self.last_start_time) if self.last_start_time else "Unknown"
            await update.message.reply_text(
                f"🚀 **Trading Bot Started!**\n"
                f"⏰ Started at: {start_time_str}\n"
                f"📊 Timeframe: {timeframe}\n"
                f"✅ Status: Running"
            )
        else:
            await update.message.reply_text("❌ Failed to start trading bot")

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /stop command."""
        if not update.effective_chat or update.effective_chat.id != self.chat_id:
            return

        if not update.message:
            return

        if not self._is_bot_process_running():
            await update.message.reply_text("🤖 Bot is not running")
            return

        if self._stop_bot_process():
            await update.message.reply_text(
                f"🛑 **Trading Bot Stopped!**\n"
                f"⏰ Stopped at: {format_utc_time_for_display(get_utc_now())}"
            )
        else:
            await update.message.reply_text("❌ Failed to stop trading bot")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not update.effective_chat or update.effective_chat.id != self.chat_id:
            return

        if not update.message:
            return

        status = "🟢 Running" if self._is_bot_process_running() else "🔴 Stopped"

        status_msg = f"🤖 **Trading Bot Status**\n"
        status_msg += f"📊 Status: {status}\n"

        if self.is_running and self.last_start_time:
            status_msg += f"⏰ Started: {format_utc_time_for_display(self.last_start_time)}\n"
            status_msg += f"📈 Timeframe: {self.current_timeframe}\n"
            status_msg += f"⏱️ Uptime: {self._get_uptime()}\n"

        if self.bot_process:
            status_msg += f"🔢 Process ID: {self.bot_process.pid}\n"

        await update.message.reply_text(status_msg)

    async def cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /restart command."""
        if not update.effective_chat or update.effective_chat.id != self.chat_id:
            return

        if not update.message:
            return

        # Get new timeframe from arguments
        new_timeframe = context.args[0] if context.args else self.current_timeframe

        await update.message.reply_text("🔄 Restarting trading bot...")

        # Stop current process
        stopped = self._stop_bot_process()

        # Small delay
        await asyncio.sleep(2)

        # Start with new timeframe
        started = self._start_bot_process(new_timeframe)

        if started:
            start_time_str = format_utc_time_for_display(self.last_start_time) if self.last_start_time else "Unknown"
            await update.message.reply_text(
                f"✅ **Trading Bot Restarted!**\n"
                f"⏰ Restarted at: {start_time_str}\n"
                f"📊 Timeframe: {new_timeframe}"
            )
        else:
            await update.message.reply_text("❌ Failed to restart trading bot")

    async def cmd_timeframe(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /timeframe command."""
        if not update.effective_chat or update.effective_chat.id != self.chat_id:
            return

        if not update.message:
            return

        if not context.args:
            await update.message.reply_text(
                f"📊 Current timeframe: {self.current_timeframe}\n"
                f"📋 Valid timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1d\n"
                f"💡 Use: /timeframe <new_timeframe>"
            )
            return

        new_timeframe = context.args[0]
        valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

        if new_timeframe not in valid_timeframes:
            await update.message.reply_text(
                f"❌ Invalid timeframe: {new_timeframe}\n"
                f"📋 Valid timeframes: {', '.join(valid_timeframes)}"
            )
            return

        old_timeframe = self.current_timeframe
        self.current_timeframe = new_timeframe

        await update.message.reply_text(
            f"✅ Timeframe updated: {old_timeframe} → {new_timeframe}\n"
            f"💡 Use /restart to apply the new timeframe"
        )

    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /logs command."""
        if not update.effective_chat or update.effective_chat.id != self.chat_id:
            return

        if not update.message:
            return

        try:
            # Get last 20 lines from log file
            log_file = "logs/trading_bot.log"
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    lines = f.readlines()[-20:]
                    logs = ''.join(lines)

                # Send logs (truncate if too long)
                if len(logs) > 4000:
                    logs = "...\n" + logs[-4000:]

                await update.message.reply_text(f"📄 **Recent Logs:**\n```\n{logs}\n```")
            else:
                await update.message.reply_text("📄 No log file found")

        except Exception as e:
            await update.message.reply_text(f"❌ Error reading logs: {str(e)}")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not update.effective_chat or update.effective_chat.id != self.chat_id:
            return

        if not update.message:
            return

        help_text = """
🤖 **Trading Bot Control Commands**

🚀 **Bot Control:**
/start [timeframe] - Start the trading bot (default: 30m)
/stop - Stop the trading bot
/restart [timeframe] - Restart the trading bot
/status - Show current bot status

⚙️ **Configuration:**
/timeframe [new_timeframe] - Set timeframe (1m,5m,15m,30m,1h,4h,1d)
/logs - Show recent log entries

📚 **Help:**
/help - Show this help message

📊 **Examples:**
/start 1h - Start with 1-hour timeframe
/restart 4h - Restart with 4-hour timeframe
/timeframe 15m - Change to 15-minute timeframe
        """

        await update.message.reply_text(help_text)

    async def cmd_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle unknown commands."""
        if not update.effective_chat or update.effective_chat.id != self.chat_id:
            return

        if not update.message:
            return

        await update.message.reply_text(
            "❓ Unknown command. Use /help to see available commands."
        )

    def _get_uptime(self) -> str:
        """Get bot uptime as formatted string."""
        if not self.last_start_time:
            return "N/A"

        uptime = get_utc_now() - self.last_start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    async def run(self):
        """Run the Telegram controller bot."""
        logger.info("Starting Telegram Controller Bot...")

        # Send startup message
        await self.send_message(
            "🤖 **Trading Bot Controller Started**\n"
            "📱 Use /help to see available commands\n"
            "✅ Ready to receive commands"
        )

        # Start the bot
        await self.application.run_polling()

    async def shutdown(self):
        """Shutdown the controller gracefully."""
        logger.info("Shutting down Telegram Controller...")

        # Stop the trading bot if running
        if self._is_bot_process_running():
            self._stop_bot_process()

        # Send shutdown message
        await self.send_message("🛑 **Trading Bot Controller Stopped**")


def main():
    """Main entry point for the Telegram controller."""
    try:
        controller = TradingBotController()

        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            try:
                asyncio.create_task(controller.shutdown())
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Run the controller
        asyncio.run(controller.run())

    except KeyboardInterrupt:
        logger.info("Controller stopped by user")
    except Exception as e:
        logger.error(f"Controller error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
