#!/usr/bin/env python3
"""
Debug script to test strategy exit check without Node.js.
Run this to see what's failing in the Python strategy exit check.
"""

import sys
import json
import logging

# Setup logging to see all messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def debug_strategy_exit():
    """Debug the strategy exit check."""
    
    print("\n=== DEBUGGING STRATEGY EXIT CHECK ===\n")
    
    # Step 1: Check if trading_bot module can be imported
    print("1. Testing trading_bot imports...")
    try:
        from trading_bot.strategies import StrategyFactory
        print("   ✓ StrategyFactory imported successfully")
    except ImportError as e:
        print(f"   ✗ FAILED to import StrategyFactory: {e}")
        return
    
    # Step 2: List available strategies
    print("\n2. Available strategies in registry:")
    try:
        strategies = StrategyFactory.get_available_strategies()
        if not strategies:
            print("   ✗ NO STRATEGIES REGISTERED!")
        else:
            for name in strategies.keys():
                print(f"   ✓ {name}")
    except Exception as e:
        print(f"   ✗ FAILED to get strategies: {e}")
        return
    
    # Step 3: Try to instantiate CointegrationSpreadTrader
    print("\n3. Testing CointegrationSpreadTrader instantiation...")
    try:
        from trading_bot.config.settings_v2 import ConfigV2
        from trading_bot.config.settings_v2 import (
            PathsConfig, OpenAIConfig, BybitConfig, TradingConfig, FileManagementConfig
        )
        
        config = ConfigV2(
            paths=PathsConfig(database="data/trading.db", charts="data/charts", logs="logs", session_file="data/"),
            openai=OpenAIConfig(api_key="", model="gpt-4", max_tokens=2000, temperature=0.7),
            bybit=BybitConfig(use_testnet=False, recv_window=5000, max_retries=3),
            trading=TradingConfig(
                paper_trading=True, auto_approve_trades=False, min_confidence_threshold=0.5,
                min_rr=1.0, risk_percentage=1.0, max_loss_usd=100.0, leverage=1,
                max_concurrent_trades=5, timeframe="1h", enable_position_tightening=False,
                enable_sl_tightening=False
            ),
            file_management=FileManagementConfig(enable_backup=False)
        )
        
        strategy_class = strategies.get("CointegrationSpreadTrader")
        if not strategy_class:
            print("   ✗ CointegrationSpreadTrader not found in registry")
            return
        
        strategy = strategy_class(
            config=config,
            instance_id="simulator",
            run_id=None,
            strategy_config={}
        )
        print("   ✓ CointegrationSpreadTrader instantiated successfully")
        
        # Step 4: Test should_exit method
        print("\n4. Testing should_exit method...")
        test_trade = {
            "symbol": "SOPHUSDT",
            "side": "Buy",
            "entry_price": 0.0642369,
            "stop_loss": 0.05,
            "take_profit": 0.08,
            "strategy_metadata": {
                "pair_symbol": "WETUSDT",
                "z_score_at_entry": 5.81,
                "z_exit_threshold": 0.2,
                "beta": -1.168,
                "spread_mean": 0.227,
                "spread_std": 0.037
            }
        }
        
        test_candle = {
            "timestamp": 1703337600000,
            "open": 0.0642,
            "high": 0.0645,
            "low": 0.0640,
            "close": 0.0643
        }
        
        result = strategy.should_exit(
            trade=test_trade,
            current_candle=test_candle,
            pair_candle=None
        )
        
        print(f"   ✓ should_exit returned: {json.dumps(result, indent=2)}")
        
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n=== ALL CHECKS PASSED ===\n")

if __name__ == "__main__":
    debug_strategy_exit()

