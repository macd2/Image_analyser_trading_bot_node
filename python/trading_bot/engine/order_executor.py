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
    
    def place_spread_based_orders(
        self,
        symbol_x: str,
        symbol_y: str,
        qty_x: float,
        qty_y: float,
        price_x: float,
        price_y: float,
        order_link_id: Optional[str] = None,
        time_in_force: str = "GTC",
    ) -> Dict[str, Any]:
        """
        Place TWO coordinated orders for spread-based trading.

        For spread-based strategies, we need to trade BOTH symbols with opposite sides.
        This method places both orders with coordinated order_link_ids to track them together.

        Args:
            symbol_x: First symbol (e.g., "BTCUSDT")
            symbol_y: Second symbol (e.g., "ETHUSDT")
            qty_x: Quantity for symbol X
            qty_y: Quantity for symbol Y
            price_x: Entry price for symbol X
            price_y: Entry price for symbol Y
            order_link_id: Base order link ID (will be suffixed with _x and _y)
            time_in_force: Time in force (default: GTC)

        Returns:
            Dict with both order results or error
        """
        if not self._session:
            return {"error": "Session not initialized"}

        base_link_id = order_link_id or str(uuid.uuid4())[:8]

        # For spread-based trades, qty_x and qty_y have signs indicating direction
        # qty_x > 0 means BUY, qty_x < 0 means SELL
        # qty_y > 0 means BUY, qty_y < 0 means SELL
        side_x = "Buy" if qty_x > 0 else "Sell"
        side_y = "Buy" if qty_y > 0 else "Sell"

        normalized_symbol_x = normalize_symbol_for_bybit(symbol_x)
        normalized_symbol_y = normalize_symbol_for_bybit(symbol_y)

        # Place first order (symbol X)
        params_x: Dict[str, Any] = {
            "category": "linear",
            "symbol": normalized_symbol_x,
            "side": side_x.capitalize(),
            "orderType": "Limit",
            "qty": str(abs(qty_x)),
            "price": str(price_x),
            "timeInForce": time_in_force,
            "orderLinkId": f"{base_link_id}_x",
        }

        try:
            response_x = self._session.place_order(**params_x)

            if response_x.get("retCode") != 0:
                error_msg = response_x.get("retMsg", "Unknown error")
                logger.error(f"Order X failed: {error_msg}")
                return {"error": f"Symbol X order failed: {error_msg}", "retCode": response_x.get("retCode")}

            result_x = response_x.get("result", {})
            order_id_x = result_x.get("orderId")

            # Place second order (symbol Y)
            params_y: Dict[str, Any] = {
                "category": "linear",
                "symbol": normalized_symbol_y,
                "side": side_y.capitalize(),
                "orderType": "Limit",
                "qty": str(abs(qty_y)),
                "price": str(price_y),
                "timeInForce": time_in_force,
                "orderLinkId": f"{base_link_id}_y",
            }

            response_y = self._session.place_order(**params_y)

            if response_y.get("retCode") != 0:
                error_msg = response_y.get("retMsg", "Unknown error")
                logger.error(f"Order Y failed: {error_msg}. Cancelling order X ({order_id_x})")
                # Cancel the first order since the second failed
                self.cancel_order(symbol_x, order_id=order_id_x)
                return {"error": f"Symbol Y order failed: {error_msg}. Order X cancelled.", "retCode": response_y.get("retCode")}

            result_y = response_y.get("result", {})
            order_id_y = result_y.get("orderId")

            logger.info(
                f"Spread-based orders placed: {symbol_x} {side_x} {abs(qty_x)} @ {price_x} (ID: {order_id_x}) | "
                f"{symbol_y} {side_y} {abs(qty_y)} @ {price_y} (ID: {order_id_y})"
            )

            return {
                "order_id_x": order_id_x,
                "order_id_y": order_id_y,
                "order_link_id_x": result_x.get("orderLinkId"),
                "order_link_id_y": result_y.get("orderLinkId"),
                "symbol_x": normalized_symbol_x,
                "symbol_y": normalized_symbol_y,
                "side_x": side_x,
                "side_y": side_y,
                "qty_x": abs(qty_x),
                "qty_y": abs(qty_y),
                "price_x": price_x,
                "price_y": price_y,
                "status": "submitted",
            }

        except Exception as e:
            logger.error(f"Spread-based order placement error: {e}")
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
        """
        Get open positions from Bybit API.

        Returns the raw Bybit API response format with retCode for compatibility
        with count_open_positions_and_orders() and other functions that expect
        the standard Bybit API response structure.

        Returns:
            Dict with Bybit API response format:
            - retCode: 0 for success, non-zero for error
            - retMsg: Status message
            - result: Dict with 'list' containing position data
        """
        if not self._session:
            return {
                "retCode": -1,
                "retMsg": "Session not initialized",
                "result": {"list": []}
            }

        try:
            response = self._session.get_positions(
                category="linear",
                settleCoin=settle_coin,
            )

            # Return the raw Bybit API response (which has retCode, retMsg, result)
            return response

        except Exception as e:
            return {
                "retCode": -1,
                "retMsg": str(e),
                "result": {"list": []}
            }

    def get_open_orders(self, **kwargs) -> Dict[str, Any]:
        """
        Get open orders from Bybit API.

        Returns the raw Bybit API response format with retCode for compatibility
        with count_open_positions_and_orders() and other functions that expect
        the standard Bybit API response structure.

        Args:
            **kwargs: Parameters to pass to Bybit API (openOnly, limit, symbol, etc.)

        Returns:
            Dict with Bybit API response format:
            - retCode: 0 for success, non-zero for error
            - retMsg: Status message
            - result: Dict with 'list' containing order data
        """
        if not self._session:
            return {
                "retCode": -1,
                "retMsg": "Session not initialized",
                "result": {"list": []}
            }

        try:
            # Set defaults for Bybit API
            kwargs.setdefault("category", "linear")
            kwargs.setdefault("openOnly", 0)  # 0 returns open orders, 1 returns closed orders
            kwargs.setdefault("limit", 50)

            # Normalize symbol if provided
            if "symbol" in kwargs:
                kwargs["symbol"] = normalize_symbol_for_bybit(kwargs["symbol"])

            # Bybit API requires symbol, settleCoin, or baseCoin for open orders
            if "symbol" not in kwargs and "settleCoin" not in kwargs and "baseCoin" not in kwargs:
                kwargs.setdefault("settleCoin", "USDT")

            response = self._session.get_open_orders(**kwargs)

            # Return the raw Bybit API response (which has retCode, retMsg, result)
            return response

        except Exception as e:
            return {
                "retCode": -1,
                "retMsg": str(e),
                "result": {"list": []}
            }
