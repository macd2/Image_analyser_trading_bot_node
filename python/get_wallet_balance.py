#!/usr/bin/env python3
"""
Fetch wallet balance from Bybit API.
Used by /api/bot/wallet endpoint as a fallback when WebSocket data is unavailable.
"""

import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_bot.engine.order_executor import OrderExecutor


def get_wallet_balance():
    """Fetch wallet balance from Bybit."""
    try:
        executor = OrderExecutor(testnet=False)
        wallet = executor.get_wallet_balance()
        
        if "error" in wallet:
            return {
                "error": wallet["error"],
                "coin": "USDT",
                "walletBalance": "0",
                "availableToWithdraw": "0",
                "equity": "0",
                "unrealisedPnl": "0"
            }
        
        # Convert to string format for consistency with WebSocket data
        return {
            "coin": wallet.get("coin", "USDT"),
            "walletBalance": str(wallet.get("wallet_balance", 0)),
            "availableToWithdraw": str(wallet.get("available", 0)),
            "equity": str(wallet.get("equity", 0)),
            "unrealisedPnl": str(wallet.get("unrealised_pnl", 0))
        }
    except Exception as e:
        return {
            "error": str(e),
            "coin": "USDT",
            "walletBalance": "0",
            "availableToWithdraw": "0",
            "equity": "0",
            "unrealisedPnl": "0"
        }


if __name__ == "__main__":
    result = get_wallet_balance()
    print(json.dumps(result))

