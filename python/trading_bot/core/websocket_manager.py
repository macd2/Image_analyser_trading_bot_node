"""
Bybit WebSocket Manager for real-time trading data.
Handles private streams: order, position, execution, wallet.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, List
from enum import Enum

from pybit.unified_trading import WebSocket

from trading_bot.core.secrets_manager import get_bybit_credentials

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class BybitWebSocketManager:
    """
    Manages WebSocket connections to Bybit private streams.
    
    Streams:
    - order: Real-time order updates (status changes, fills)
    - position: Real-time position updates
    - execution: Real-time execution/fill notifications
    - wallet: Real-time balance updates
    """
    
    def __init__(
        self,
        testnet: bool = False,
        on_order: Optional[Callable[[Dict], None]] = None,
        on_position: Optional[Callable[[Dict], None]] = None,
        on_execution: Optional[Callable[[Dict], None]] = None,
        on_wallet: Optional[Callable[[Dict], None]] = None,
        on_connect: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize WebSocket manager.
        
        Args:
            testnet: Use testnet if True
            on_order: Callback for order stream updates
            on_position: Callback for position stream updates
            on_execution: Callback for execution stream updates
            on_wallet: Callback for wallet stream updates
            on_connect: Callback when connected
            on_disconnect: Callback when disconnected
        """
        self.testnet = testnet
        self._ws: Optional[WebSocket] = None
        self._state = ConnectionState.DISCONNECTED
        self._lock = threading.Lock()
        
        # Callbacks
        self._on_order = on_order
        self._on_position = on_position
        self._on_execution = on_execution
        self._on_wallet = on_wallet
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        
        # Reconnection settings
        self._max_reconnect_attempts = 10
        self._reconnect_delay_base = 1.0  # seconds
        self._reconnect_delay_max = 60.0  # seconds
        self._reconnect_attempts = 0
        
        # Keep-alive
        self._keep_alive_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Last message timestamps for monitoring
        self._last_message_time: Dict[str, float] = {}
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._state == ConnectionState.CONNECTED
    
    def connect(self) -> bool:
        """
        Connect to Bybit WebSocket private streams.
        
        Returns:
            True if connection successful, False otherwise.
        """
        with self._lock:
            if self._state == ConnectionState.CONNECTED:
                logger.warning("WebSocket already connected")
                return True
            
            self._state = ConnectionState.CONNECTING
        
        try:
            api_key, api_secret = get_bybit_credentials()
            
            logger.info(f"Connecting to Bybit WebSocket ({'testnet' if self.testnet else 'mainnet'})...")
            
            self._ws = WebSocket(
                testnet=self.testnet,
                channel_type="private",
                api_key=api_key,
                api_secret=api_secret,
            )
            
            # Subscribe to streams
            self._subscribe_streams()
            
            with self._lock:
                self._state = ConnectionState.CONNECTED
                self._reconnect_attempts = 0
            
            logger.info("✅ WebSocket connected successfully")
            
            if self._on_connect:
                self._on_connect()
            
            # Start keep-alive thread
            self._start_keep_alive()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            with self._lock:
                self._state = ConnectionState.ERROR
            return False
    
    def _subscribe_streams(self) -> None:
        """Subscribe to all private streams."""
        if not self._ws:
            return
        
        # Subscribe to order stream
        if self._on_order:
            self._ws.order_stream(callback=self._handle_order)
            logger.debug("Subscribed to order stream")
        
        # Subscribe to position stream
        if self._on_position:
            self._ws.position_stream(callback=self._handle_position)
            logger.debug("Subscribed to position stream")
        
        # Subscribe to execution stream
        if self._on_execution:
            self._ws.execution_stream(callback=self._handle_execution)
            logger.debug("Subscribed to execution stream")
        
        # Subscribe to wallet stream
        if self._on_wallet:
            self._ws.wallet_stream(callback=self._handle_wallet)
            logger.debug("Subscribed to wallet stream")

    def _handle_order(self, message: Dict) -> None:
        """Handle order stream message."""
        self._last_message_time['order'] = time.time()
        try:
            if self._on_order:
                self._on_order(message)
        except Exception as e:
            logger.error(f"Error in order callback: {e}")

    def _handle_position(self, message: Dict) -> None:
        """Handle position stream message."""
        self._last_message_time['position'] = time.time()
        try:
            if self._on_position:
                self._on_position(message)
        except Exception as e:
            logger.error(f"Error in position callback: {e}")

    def _handle_execution(self, message: Dict) -> None:
        """Handle execution stream message."""
        self._last_message_time['execution'] = time.time()
        try:
            if self._on_execution:
                self._on_execution(message)
        except Exception as e:
            logger.error(f"Error in execution callback: {e}")

    def _handle_wallet(self, message: Dict) -> None:
        """Handle wallet stream message."""
        self._last_message_time['wallet'] = time.time()
        try:
            if self._on_wallet:
                self._on_wallet(message)
        except Exception as e:
            logger.error(f"Error in wallet callback: {e}")

    def _start_keep_alive(self) -> None:
        """Start keep-alive thread for connection monitoring."""
        self._stop_event.clear()
        self._keep_alive_thread = threading.Thread(
            target=self._keep_alive_loop,
            daemon=True,
            name="ws-keep-alive"
        )
        self._keep_alive_thread.start()

    def _keep_alive_loop(self) -> None:
        """Keep-alive loop - monitors connection health."""
        while not self._stop_event.is_set():
            try:
                # Check connection every 20 seconds (as per Bybit docs)
                self._stop_event.wait(20)

                if self._stop_event.is_set():
                    break

                # pybit handles ping/pong internally, we just monitor state
                if self._state != ConnectionState.CONNECTED:
                    logger.warning("Connection lost, attempting reconnect...")
                    self._reconnect()

            except Exception as e:
                logger.error(f"Keep-alive error: {e}")

    def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        with self._lock:
            if self._state == ConnectionState.RECONNECTING:
                return
            self._state = ConnectionState.RECONNECTING

        while self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1

            # Exponential backoff with jitter
            delay = min(
                self._reconnect_delay_base * (2 ** (self._reconnect_attempts - 1)),
                self._reconnect_delay_max
            )
            delay *= (0.5 + 0.5 * (time.time() % 1))  # Add jitter

            logger.info(f"Reconnect attempt {self._reconnect_attempts}/{self._max_reconnect_attempts} in {delay:.1f}s")
            time.sleep(delay)

            if self._stop_event.is_set():
                break

            # Try to reconnect
            self.disconnect()
            if self.connect():
                return

        logger.error("Max reconnection attempts reached")
        with self._lock:
            self._state = ConnectionState.ERROR

        if self._on_disconnect:
            self._on_disconnect()

    def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._stop_event.set()

        if self._keep_alive_thread and self._keep_alive_thread.is_alive():
            self._keep_alive_thread.join(timeout=5)

        if self._ws:
            try:
                self._ws.exit()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
            self._ws = None

        with self._lock:
            self._state = ConnectionState.DISCONNECTED

        logger.info("WebSocket disconnected")

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "state": self._state.value,
            "testnet": self.testnet,
            "reconnect_attempts": self._reconnect_attempts,
            "last_messages": {
                stream: datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                for stream, ts in self._last_message_time.items()
            }
        }

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False

