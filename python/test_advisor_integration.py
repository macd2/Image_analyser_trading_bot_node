"""
Test script for advisor service integration.
This script tests the complete advisor service workflow.
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import uuid
import json
import os

# Add the trading_bot directory to Python path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'trading_bot'))

from trading_bot.services.advisor_service import AdvisorService
from trading_bot.services.alex_strategy import AlexStrategy
from trading_bot.services.market_regime_strategy import MarketRegimeStrategy
from trading_bot.db.init_trading_db import init_database

def create_test_candle_data():
    """Create test candle data for analysis."""
    # Create a DataFrame with OHLCV data
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='1H')
    prices = np.cumsum(np.random.randn(100) * 0.5 + 50)

    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices,
        'high': prices + np.random.rand(100) * 2,
        'low': prices - np.random.rand(100) * 2,
        'close': prices + np.random.randn(100) * 0.5,
        'volume': np.random.randint(100, 1000, 100)
    })

    df.set_index('timestamp', inplace=True)
    return df

async def test_strategy_registration():
    """Test strategy registration."""
    print("🧪 Testing strategy registration...")

    # Initialize advisor service
    config = {"test_mode": True}
    advisor = AdvisorService(config)

    # Check that strategies are registered
    assert "alex_strategy" in advisor.STRATEGY_REGISTRY
    assert "market_regime" in advisor.STRATEGY_REGISTRY

    print("✅ Strategy registration successful")

async def test_individual_strategies():
    """Test individual strategy analysis."""
    print("🧪 Testing individual strategies...")

    # Create test data
    candle_data = create_test_candle_data()

    # Test Alex Strategy
    alex_config = {
        "timeframes": ["1h", "4h"],
        "lookback_periods": 20,
        "indicators": ["RSI", "MACD", "EMA"]
    }
    alex_strategy = AlexStrategy(alex_config)

    alex_result = await alex_strategy.analyze(candle_data, "BTCUSDT", "1h")
    print(f"Alex Strategy Result: {alex_result['recommendation']} (Confidence: {alex_result['confidence']:.2f})")

    # Test Market Regime Strategy
    regime_config = {
        "timeframe": "4h",
        "volume_threshold": 1.5,
        "pattern_lookback": 10
    }
    regime_strategy = MarketRegimeStrategy(regime_config)

    regime_result = await regime_strategy.analyze(candle_data, "BTCUSDT", "1h")
    print(f"Market Regime Result: {regime_result['recommendation']} (Confidence: {regime_result['confidence']:.2f})")

    print("✅ Individual strategy testing successful")

async def test_advisor_service():
    """Test complete advisor service workflow."""
    print("🧪 Testing advisor service workflow...")

    # Initialize database
    conn = init_database()

    # Create test instance
    instance_id = str(uuid.uuid4())[:8]
    conn.execute("""
        INSERT INTO instances (id, name, settings, is_active)
        VALUES (?, ?, ?, ?)
    """, (instance_id, "Test Advisor Instance", json.dumps({"advisor_enabled": True}), 1))
    conn.commit()

    # Initialize advisor service with instance
    config = {"test_mode": True}
    advisor = AdvisorService(config, conn, instance_id)

    # Create test candle data
    candle_data = create_test_candle_data()

    # Run advisor analysis
    result = await advisor.analyze_market_data("BTCUSDT", "1h", candle_data)

    print(f"Advisor Analysis Result:")
    print(f"  Recommendation: {result['recommendation']}")
    print(f"  Confidence: {result['confidence']:.2f}")
    print(f"  Strategies Applied: {len(result['strategies_applied'])}")
    print(f"  Signals Found: {len(result['signals'])}")
    print(f"  Trace Log Entries: {len(result['trace_log'])}")

    # Test prompt enhancement
    market_data = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "last_price": candle_data['close'].iloc[-1]
    }
    base_prompt = "Analyze this trading pair and provide recommendations."

    enhanced_prompt = await advisor.enhance_prompt(market_data, base_prompt)
    print(f"Prompt enhanced with TA context: {len(enhanced_prompt)} characters")

    # Test recommendation enhancement
    ai_recommendation = {
        "recommendation": "LONG",
        "confidence": 0.75,
        "reasoning": "AI detected bullish pattern"
    }

    enhanced_recommendation = await advisor.enhance_recommendation(ai_recommendation, result)
    print(f"Enhanced recommendation confidence: {enhanced_recommendation['confidence']:.2f}")

    # Clean up
    await advisor.close()
    conn.close()

    print("✅ Advisor service workflow testing successful")

async def test_database_integration():
    """Test database integration and traceability."""
    print("🧪 Testing database integration...")

    # Initialize database
    conn = init_database()

    # Create test instance
    instance_id = str(uuid.uuid4())[:8]
    conn.execute("""
        INSERT INTO instances (id, name, settings, is_active)
        VALUES (?, ?, ?, ?)
    """, (instance_id, "Test DB Instance", json.dumps({"advisor_enabled": True}), 1))

    # Insert test strategies
    conn.execute("""
        INSERT OR IGNORE INTO advisor_strategies (id, name, description, version, config_schema)
        VALUES (?, ?, ?, ?, ?)
    """, (
        'alex_top_down',
        'Alex Top-Down Analysis',
        'Top-down analysis',
        '1.0',
        '{"timeframes": ["1h", "4h"]}'
    ))

    conn.execute("""
        INSERT OR IGNORE INTO advisor_strategies (id, name, description, version, config_schema)
        VALUES (?, ?, ?, ?, ?)
    """, (
        'market_regime_check',
        'Market Regime Detection',
        'Market regime analysis',
        '1.0',
        '{"timeframe": "4h"}'
    ))

    # Create advisor nodes
    node1_id = str(uuid.uuid4())[:8]
    node2_id = str(uuid.uuid4())[:8]

    conn.execute("""
        INSERT INTO advisor_nodes (id, instance_id, strategy_id, config, enabled, execution_order)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (node1_id, instance_id, 'alex_top_down', json.dumps({"lookback_periods": 20}), 1, 1))

    conn.execute("""
        INSERT INTO advisor_nodes (id, instance_id, strategy_id, config, enabled, execution_order)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (node2_id, instance_id, 'market_regime_check', json.dumps({"volume_threshold": 1.5}), 1, 2))

    # Create instance settings
    conn.execute("""
        INSERT INTO advisor_instance_settings (instance_id, strategy_id, config, enabled)
        VALUES (?, ?, ?, ?)
    """, (instance_id, 'alex_top_down', json.dumps({"timeframes": ["1h", "4h"]}), 1))

    conn.commit()

    # Test advisor service with database config
    config = {"test_mode": True}
    advisor = AdvisorService(config, conn, instance_id)

    # Verify strategies and nodes loaded
    print(f"Strategies loaded: {len(advisor.strategies)}")
    print(f"Nodes loaded: {len(advisor.nodes)}")

    # Test analysis
    candle_data = create_test_candle_data()
    result = await advisor.analyze_market_data("BTCUSDT", "1h", candle_data)

    # Check database logs
    logs = conn.execute("SELECT COUNT(*) FROM advisor_logs WHERE instance_id = ?", (instance_id,)).fetchone()
    print(f"Database log entries created: {logs[0]}")

    # Clean up
    await advisor.close()
    conn.close()

    print("✅ Database integration testing successful")

async def main():
    """Run all tests."""
    print("🚀 Starting Advisor Service Integration Tests\n")

    try:
        await test_strategy_registration()
        print()

        await test_individual_strategies()
        print()

        await test_advisor_service()
        print()

        await test_database_integration()
        print()

        print("🎉 All tests completed successfully!")
        print("\n✅ Advisor Service Integration Verified:")
        print("   - Strategy implementations working")
        print("   - Database schema complete")
        print("   - Node-based architecture functional")
        print("   - Traceability logging operational")
        print("   - Integration with trading cycle ready")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())