"""Exchange data types and structures for Bybit integration."""
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


class ExchangeTradeState(Enum):
    """Simplified trade states based on exchange data."""
    PENDING = "pending"           # Order placed but not filled
    FILLED = "filled"             # Order filled, position open
    CLOSED = "closed"             # Position closed
    CANCELLED = "cancelled"       # Order cancelled

def _safe_float_conversion(value: Any, default: float = 0.0) -> float:
    """Safely converts a value to float, handling None or empty strings."""
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def _safe_int_conversion(value: Any, default: int = 0) -> int:
    """Safely converts a value to int, handling None or empty strings."""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

@dataclass
class ExchangeOrderData:
    """Exchange order data structure."""
    order_id: str
    symbol: str
    side: str                     # Buy/Sell
    qty: float
    price: float
    order_status: str             # NEW, FILLED, CANCELLED, etc.
    cum_exec_qty: float
    avg_price: float
    created_time: int
    updated_time: int
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExchangeOrderData':
        """Create ExchangeOrderData from dictionary."""
        return cls(
            order_id=str(data.get('orderId', '')),
            symbol=str(data.get('symbol', '')),
            side=str(data.get('side', 'Buy')),
            qty=_safe_float_conversion(data.get('qty', 0)),
            price=_safe_float_conversion(data.get('price', 0)),
            order_status=str(data.get('orderStatus', 'NEW')),
            cum_exec_qty=_safe_float_conversion(data.get('cumExecQty', 0)),
            avg_price=_safe_float_conversion(data.get('avgPrice', 0)),
            created_time=_safe_int_conversion(data.get('createdTime', 0)),
            updated_time=_safe_int_conversion(data.get('updatedTime', 0))
        )


@dataclass
class ExchangePositionData:
    """Exchange position data structure."""
    symbol: str
    side: str
    size: float
    avg_price: float
    unrealised_pnl: float
    cum_realised_pnl: float
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExchangePositionData':
        """Create ExchangePositionData from dictionary."""
        return cls(
            symbol=str(data.get('symbol', '')),
            side=str(data.get('side', 'Buy')),
            size=_safe_float_conversion(data.get('size', 0)),
            avg_price=_safe_float_conversion(data.get('avgPrice', 0)),
            unrealised_pnl=_safe_float_conversion(data.get('unrealisedPnl', 0)),
            cum_realised_pnl=_safe_float_conversion(data.get('cumRealisedPnl', 0))
        )


@dataclass
class ExchangeClosedPnlData:
    """Exchange closed PnL data structure."""
    order_id: str
    symbol: str
    side: str
    qty: float
    avg_entry_price: float
    avg_exit_price: float
    closed_pnl: float
    created_time: int
    updated_time: int
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExchangeClosedPnlData':
        """Create ExchangeClosedPnlData from dictionary."""
        return cls(
            order_id=str(data.get('orderId', '')),
            symbol=str(data.get('symbol', '')),
            side=str(data.get('side', 'Buy')),
            qty=_safe_float_conversion(data.get('qty', 0)),
            avg_entry_price=_safe_float_conversion(data.get('avgEntryPrice', 0)),
            avg_exit_price=_safe_float_conversion(data.get('avgExitPrice', 0)),
            closed_pnl=_safe_float_conversion(data.get('closedPnl', 0)),
            created_time=_safe_int_conversion(data.get('createdTime', 0)),
            updated_time=_safe_int_conversion(data.get('updatedTime', 0))
        )
