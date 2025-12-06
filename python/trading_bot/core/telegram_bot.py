import asyncio
import logging
import os
from typing import Optional, Dict, Any, Tuple

try:
    import telegram
    from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.error import TelegramError, NetworkError, TimedOut
except ImportError:
    raise ImportError("python-telegram-bot is required. Install with: pip install python-telegram-bot")

logger = logging.getLogger(__name__)


def get_telegram_config() -> Tuple[Optional[str], Optional[str]]:
    """
    Get Telegram configuration from environment variables.
    
    Returns:
        Tuple of (bot_token, chat_id)
    """
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    return bot_token, chat_id


class TelegramBot:
    """Telegram bot for trade notifications and user confirmation."""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram bot with configuration.
        
        Args:
            bot_token: Telegram bot token. If None, loads from TELEGRAM_BOT_TOKEN env var.
            chat_id: Telegram chat ID. If None, loads from TELEGRAM_CHAT_ID env var.
        """
        self.bot_token = bot_token or get_telegram_config()[0]
        chat_id_value = chat_id or get_telegram_config()[1]
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        if not chat_id_value:
            raise ValueError("TELEGRAM_CHAT_ID environment variable is required")
            
        try:
            self.chat_id = int(chat_id_value)
        except ValueError:
            raise ValueError("TELEGRAM_CHAT_ID must be a valid integer")
            
        self.bot = telegram.Bot(token=self.bot_token)
        self.application = Application.builder().token(self.bot_token).build()
        
        # Ensure updater exists - if not, create a minimal one
        if self.application.updater is None:
            # The updater should be created automatically by the builder
            # If it's still None, there might be an issue with the telegram library version
            logger.warning("Updater is None - this might cause issues with polling")
        
        # Store user responses
        self.user_responses = {}
        self.timeout_seconds = 30
        
    def format_trade_message(self, trade_data: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
        """
        Format trade details into a readable message with inline keyboard.
        
        Args:
            trade_data: Dictionary containing trade information
                Required keys: direction, symbol, timeframe, entry_price, stop_loss, take_profits
                Optional: trade_id for unique callback data
            
        Returns:
            Tuple of (message_text, inline_keyboard_markup)
        """
        direction = trade_data.get('direction', '').upper()
        symbol = trade_data.get('symbol', '')
        timeframe = trade_data.get('timeframe', '')
        entry_price = trade_data.get('entry_price', 0)
        stop_loss = trade_data.get('stop_loss', 0)
        take_profits = trade_data.get('take_profits', [])
        trade_id = trade_data.get('trade_id', '')
        
        # Calculate risk/reward
        risk = abs(entry_price - stop_loss)
        if take_profits and len(take_profits) > 0:
            reward = abs(take_profits[0] - entry_price)
            risk_reward = reward / risk if risk > 0 else 0
        else:
            risk_reward = 0
        
        # Direction emoji
        direction_emoji = "🟢" if direction == "BUY" else "🔴"
        
        message = f"""
📊 **TRADE ALERT** {direction_emoji}

**{direction} {symbol}** ({timeframe})

💰 **Entry:** ${entry_price:.4f}
🛑 **Stop Loss:** ${stop_loss:.4f}
🎯 **Take Profits:**
"""
        
        for i, tp in enumerate(take_profits, 1):
            message += f"   TP{i}: ${tp:.4f}\n"
            
        message += f"\n⚖️ **Risk/Reward:** 1:{risk_reward:.2f}"
        message += "\n\nClick ✅ to confirm or ❌ to reject this trade:"
        
        # Create inline keyboard with unique callback data
        confirm_data = f"confirm_{trade_id}" if trade_id else "confirm_trade"
        reject_data = f"reject_{trade_id}" if trade_id else "reject_trade"
        
        keyboard = [
            [
                InlineKeyboardButton("✅ CONFIRM", callback_data=confirm_data),
                InlineKeyboardButton("❌ REJECT", callback_data=reject_data)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        return message.strip(), reply_markup
    
    async def send_trade_notification(self, trade_data: Dict[str, Any]) -> Tuple[bool, Optional[int]]:
        """
        Send trade notification to user with inline keyboard.
        
        Args:
            trade_data: Dictionary containing trade information
            
        Returns:
            Tuple of (success, message_id) where message_id is the sent message ID
        """
        try:
            message, reply_markup = self.format_trade_message(trade_data)
            sent_message = await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            logger.info(f"Trade notification sent for {trade_data.get('symbol', 'unknown')}")
            return True, sent_message.message_id
            
        except TelegramError as e:
            logger.error(f"Failed to send trade notification: {e}")
            return False, None
    
    async def wait_for_confirmation(self, timeout: Optional[int] = None, trade_id: Optional[str] = None) -> Optional[bool]:
        """
        Wait for user confirmation via inline keyboard callback.
        
        Args:
            timeout: Timeout in seconds. Uses default if None.
            trade_id: Trade ID for unique callback handling
            
        Returns:
            True for CONFIRM, False for REJECT, None for timeout/error
        """
        timeout = timeout or self.timeout_seconds
        
        # Use asyncio.Event for proper event-driven handling
        confirmation_event = asyncio.Event()
        confirmation_result = None
        
        # Set up callback query handler
        async def handle_callback(update, context):
            nonlocal confirmation_result
            if update.effective_chat.id != self.chat_id:
                return
                
            query = update.callback_query
            await query.answer()  # Acknowledge the callback
            
            # Handle unique callback data
            confirm_data = f"confirm_{trade_id}" if trade_id else "confirm_trade"
            reject_data = f"reject_{trade_id}" if trade_id else "reject_trade"
            
            # Debug logging
            logger.info(f"Received callback data: '{query.data}'")
            logger.info(f"Expected confirm_data: '{confirm_data}'")
            logger.info(f"Expected reject_data: '{reject_data}'")
            logger.info(f"Trade ID: '{trade_id}'")
            
            if query.data == confirm_data:
                confirmation_result = True
                logger.info(f"Trade {trade_id} CONFIRMED")
                await query.edit_message_text(
                    text=query.message.text + "\n\n✅ **TRADE CONFIRMED** - Processing trade..."
                )
                confirmation_event.set()  # Signal that we got a response
            elif query.data == reject_data:
                confirmation_result = False
                logger.info(f"Trade {trade_id} REJECTED")
                await query.edit_message_text(
                    text=query.message.text + "\n\n❌ **TRADE REJECTED** - Trade cancelled"
                )
                confirmation_event.set()  # Signal that we got a response
            else:
                logger.warning(f"Unmatched callback data: '{query.data}' for trade_id: '{trade_id}'")
        
        # Register handler
        handler = CallbackQueryHandler(handle_callback)
        self.application.add_handler(handler)
        
        try:
            # Add the handler to the application
            self.application.add_handler(handler)
            
            # Create a task to run the bot and wait for confirmation
            async def run_bot_and_wait():
                async with self.application:
                    await self.application.start()
                    await self.application.updater.start_polling()
                    
                    try:
                        # Wait for either confirmation or timeout
                        await asyncio.wait_for(confirmation_event.wait(), timeout=timeout)
                        return confirmation_result
                    finally:
                        await self.application.updater.stop()
                        await self.application.stop()
            
            # Run the bot and wait for confirmation
            return await asyncio.wait_for(run_bot_and_wait(), timeout=timeout + 5)  # Add buffer time
            
        except asyncio.TimeoutError:
            # Timeout - send timeout message
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text="⏰ Trade confirmation timeout. Trade cancelled."
                )
            except:
                pass
            return None
        except NetworkError as e:
            logger.error(f"Network error during confirmation: {e}")
            return None
        except Exception as e:
            logger.error(f"Error during confirmation: {e}")
            return None
        finally:
            # Clean up - remove handler
            try:
                self.application.remove_handler(handler)
            except:
                pass
    
    async def send_message(self, message: str) -> bool:
        """
        Send a simple message to the user.
        
        Args:
            message: Message text to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def send_trades_summary(self, trades: list) -> bool:
        """
        Send a summary of all valid trades before individual confirmations.
        
        Args:
            trades: List of trade dictionaries
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not trades:
            return False
            
        # Send divider first
        divider = "=" * 50 + "\n🔍 **TRADE ANALYSIS COMPLETE** 🔍\n" + "=" * 50
        await self.send_message(divider)
        
        # Create summary message
        summary = f"📊 **Found {len(trades)} Valid Trades:**\n\n"
        
        for i, trade in enumerate(trades, 1):
            symbol = trade.get('symbol', 'Unknown')
            timeframe = trade.get('timeframe', 'Unknown')
            direction = trade.get('direction', '').upper()
            entry_price = trade.get('entry_price', 0)
            stop_loss = trade.get('stop_loss', 0)
            take_profits = trade.get('take_profits', [])
            
            # Calculate risk/reward
            risk = abs(entry_price - stop_loss)
            if take_profits and len(take_profits) > 0:
                reward = abs(take_profits[0] - entry_price)
                risk_reward = reward / risk if risk > 0 else 0
            else:
                risk_reward = 0
            
            direction_emoji = "🟢" if direction == "BUY" else "🔴"
            summary += f"{i}. {direction_emoji} **{symbol}** | {timeframe} | RR: 1:{risk_reward:.2f}\n"
        
        summary += f"\n🔄 **Processing each trade individually for confirmation...**"
        
        return await self.send_message(summary)
    
    async def send_trade_with_confirmation(self, trade_data: Dict[str, Any],
                                         timeout: Optional[int] = None) -> Optional[bool]:
        """
        Send trade notification and wait for user confirmation via inline keyboard.
        
        Args:
            trade_data: Dictionary containing trade information
            timeout: Timeout in seconds
            
        Returns:
            True if confirmed, False if rejected, None if timeout/error
        """
        # Send notification
        success, message_id = await self.send_trade_notification(trade_data)
        if not success:
            return None
            
        # Wait for confirmation with trade_id
        trade_id = trade_data.get('trade_id')
        return await self.wait_for_confirmation(timeout, trade_id)
    
    async def send_custom_confirmation(self, message: str, confirm_text: str = "✅ CONFIRM",
                                     reject_text: str = "❌ REJECT",
                                     trade_id: Optional[str] = None,
                                     timeout: Optional[int] = None) -> Optional[bool]:
        """
        Send a custom message with confirmation buttons and wait for user response.
        
        Args:
            message: Custom message text to send
            confirm_text: Text for confirm button
            reject_text: Text for reject button
            trade_id: Unique ID for this confirmation
            timeout: Timeout in seconds
            
        Returns:
            True if confirmed, False if rejected, None if timeout/error
        """
        try:
            # Create inline keyboard with unique callback data
            confirm_data = f"confirm_{trade_id}" if trade_id else "confirm_custom"
            reject_data = f"reject_{trade_id}" if trade_id else "reject_custom"
            
            keyboard = [
                [
                    InlineKeyboardButton(confirm_text, callback_data=confirm_data),
                    InlineKeyboardButton(reject_text, callback_data=reject_data)
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send message with inline keyboard
            sent_message = await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            logger.info(f"Custom confirmation message sent with ID: {trade_id}")
            
            # Wait for confirmation
            return await self.wait_for_confirmation(timeout, trade_id)
            
        except TelegramError as e:
            logger.error(f"Failed to send custom confirmation: {e}")
            return None


# Synchronous wrapper functions for easier usage
def send_trade_notification_sync(trade_data: Dict[str, Any],
                                bot_token: Optional[str] = None,
                                chat_id: Optional[str] = None) -> bool:
    """
    Synchronous wrapper for sending trade notifications.
    
    Args:
        trade_data: Dictionary containing trade information
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
        
    Returns:
        True if sent successfully, False otherwise
    """
    bot = TelegramBot(bot_token, chat_id)
    success, _ = asyncio.run(bot.send_trade_notification(trade_data))
    return success


def wait_for_confirmation_sync(timeout: Optional[int] = None,
                              bot_token: Optional[str] = None,
                              chat_id: Optional[str] = None) -> Optional[bool]:
    """
    Synchronous wrapper for waiting user confirmation.
    
    Args:
        timeout: Timeout in seconds
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
        
    Returns:
        True for YES, False for NO, None for timeout/error
    """
    bot = TelegramBot(bot_token, chat_id)
    return asyncio.run(bot.wait_for_confirmation(timeout))


# Removed send_trade_with_confirmation_sync() function - use async TelegramBot.send_trade_with_confirmation() directly
