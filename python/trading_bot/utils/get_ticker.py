#!/usr/bin/env python3
"""
Get current ticker price for a symbol from Bybit.
Usage: python get_ticker.py BTCUSDT
"""

import sys
import json
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def get_ticker(symbol: str) -> dict:
    """
    Fetch current ticker data from Bybit public API.
    
    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        
    Returns:
        dict with lastPrice, bid1Price, ask1Price, etc.
    """
    try:
        # Bybit public API endpoint for tickers
        url = "https://api.bybit.com/v5/market/tickers"
        params = {
            "category": "linear",
            "symbol": symbol
        }
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("retCode") != 0:
            return {"error": f"Bybit API error: {data.get('retMsg', 'Unknown error')}"}
        
        ticker_list = data.get("result", {}).get("list", [])
        if not ticker_list:
            return {"error": f"No ticker data found for {symbol}"}
        
        ticker = ticker_list[0]
        
        return {
            "symbol": ticker.get("symbol"),
            "lastPrice": ticker.get("lastPrice"),
            "bid1Price": ticker.get("bid1Price"),
            "ask1Price": ticker.get("ask1Price"),
            "markPrice": ticker.get("markPrice"),
            "price24hPcnt": ticker.get("price24hPcnt"),
            "highPrice24h": ticker.get("highPrice24h"),
            "lowPrice24h": ticker.get("lowPrice24h"),
            "volume24h": ticker.get("volume24h"),
        }
        
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python get_ticker.py SYMBOL"}), flush=True)
        sys.exit(1)
    
    symbol = sys.argv[1]
    result = get_ticker(symbol)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()

