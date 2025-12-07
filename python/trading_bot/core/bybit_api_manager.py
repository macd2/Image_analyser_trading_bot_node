import logging
import time
import random # Import the random module
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, cast # Import cast

from pybit.unified_trading import HTTP

from trading_bot.core.secrets_manager import get_bybit_credentials
from trading_bot.config.settings_v2 import ConfigV2
from trading_bot.core.utils import (
    sync_server_time,
    normalize_symbol_for_bybit,
    get_bybit_server_time,
    get_server_synchronized_timestamp,
    get_server_time_sync_status
)

logger = logging.getLogger(__name__)

class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # API calls suspended
    HALF_OPEN = "half_open" # Testing recovery

class BybitAPIManager:
    """
    Unified API Manager for Bybit.
    Handles all API communication, server time synchronization,
    and implements circuit breaker patterns for enhanced reliability.
    """

    def __init__(self, config: ConfigV2, use_testnet: bool = False):
        self.config = config
        self.use_testnet = use_testnet
        self.session: Optional[HTTP] = None
        self._init_bybit_client()

        # Circuit Breaker state
        self._circuit_breaker_state = CircuitBreakerState.CLOSED
        self._last_error_time = 0
        self._consecutive_errors = 0
        self._last_reset_time = time.time()
        # Timestamp storm detection
        self._timestamp_storm_start_time = 0
        self._timestamp_storm_error_count = 0
        self._timestamp_storm_threshold = 5  # Number of timestamp errors in 10 seconds to trigger storm
        self._timestamp_storm_window = 10  # Time window in seconds for storm detection

        # Circuit Breaker configuration from config.yaml
        cb_config = self.config.bybit.circuit_breaker
        if cb_config:
            self.error_threshold = cb_config.error_threshold
            self.recovery_timeout = cb_config.recovery_timeout
            self.max_recv_window = cb_config.max_recv_window
            self.backoff_multiplier = cb_config.backoff_multiplier
            self.jitter_range = cb_config.jitter_range
        else:
            # Fallback to default values if circuit_breaker config is None
            self.error_threshold = 5
            self.recovery_timeout = 300
            self.max_recv_window = 300000
            self.backoff_multiplier = 2.0
            self.jitter_range = 0.1

    def _init_bybit_client(self):
        """Initialize Bybit HTTP client with enhanced recv_window."""
        if HTTP is None:
            logger.error("pybit not installed. Run: pip install pybit")
            return

        try:
            # Use a higher default recv_window to mitigate timestamp errors
            # This overrides the config value if it's lower, ensuring robustness
            recv_window_ms = max(self.config.bybit.recv_window, 600000) # Ensure at least 600000ms (10 minutes)

            # Get API credentials with enhanced error handling
            try:
                api_key, api_secret = get_bybit_credentials()

                # Validate credentials are not empty
                if not api_key or not api_secret:
                    logger.error("❌ Bybit API credentials are empty! Check BYBIT_API_KEY and BYBIT_API_SECRET environment variables.")
                    self.session = None
                    return

                # Log credential status (masked for security)
                key_preview = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
                logger.info(f"🔑 Loaded Bybit API credentials (key: {key_preview})")

            except ValueError as e:
                logger.error(f"❌ Failed to load Bybit API credentials: {e}")
                logger.error("Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables in Railway dashboard")
                self.session = None
                return

            self.session = HTTP(
                testnet=self.use_testnet,
                api_key=api_key,
                api_secret=api_secret,
                recv_window=recv_window_ms,
                timeout=30,  # Set a 30-second timeout for API calls
            )
            logger.info(f"✅ Bybit client initialized with recv_window: {recv_window_ms}ms (testnet: {self.use_testnet})")

            # Perform initial timestamp synchronization
            logger.debug("🕐 Performing initial timestamp synchronization...")
            if self._enhanced_timestamp_sync():
                logger.info("✅ Initial timestamp sync completed successfully")
            else:
                logger.info("ℹ️ Initial timestamp sync unavailable - using local time (this is normal if API is rate-limited)")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Bybit client: {e}", exc_info=True)
            self.session = None

    def _get_current_recv_window(self) -> int:
        """Dynamically get the current recv_window, potentially scaled up during errors."""
        base_recv_window = self.config.bybit.recv_window
        if self._circuit_breaker_state == CircuitBreakerState.OPEN:
            # During open state, use max_recv_window to give more buffer
            return self.max_recv_window
        elif self._consecutive_errors > 0:
            # Progressive recv_window scaling based on backoff multiplier and max_recv_window
            # The idea is to increase the recv_window with each consecutive error, up to max_recv_window
            scaled_window = int(base_recv_window * (self.backoff_multiplier ** (self._consecutive_errors - 1)))
            return min(scaled_window, self.max_recv_window)
        return base_recv_window

    def _enhanced_timestamp_sync(self) -> bool:
        """
        Enhanced timestamp synchronization with aggressive retry logic.
        This method is specifically designed to solve timestamp errors (ErrCode: 10002).
        """
        logger.info("🕐 Performing enhanced timestamp synchronization...")
        
        # Try multiple sync attempts with increasing delays
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Use the centralized sync function from utils
                sync_result = sync_server_time(self.session)
                if sync_result:
                    # Get sync status for logging
                    sync_status = get_server_time_sync_status()
                    logger.info(f"✅ Enhanced timestamp sync successful (attempt {attempt + 1}/{max_attempts})")
                    logger.info(f"   Offset: {sync_status.get('offset_ms', 0)}ms, Last sync: {sync_status.get('last_sync_ago_seconds', 0):.1f}s ago")
                    return True
                else:
                    logger.warning(f"⚠️ Enhanced timestamp sync failed (attempt {attempt + 1}/{max_attempts})")
                    if attempt < max_attempts - 1:
                        delay = (attempt + 1) * 0.5  # 0.5s, 1.0s, 1.5s delays
                        logger.info(f"   Retrying in {delay}s...")
                        time.sleep(delay)
            except Exception as e:
                logger.error(f"❌ Error during enhanced timestamp sync (attempt {attempt + 1}/{max_attempts}): {e}")
                if attempt < max_attempts - 1:
                    delay = (attempt + 1) * 0.5
                    time.sleep(delay)
        
        logger.error("❌ All enhanced timestamp sync attempts failed")
        return False

    def get_timestamp_sync_status(self) -> Dict[str, Any]:
        """Get current timestamp synchronization status for monitoring."""
        try:
            sync_status = get_server_time_sync_status()
            return {
                "status": "success",
                "sync_data": sync_status,
                "circuit_breaker_state": self._circuit_breaker_state.value,
                "consecutive_errors": self._consecutive_errors,
                "current_recv_window": self._get_current_recv_window()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "circuit_breaker_state": self._circuit_breaker_state.value,
                "consecutive_errors": self._consecutive_errors
            }

    def force_timestamp_sync(self) -> bool:
        """Force a timestamp synchronization - useful for manual troubleshooting."""
        logger.info("🔧 Manual timestamp sync requested...")
        return self._enhanced_timestamp_sync()

    def _execute_with_circuit_breaker(self, func, *args, **kwargs):
        """
        Execute a Bybit API call with circuit breaker, retry, and server time sync.
        """
        if not self.session:
            error_msg = "Bybit API manager not initialized. Check that BYBIT_API_KEY and BYBIT_API_SECRET are set in Railway environment variables."
            logger.error(f"❌ {error_msg}")
            return {"retCode": -1, "retMsg": error_msg, "error": error_msg}
        
        # Explicitly cast self.session to HTTP to satisfy Pylance
        session_http = cast(HTTP, self.session)

        # Circuit breaker state check (deactivated)
        current_time = time.time()
        last_error = None
        max_retries = self.config.bybit.max_retries # Use max_retries from config

        for attempt in range(max_retries + 1):
            try:
                # Apply exponential backoff with jitter
                if attempt > 0:
                    delay = (self.backoff_multiplier ** (attempt - 1)) * (1 + random.uniform(-self.jitter_range, self.jitter_range))
                    time.sleep(delay)
                    logger.info(f"Retrying API call after {delay:.2f}s delay (attempt {attempt}/{max_retries})")

                # Dynamically set recv_window for the current call
                kwargs['recv_window'] = self._get_current_recv_window()
                response = func(session_http, *args, **kwargs) # Use the casted session_http

                # Check for API errors (retCode != 0)
                if isinstance(response, dict) and response.get("retCode") != 0:
                    ret_code = response.get("retCode")
                    ret_msg = response.get("retMsg", "Unknown error")
                    error_message = f"API Error: retCode={ret_code}, retMsg={ret_msg}"

                    # Handle timestamp errors (ErrCode 10002) specifically
                    if ret_code == 10002 or "timestamp" in ret_msg.lower() or "recv_window" in ret_msg.lower():
                        logger.warning(f"🚨 Timestamp error detected: {error_message}")

                        # Extract timestamp information from error message for better debugging
                        import re
                        timestamp_match = re.search(r'req_timestamp\[(\d+)\],server_timestamp\[(\d+)\],recv_window\[(\d+)\]', ret_msg)
                        if timestamp_match:
                            req_ts = int(timestamp_match.group(1))
                            server_ts = int(timestamp_match.group(2))
                            recv_window = int(timestamp_match.group(3))
                            time_diff = abs(req_ts - server_ts) / 1000  # Convert to seconds
                            logger.warning(f"📊 Timestamp analysis: Request={req_ts}, Server={server_ts}, Diff={time_diff:.1f}s, RecvWindow={recv_window}ms")

                        # Perform enhanced server time synchronization
                        if not self._enhanced_timestamp_sync():
                            logger.warning(f"Enhanced timestamp sync failed after detecting error. Retrying API call.")
                            last_error = {"error": error_message}
                            continue # Retry API call after sync attempt

                        last_error = {"error": error_message}
                        continue # Retry if it's a timestamp error

                    else:
                        # Non-timestamp API error, break retry loop unless it's a temporary issue
                        logger.error(f"❌ Non-timestamp API error: {error_message}")
                        self._consecutive_errors = 0 # Reset consecutive errors on non-timestamp error
                        self._circuit_breaker_state = CircuitBreakerState.CLOSED # Close circuit if non-timestamp error
                        return {"error": error_message}

                # Success: Reset circuit breaker and error counts
                self._circuit_breaker_state = CircuitBreakerState.CLOSED
                self._consecutive_errors = 0
                self._last_reset_time = current_time

                return response

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Enhanced error logging with exception type
                logger.error(f"❌ Exception during API call: {type(e).__name__}: {e}")

                # Check for network/request errors that might indicate a temporary issue
                if "connection" in error_str or "timeout" in error_str or "read timed out" in error_str:
                    logger.warning(f"🌐 Network/Timeout error: {e}")
                    self._consecutive_errors += 1
                    self._last_error_time = current_time

                    if self._consecutive_errors >= self.error_threshold:
                        self._circuit_breaker_state = CircuitBreakerState.OPEN
                        logger.error(f"Circuit breaker OPEN due to {self._consecutive_errors} consecutive network errors.")
                        return {"retCode": -1, "retMsg": "Circuit breaker OPEN. API calls suspended.", "error": "Circuit breaker OPEN"}
                    continue # Retry network errors

                # For other exceptions, treat as critical and don't retry
                logger.error(f"❌ Unexpected exception during API call: {type(e).__name__}: {e}")
                self._consecutive_errors = 0
                self._circuit_breaker_state = CircuitBreakerState.CLOSED # Close circuit
                return {"retCode": -1, "retMsg": f"{type(e).__name__}: {str(e)}", "error": str(e)}

        # If all retries fail
        if last_error:
            logger.error(f"All API call retries failed. Last error: {last_error}")
            error_msg = f"All retries failed: {str(last_error)}"
            return {"retCode": -1, "retMsg": error_msg, "error": error_msg}
        return {"retCode": -1, "retMsg": "Unknown error after retries", "error": "Unknown error after retries"}

    # --- Unified API Methods ---

    def get_positions(self, **kwargs) -> Dict[str, Any]:
        """Get current positions from Bybit."""
        kwargs.setdefault("category", "linear")
        kwargs.setdefault("settleCoin", "USDT")
        if "symbol" in kwargs:
            kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_positions(**kw), **kwargs)

    def get_open_orders(self, **kwargs) -> Dict[str, Any]:
        """Get open orders from Bybit."""
        kwargs.setdefault("category", "linear")
        kwargs.setdefault("openOnly", 1)
        kwargs.setdefault("limit", 50)
        if "symbol" in kwargs:
            kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        # Bybit API requires symbol, settleCoin, or baseCoin for open orders
        if "symbol" not in kwargs and "settleCoin" not in kwargs and "baseCoin" not in kwargs:
            kwargs.setdefault("settleCoin", "USDT")
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_open_orders(**kw), **kwargs)

    def place_order(self, **kwargs) -> Dict[str, Any]:
        """Place an order on Bybit."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.place_order(**kw), **kwargs)

    def cancel_order(self, **kwargs) -> Dict[str, Any]:
        """Cancel an order on Bybit."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.cancel_order(**kw), **kwargs)

    def cancel_all_orders(self, **kwargs) -> Dict[str, Any]:
        """Cancel all orders on Bybit."""
        kwargs.setdefault("category", "linear")
        return self._execute_with_circuit_breaker(lambda s, **kw: s.cancel_all_orders(**kw), **kwargs)

    def set_trading_stop(self, **kwargs) -> Dict[str, Any]:
        """Set or update TP/SL for a position."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.set_trading_stop(**kw), **kwargs)

    def get_wallet_balance(self, **kwargs) -> Dict[str, Any]:
        """Get wallet balance from Bybit."""
        kwargs.setdefault("accountType", "UNIFIED")
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_wallet_balance(**kw), **kwargs)

    def get_order_history(self, **kwargs) -> Dict[str, Any]:
        """Get order history from Bybit."""
        kwargs.setdefault("category", "linear")
        kwargs.setdefault("limit", 20)
        if "symbol" in kwargs:
            kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_order_history(**kw), **kwargs)

    def get_server_time(self) -> Dict[str, Any]:
        """Get Bybit server time."""
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_server_time())

    def get_kline(self, **kwargs) -> Dict[str, Any]:
        """Get kline (candlestick) data."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_kline(**kw), **kwargs)

    def get_instruments_info(self, **kwargs) -> Dict[str, Any]:
        """Get instrument information."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_instruments_info(**kw), **kwargs)

    def get_fee_rates(self, **kwargs) -> Dict[str, Any]:
        """Get trading fee rates."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_fee_rates(**kw), **kwargs)

    def set_leverage(self, **kwargs) -> Dict[str, Any]:
        """Set leverage for a symbol."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        return self._execute_with_circuit_breaker(lambda s, **kw: s.set_leverage(**kw), **kwargs)

    def get_realtime_orders(self, **kwargs) -> Dict[str, Any]:
        """Get realtime orders from Bybit using get_open_orders with realtime parameters."""
        kwargs.setdefault("category", "linear")
        kwargs.setdefault("limit", 50)
        # Bybit API requires symbol, settleCoin, or baseCoin for orders
        if "symbol" not in kwargs and "settleCoin" not in kwargs and "baseCoin" not in kwargs:
            kwargs["settleCoin"] = "USDT"
        if "symbol" in kwargs:
            kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        # Use get_open_orders with openOnly=0 to get all recent orders (realtime behavior)
        kwargs.setdefault("openOnly", 0)
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_open_orders(**kw), **kwargs)

    def get_funding_rate_history(self, **kwargs) -> Dict[str, Any]:
        """Get funding rate history."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        # Remove recv_window from kwargs as the pybit method doesn't accept it
        kwargs.pop('recv_window', None)
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_funding_rate_history(**kw), **kwargs)

    def get_long_short_ratio(self, **kwargs) -> Dict[str, Any]:
        """Get long/short ratio."""
        kwargs.setdefault("category", "linear")
        
        # Convert timeframe to period if provided
        if "timeframe" in kwargs:
            timeframe = kwargs["timeframe"]
            # Map timeframe to Bybit period format
            timeframe_to_period = {
                "1m": "5min",
                "5m": "15min",
                "15m": "30min",
                "30m": "1h",
                "1h": "1h",
                "4h": "4h",
                "1d": "1d"
            }
            period = timeframe_to_period.get(timeframe, "1h")  # Default to 1h
            kwargs["period"] = period
            # Remove timeframe from kwargs as it's not a valid API parameter
            kwargs.pop("timeframe", None)
        else:
            # Default period if no timeframe provided
            kwargs.setdefault("period", "1h")
            
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        # Remove recv_window from kwargs as the pybit method doesn't accept it
        kwargs.pop('recv_window', None)
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_long_short_ratio(**kw), **kwargs)

    def get_historical_volatility(self, **kwargs) -> Dict[str, Any]:
        """Get historical volatility."""
        kwargs.setdefault("category", "option") # Historical volatility is typically for options
        # Remove recv_window from kwargs as the pybit method doesn't accept it
        kwargs.pop('recv_window', None)
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_historical_volatility(**kw), **kwargs)
    
    def get_closed_pnl(self, **kwargs) -> Dict[str, Any]:
        """Get closed PnL records."""
        kwargs.setdefault("category", "linear")
        # Remove recv_window from kwargs as the pybit method doesn't accept it
        kwargs.pop('recv_window', None)
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_closed_pnl(**kw), **kwargs)

    def get_public_trade_history(self, **kwargs) -> Dict[str, Any]:
        """Get recent public trading history."""
        kwargs.setdefault("category", "linear")
        kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        # Remove recv_window from kwargs as the pybit method doesn't accept it
        kwargs.pop('recv_window', None)
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_public_trade_history(**kw), **kwargs)

    def get_tickers(self, **kwargs) -> Dict[str, Any]:
        """Get latest price snapshot, best bid/ask price, and trading volume."""
        kwargs.setdefault("category", "linear")
        if "symbol" in kwargs:
            kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        # Remove recv_window as it's handled by circuit breaker
        kwargs.pop('recv_window', None)
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_tickers(**kw), **kwargs)

    def get_executions(self, **kwargs) -> Dict[str, Any]:
        """Get execution/trade history from Bybit."""
        kwargs.setdefault("category", "linear")
        if "symbol" in kwargs:
            kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])
        # Remove recv_window as it's handled by circuit breaker
        kwargs.pop('recv_window', None)
        return self._execute_with_circuit_breaker(lambda s, **kw: s.get_executions(**kw), **kwargs)
