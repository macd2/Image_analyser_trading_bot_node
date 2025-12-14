#!/usr/bin/env python3
"""
Fetch open orders from Bybit REST API
Used by Node.js server to get initial state when WebSocket connects
"""

import json
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from trading_bot.engine.order_executor import OrderExecutor

    # Create order executor (handles Bybit API directly)
    testnet = os.getenv('BYBIT_TESTNET', 'false').lower() == 'true'
    executor = OrderExecutor(testnet=testnet)

    # Fetch open orders (openOnly=0 returns all orders including open ones)
    # Note: Bybit API openOnly parameter seems inverted - 0 returns open orders, 1 returns closed
    response = executor.get_open_orders(
        category='linear',
        settleCoin='USDT',
        openOnly=0,  # Returns all orders including open/pending ones
        limit=50
    )

    # Extract orders from response
    orders = []
    if response.get('retCode') == 0 and response.get('result'):
        orders = response['result'].get('list', [])

    # Output as JSON
    print(json.dumps({
        'success': response.get('retCode') == 0,
        'orders': orders,
        'message': response.get('retMsg', '')
    }))

except Exception as e:
    print(json.dumps({
        'success': False,
        'orders': [],
        'message': str(e)
    }))
    sys.exit(1)

