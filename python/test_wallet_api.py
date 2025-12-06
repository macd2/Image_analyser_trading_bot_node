#!/usr/bin/env python3
"""
Test script to check if Bybit wallet API is working.
Run with: python python/test_wallet_api.py
"""

import sys
from pathlib import Path

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.engine.order_executor import OrderExecutor

def test_wallet_api():
    """Test wallet API call."""
    print("Testing Bybit wallet API...")
    
    try:
        executor = OrderExecutor(testnet=False)
        print("✅ OrderExecutor initialized")
        
        wallet = executor.get_wallet_balance()
        print(f"\n📊 Wallet response:")
        print(f"   {wallet}")
        
        if "error" in wallet:
            print(f"\n❌ Error: {wallet['error']}")
            return False
        
        print(f"\n✅ Success!")
        print(f"   Balance: ${wallet.get('wallet_balance', 0):.2f}")
        print(f"   Available: ${wallet.get('available', 0):.2f}")
        print(f"   Equity: ${wallet.get('equity', 0):.2f}")
        return True
        
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_wallet_api()
    sys.exit(0 if success else 1)

