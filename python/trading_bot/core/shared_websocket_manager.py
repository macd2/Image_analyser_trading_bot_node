"""
Shared WebSocket Manager - Singleton for multi-instance trading.

MULTI-INSTANCE SUPPORT:
- Only ONE WebSocket connection per API key (Bybit limitation)
- Multiple StateManager instances can subscribe to the same WebSocket
- Messages are broadcast to all subscribers
- Each StateManager filters messages based on order_link_id prefix
"""

import logging
import threading
from typing import Dict, Any, Optional, Callable, List, Set
from pybit.unified_trading import WebSocket

from trading_bot.core.secrets_manager import get_bybit_credentials

logger = logging.getLogger(__name__)


class SharedWebSocketManager:
    """
    Singleton WebSocket manager for multi-instance trading.
    
    Features:
    - Single WebSocket connection shared across all instances
    - Broadcast messages to all registered subscribers
    - Thread-safe subscription management
    """
    
    _instance: Optional['SharedWebSocketManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls, testnet: bool = False):
        """Singleton pattern - only one instance per testnet/mainnet."""
        with cls._lock:
            # Use different singleton for testnet vs mainnet
            key = f"testnet_{testnet}"
            if not hasattr(cls, '_instances'):
                cls._instances: Dict[str, 'SharedWebSocketManager'] = {}
            
            if key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[key] = instance
                instance._initialized = False
            
            return cls._instances[key]
    
    def __init__(self, testnet: bool = False):
        """Initialize shared WebSocket manager (only once)."""
        if self._initialized:
            return
        
        self.testnet = testnet
        self._ws: Optional[WebSocket] = None
        self._connected = False
        self._subscribers_lock = threading.RLock()
        
        # Subscribers: {subscriber_id: {on_order, on_position, on_execution, on_wallet}}
        self._subscribers: Dict[str, Dict[str, Optional[Callable]]] = {}
        
        self._initialized = True
        logger.info(f"SharedWebSocketManager initialized ({'testnet' if testnet else 'mainnet'})")
    
    def subscribe(
        self,
        subscriber_id: str,
        on_order: Optional[Callable[[Dict], None]] = None,
        on_position: Optional[Callable[[Dict], None]] = None,
        on_execution: Optional[Callable[[Dict], None]] = None,
        on_wallet: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        """
        Subscribe to WebSocket messages.
        
        Args:
            subscriber_id: Unique ID for this subscriber (typically instance_id)
            on_order: Callback for order updates
            on_position: Callback for position updates
            on_execution: Callback for execution updates
            on_wallet: Callback for wallet updates
        """
        with self._subscribers_lock:
            self._subscribers[subscriber_id] = {
                'on_order': on_order,
                'on_position': on_position,
                'on_execution': on_execution,
                'on_wallet': on_wallet,
            }
            logger.info(f"Subscriber {subscriber_id} registered (total: {len(self._subscribers)})")
    
    def unsubscribe(self, subscriber_id: str) -> None:
        """Unsubscribe from WebSocket messages."""
        with self._subscribers_lock:
            if subscriber_id in self._subscribers:
                del self._subscribers[subscriber_id]
                logger.info(f"Subscriber {subscriber_id} unregistered (remaining: {len(self._subscribers)})")
    
    def connect(self) -> bool:
        """
        Connect to Bybit WebSocket (if not already connected).
        
        Returns:
            True if connected successfully
        """
        if self._connected and self._ws:
            logger.info("WebSocket already connected")
            return True
        
        try:
            api_key, api_secret = get_bybit_credentials()
            
            logger.info(f"Connecting shared WebSocket ({'testnet' if self.testnet else 'mainnet'})...")
            
            self._ws = WebSocket(
                testnet=self.testnet,
                channel_type="private",
                api_key=api_key,
                api_secret=api_secret,
            )
            
            # Subscribe to streams with broadcast handlers
            self._ws.order_stream(self._broadcast_order)
            self._ws.position_stream(self._broadcast_position)
            self._ws.execution_stream(self._broadcast_execution)
            self._ws.wallet_stream(self._broadcast_wallet)
            
            self._connected = True
            logger.info("✅ Shared WebSocket connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Shared WebSocket connection failed: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect WebSocket (only if no subscribers remain)."""
        with self._subscribers_lock:
            if len(self._subscribers) > 0:
                logger.warning(f"Cannot disconnect - {len(self._subscribers)} subscribers still active")
                return

        if self._ws:
            try:
                self._ws.exit()
                logger.info("Shared WebSocket disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting WebSocket: {e}")
            finally:
                self._ws = None
                self._connected = False

    # ==================== BROADCAST METHODS ====================

    def _broadcast_order(self, message: Dict) -> None:
        """Broadcast order message to all subscribers."""
        with self._subscribers_lock:
            for subscriber_id, callbacks in self._subscribers.items():
                if callbacks['on_order']:
                    try:
                        callbacks['on_order'](message)
                    except Exception as e:
                        logger.error(f"Error in {subscriber_id} order callback: {e}")

    def _broadcast_position(self, message: Dict) -> None:
        """Broadcast position message to all subscribers."""
        with self._subscribers_lock:
            for subscriber_id, callbacks in self._subscribers.items():
                if callbacks['on_position']:
                    try:
                        callbacks['on_position'](message)
                    except Exception as e:
                        logger.error(f"Error in {subscriber_id} position callback: {e}")

    def _broadcast_execution(self, message: Dict) -> None:
        """Broadcast execution message to all subscribers."""
        with self._subscribers_lock:
            for subscriber_id, callbacks in self._subscribers.items():
                if callbacks['on_execution']:
                    try:
                        callbacks['on_execution'](message)
                    except Exception as e:
                        logger.error(f"Error in {subscriber_id} execution callback: {e}")

    def _broadcast_wallet(self, message: Dict) -> None:
        """Broadcast wallet message to all subscribers."""
        with self._subscribers_lock:
            for subscriber_id, callbacks in self._subscribers.items():
                if callbacks['on_wallet']:
                    try:
                        callbacks['on_wallet'](message)
                    except Exception as e:
                        logger.error(f"Error in {subscriber_id} wallet callback: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected

    def get_subscriber_count(self) -> int:
        """Get number of active subscribers."""
        with self._subscribers_lock:
            return len(self._subscribers)

