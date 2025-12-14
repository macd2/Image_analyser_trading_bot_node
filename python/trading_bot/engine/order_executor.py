"""
Order Executor - Clean order placement with Bybit API.
Handles order placement, cancellation, and modification.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional

from pybit.unified_trading import HTTP

from trading_bot.core.secrets_manager import get_bybit_credentials
from trading_bot.core.utils import normalize_symbol_for_bybit, smart_format_price

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Clean order executor for Bybit.
    Handles all order operations with proper error handling.
    """
    
    def __init__(self, testnet: bool = False, recv_window: int = 60000):
        """
        Initialize order executor.
        
        Args:
            testnet: Use testnet if True
            recv_window: Request timeout window in ms
        """
        self.testnet = testnet
        self.recv_window = recv_window
        self._session: Optional[HTTP] = None
        self._init_session()
    
    def _init_session(self) -> None:
        """Initialize Bybit HTTP session."""
        try:
            api_key, api_secret = get_bybit_credentials()
            self._session = HTTP(
                testnet=self.testnet,
                api_key=api_key,
                api_secret=api_secret,
                recv_window=self.recv_window,
            )
            logger.info(f"OrderExecutor initialized ({'testnet' if self.testnet else 'mainnet'})")
        except Exception as e:
            logger.error(f"Failed to initialize OrderExecutor: {e}")
            raise
    
    def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        order_link_id: Optional[str] = None,
        time_in_force: str = "GTC",
    ) -> Dict[str, Any]:
        """
        Place a limit order with optional TP/SL.
        
        Args:
            symbol: Trading symbol
            side: "Buy" or "Sell"
            qty: Order quantity
            price: Limit price
            take_profit: Take profit price (optional)
            stop_loss: Stop loss price (optional)
            order_link_id: Client order ID (optional)
            time_in_force: Time in force (default: GTC)
            
        Returns:
            Order result dict with order_id or error
        """
        if not self._session:
            return {"error": "Session not initialized"}
        
        normalized_symbol = normalize_symbol_for_bybit(symbol)
        order_link_id = order_link_id or str(uuid.uuid4())[:8]
        
        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": normalized_symbol,
            "side": side.capitalize(),
            "orderType": "Limit",
            "qty": str(qty),
            "price": str(price),
            "timeInForce": time_in_force,
            "orderLinkId": order_link_id,
        }
        
        if take_profit:
            params["takeProfit"] = str(take_profit)
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
        
        try:
            response = self._session.place_order(**params)
            
            if response.get("retCode") != 0:
                error_msg = response.get("retMsg", "Unknown error")
                logger.error(f"Order failed: {error_msg}")
                return {"error": error_msg, "retCode": response.get("retCode")}
            
            result = response.get("result", {})
            order_id = result.get("orderId")
            
            logger.info(f"Order placed: {symbol} {side} {qty} @ {price} (ID: {order_id})")
            
            return {
                "order_id": order_id,
                "order_link_id": result.get("orderLinkId"),
                "symbol": normalized_symbol,
                "side": side,
                "qty": qty,
                "price": price,
                "status": "submitted",
            }
            
        except Exception as e:
            logger.error(f"Order placement error: {e}")
            return {"error": str(e)}
    
    def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        order_link_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place a market order with optional TP/SL."""
        if not self._session:
            return {"error": "Session not initialized"}
        
        normalized_symbol = normalize_symbol_for_bybit(symbol)
        order_link_id = order_link_id or str(uuid.uuid4())[:8]
        
        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": normalized_symbol,
            "side": side.capitalize(),
            "orderType": "Market",
            "qty": str(qty),
            "orderLinkId": order_link_id,
        }
        
        if take_profit:
            params["takeProfit"] = str(take_profit)
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
        
        try:
            response = self._session.place_order(**params)
            
            if response.get("retCode") != 0:
                return {"error": response.get("retMsg", "Unknown error")}
            
            result = response.get("result", {})
            return {
                "order_id": result.get("orderId"),
                "order_link_id": result.get("orderLinkId"),
                "symbol": normalized_symbol,
                "side": side,
                "qty": qty,
                "status": "submitted",
            }
        except Exception as e:
            return {"error": str(e)}

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        order_link_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an order by ID or link ID."""
        if not self._session:
            return {"error": "Session not initialized"}

        if not order_id and not order_link_id:
            return {"error": "Either order_id or order_link_id required"}

        normalized_symbol = normalize_symbol_for_bybit(symbol)

        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": normalized_symbol,
        }

        if order_id:
            params["orderId"] = order_id
        if order_link_id:
            params["orderLinkId"] = order_link_id

        try:
            response = self._session.cancel_order(**params)

            if response.get("retCode") != 0:
                return {"error": response.get("retMsg", "Unknown error")}

            logger.info(f"Order cancelled: {symbol} (ID: {order_id or order_link_id})")
            return {"status": "cancelled", "order_id": order_id}

        except Exception as e:
            return {"error": str(e)}

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set leverage for a symbol."""
        if not self._session:
            return {"error": "Session not initialized"}

        normalized_symbol = normalize_symbol_for_bybit(symbol)

        try:
            response = self._session.set_leverage(
                category="linear",
                symbol=normalized_symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
            )

            if response.get("retCode") == 0:
                return {"status": "success", "leverage": leverage}
            elif response.get("retCode") == 110043:
                # Leverage not modified (already set)
                return {"status": "unchanged", "leverage": leverage}
            else:
                return {"error": response.get("retMsg", "Unknown error")}

        except Exception as e:
            return {"error": str(e)}

    def set_trading_stop(
        self,
        symbol: str,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        position_idx: int = 0,
    ) -> Dict[str, Any]:
        """Set or modify TP/SL for an existing position."""
        if not self._session:
            return {"error": "Session not initialized"}

        normalized_symbol = normalize_symbol_for_bybit(symbol)

        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": normalized_symbol,
            "positionIdx": position_idx,
        }

        if take_profit is not None:
            params["takeProfit"] = str(take_profit)
        if stop_loss is not None:
            params["stopLoss"] = str(stop_loss)

        try:
            response = self._session.set_trading_stop(**params)

            if response.get("retCode") != 0:
                return {"error": response.get("retMsg", "Unknown error")}

            logger.info(f"Trading stop set: {symbol} TP={take_profit} SL={stop_loss}")
            return {"status": "success"}

        except Exception as e:
            return {"error": str(e)}

    def get_instrument_info(self, symbol: str) -> Dict[str, Any]:
        """Get instrument info for position sizing."""
        if not self._session:
            return {"error": "Session not initialized"}

        normalized_symbol = normalize_symbol_for_bybit(symbol)

        try:
            response = self._session.get_instruments_info(
                category="linear",
                symbol=normalized_symbol,
            )

            if response.get("retCode") != 0:
                return {"error": response.get("retMsg", "Unknown error")}

            instruments = response.get("result", {}).get("list", [])
            if instruments:
                return instruments[0]
            return {"error": "Instrument not found"}

        except Exception as e:
            return {"error": str(e)}

    def get_wallet_balance(self, coin: str = "USDT") -> Dict[str, Any]:
        """Get wallet balance."""
        if not self._session:
            return {"error": "Session not initialized"}

        try:
            response = self._session.get_wallet_balance(
                accountType="UNIFIED",
                coin=coin,
            )

            if response.get("retCode") != 0:
                return {"error": response.get("retMsg", "Unknown error")}

            accounts = response.get("result", {}).get("list", [])
            if accounts:
                account = accounts[0]
                coins = account.get("coin", [])
                for c in coins:
                    if c.get("coin") == coin:
                        return {
                            "coin": coin,
                            # For UNIFIED accounts, use totalAvailableBalance from account level
                            # availableToWithdraw is deprecated and returns empty string
                            "available": float(account.get("totalAvailableBalance") or 0),
                            "wallet_balance": float(c.get("walletBalance") or 0),
                            "equity": float(account.get("totalEquity") or 0),
                            "unrealised_pnl": float(account.get("totalPerpUPL") or 0),
                        }
            return {"coin": coin, "available": 0, "wallet_balance": 0, "equity": 0}

        except Exception as e:
            return {"error": str(e)}

    def get_positions(self, settle_coin: str = "USDT") -> Dict[str, Any]:
        """Get open positions."""
        if not self._session:
            return {"error": "Session not initialized", "positions": []}

        try:
            response = self._session.get_positions(
                category="linear",
                settleCoin=settle_coin,
            )

            if response.get("retCode") != 0:
                return {"error": response.get("retMsg"), "positions": []}

            positions = []
            for pos in response.get("result", {}).get("list", []):
                size = float(pos.get("size") or 0)
                if size > 0:
                    positions.append({
                        "symbol": pos.get("symbol"),
                        "side": pos.get("side"),
                        "size": size,
                        "entry_price": float(pos.get("avgPrice") or 0),
                        "mark_price": float(pos.get("markPrice") or 0),
                        "pnl": float(pos.get("unrealisedPnl") or 0),
                        "leverage": pos.get("leverage"),
                    })

            return {"positions": positions}

        except Exception as e:
            return {"error": str(e), "positions": []}
