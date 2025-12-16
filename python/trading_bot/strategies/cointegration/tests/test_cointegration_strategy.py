#!/usr/bin/env python3
"""
Test script for CointegrationAnalysisModule with real candle data.

Usage:
    source venv/bin/activate
    python test_cointegration_strategy.py
"""

import asyncio
import sys
import os

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
from trading_bot.config.settings_v2 import ConfigV2
from trading_bot.db.client import query, get_connection


async def test_cointegration():
    """Test cointegration strategy with real candle data."""
    
    # Get first instance from postgres
    conn = get_connection()
    instances = query(conn, "SELECT id, name FROM instances LIMIT 1")
    
    if not instances:
        print("❌ No instances found in database!")
        return False
    
    instance_id = instances[0]['id']
    instance_name = instances[0]['name']
    print(f"✅ Using instance: {instance_id} ({instance_name})")
    print()
    
    # Load config with instance_id
    config = ConfigV2.load(instance_id=instance_id)
    
    # Create strategy
    strategy = CointegrationAnalysisModule(
        config=config,
        instance_id=instance_id,
        run_id="test-run-001",
        heartbeat_callback=lambda message="", **kwargs: print(f"[HB] {message}")
    )
    
    print("=" * 70)
    print("🔄 COINTEGRATION STRATEGY TEST - REAL CANDLE DATA")
    print("=" * 70)
    print(f"Instance ID: {instance_id}")
    print()
    
    # Run analysis cycle
    # Note: symbols parameter is ignored - strategy uses pairs from config
    results = await strategy.run_analysis_cycle(
        symbols=["IGNORED"],  # This is ignored by cointegration strategy
        timeframe="1h",       # This is ignored - uses analysis_timeframe from config
        cycle_id="test-cycle-001"
    )
    
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    
    if not results:
        print("❌ No results returned")
        return False
    
    for result in results:
        symbol = result.get('symbol', 'UNKNOWN')
        print(f"\n{symbol}:")
        print(f"  Recommendation: {result.get('recommendation', 'N/A')}")
        
        confidence = result.get('confidence')
        if confidence is not None:
            print(f"  Confidence: {confidence:.2%}")
        else:
            print(f"  Confidence: N/A")
        
        entry_price = result.get('entry_price')
        if entry_price is not None:
            print(f"  Entry Price: {entry_price:.2f}")
        else:
            print(f"  Entry Price: N/A (skipped)")
        
        stop_loss = result.get('stop_loss')
        if stop_loss is not None:
            print(f"  Stop Loss: {stop_loss:.2f}")
        
        take_profit = result.get('take_profit')
        if take_profit is not None:
            print(f"  Take Profit: {take_profit:.2f}")
        
        risk_reward = result.get('risk_reward')
        if risk_reward is not None:
            print(f"  Risk/Reward: {risk_reward:.2f}")
        
        setup_quality = result.get('setup_quality')
        if setup_quality is not None:
            print(f"  Setup Quality: {setup_quality:.2f}")
        
        analysis = result.get('analysis', {})
        if isinstance(analysis, dict) and analysis:
            print(f"  Z-Score: {analysis.get('z_score', 'N/A')}")
            print(f"  Mean Reverting: {analysis.get('is_mean_reverting', 'N/A')}")
            print(f"  Size Multiplier: {analysis.get('size_multiplier', 'N/A')}")
        elif isinstance(analysis, str) and analysis:
            print(f"  Note: {analysis}")
    
    print("\n" + "=" * 70)
    print("✅ Test completed successfully")
    print("=" * 70)
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_cointegration())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

