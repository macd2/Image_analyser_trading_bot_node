from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PositionInfo:
    """Information about an open position."""
    symbol: str
    side: str  # 'Buy' or 'Sell'
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    current_stop_loss: Optional[float]
    current_take_profit: Optional[float]
    position_idx: int
    risk_amount: float  # Original risk amount (1R)
    timeframe: Optional[str] = None  # Trading timeframe (e.g., '1h', '4h', '1d')
    created_at: Optional[datetime] = None  # When the trade was created
    last_tightened_milestone: Optional[str] = None  # Last milestone at which SL was tightened
    has_trade_data: bool = False  # Whether this position has associated trade data
