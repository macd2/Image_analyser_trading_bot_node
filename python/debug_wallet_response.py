#!/usr/bin/env python3
"""
Debug script to see the full wallet response from Bybit API.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_bot.engine.order_executor import OrderExecutor


def debug_wallet():
    """Print full wallet response."""
    try:
        executor = OrderExecutor(testnet=False)
        
        # Get raw response
        if not executor._session:
            print("❌ Session not initialized")
            return
        
        response = executor._session.get_wallet_balance(
            accountType="UNIFIED",
            coin="USDT",
        )
        
        print("Full Bybit Wallet Response:")
        print(json.dumps(response, indent=2))
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_wallet()

