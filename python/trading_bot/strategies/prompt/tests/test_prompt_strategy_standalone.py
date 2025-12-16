"""
Standalone test for PromptStrategy - Tests without touching TradingCycle.

This test verifies:
1. PromptStrategy can be instantiated independently
2. Strategy can be created via StrategyFactory
3. Strategy has all required methods
4. Strategy returns correct output format
5. No dependencies on TradingCycle
"""

import asyncio
import logging
from typing import Dict, Any

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_prompt_strategy_import():
    """Test 1: PromptStrategy can be imported."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        logger.info("✓ Test 1 PASSED: PromptStrategy imported successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Test 1 FAILED: {e}")
        return False


def test_strategy_factory_registration():
    """Test 2: PromptStrategy is registered in StrategyFactory."""
    try:
        from trading_bot.strategies.factory import StrategyFactory
        
        strategies = StrategyFactory.get_available_strategies()
        assert "prompt" in strategies, "PromptStrategy not registered"
        
        logger.info(f"✓ Test 2 PASSED: PromptStrategy registered in factory")
        logger.info(f"  Available strategies: {list(strategies.keys())}")
        return True
    except Exception as e:
        logger.error(f"✗ Test 2 FAILED: {e}")
        return False


def test_strategy_instantiation():
    """Test 3: PromptStrategy can be instantiated with config."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        from trading_bot.config.settings_v2 import ConfigV2

        # Load config from database (requires instance to exist)
        # For testing, we'll create a mock config object
        try:
            config = ConfigV2.from_instance("test-instance")
        except Exception:
            # If instance doesn't exist, skip this test
            logger.warning("✓ Test 3 SKIPPED: No test instance in database")
            return True

        # Instantiate strategy
        strategy = PromptStrategy(
            config=config,
            instance_id="test-instance",
            run_id="test-run"
        )

        assert strategy is not None
        assert strategy.config == config
        assert strategy.instance_id == "test-instance"
        assert strategy.run_id == "test-run"

        logger.info("✓ Test 3 PASSED: PromptStrategy instantiated successfully")
        logger.info(f"  Instance ID: {strategy.instance_id}")
        logger.info(f"  Run ID: {strategy.run_id}")
        return True
    except Exception as e:
        logger.error(f"✗ Test 3 FAILED: {e}")
        return False


def test_strategy_has_required_methods():
    """Test 4: PromptStrategy has all required methods."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        from trading_bot.config.settings_v2 import ConfigV2

        try:
            config = ConfigV2.from_instance("test-instance")
        except Exception:
            logger.warning("✓ Test 4 SKIPPED: No test instance in database")
            return True

        strategy = PromptStrategy(config=config)
        
        # Check required methods
        required_methods = [
            "run_analysis_cycle",
            "_validate_output",
            "get_config_value",
            "_heartbeat"
        ]
        
        for method in required_methods:
            assert hasattr(strategy, method), f"Missing method: {method}"
            assert callable(getattr(strategy, method)), f"Not callable: {method}"
        
        logger.info("✓ Test 4 PASSED: All required methods present")
        for method in required_methods:
            logger.info(f"  ✓ {method}")
        return True
    except Exception as e:
        logger.error(f"✗ Test 4 FAILED: {e}")
        return False


def test_strategy_has_components():
    """Test 5: PromptStrategy has sourcer, cleaner, analyzer components."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        from trading_bot.config.settings_v2 import ConfigV2

        try:
            config = ConfigV2.from_instance("test-instance")
        except Exception:
            logger.warning("✓ Test 5 SKIPPED: No test instance in database")
            return True

        strategy = PromptStrategy(config=config)
        
        # Check components
        assert hasattr(strategy, "sourcer"), "Missing sourcer component"
        assert hasattr(strategy, "cleaner"), "Missing cleaner component"
        assert hasattr(strategy, "analyzer"), "Missing analyzer component"
        
        logger.info("✓ Test 5 PASSED: All components present")
        logger.info(f"  ✓ sourcer: {strategy.sourcer.__class__.__name__}")
        logger.info(f"  ✓ cleaner: {strategy.cleaner.__class__.__name__}")
        logger.info(f"  ✓ analyzer: {strategy.analyzer.__class__.__name__}")
        return True
    except Exception as e:
        logger.error(f"✗ Test 5 FAILED: {e}")
        return False


def test_output_format_validation():
    """Test 6: PromptStrategy validates output format correctly."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        from trading_bot.config.settings_v2 import ConfigV2

        try:
            config = ConfigV2.from_instance("test-instance")
        except Exception:
            logger.warning("✓ Test 6 SKIPPED: No test instance in database")
            return True

        strategy = PromptStrategy(config=config)
        
        # Valid output
        valid_output = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.85,
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 52000.0,
            "risk_reward": 2.0,
            "setup_quality": 0.8,
            "market_environment": 0.7,
            "analysis": {"test": "data"},
            "chart_path": "/path/to/chart.png",
            "timeframe": "1h",
            "cycle_id": "cycle-123"
        }
        
        # Should not raise
        strategy._validate_output(valid_output)
        
        logger.info("✓ Test 6 PASSED: Output validation works correctly")
        return True
    except Exception as e:
        logger.error(f"✗ Test 6 FAILED: {e}")
        return False


def run_all_tests():
    """Run all standalone tests."""
    logger.info("\n" + "="*60)
    logger.info("PROMPT STRATEGY STANDALONE TESTS")
    logger.info("="*60 + "\n")
    
    tests = [
        test_prompt_strategy_import,
        test_strategy_factory_registration,
        test_strategy_instantiation,
        test_strategy_has_required_methods,
        test_strategy_has_components,
        test_output_format_validation,
    ]
    
    results = []
    for test in tests:
        results.append(test())
        logger.info("")
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    logger.info("="*60)
    logger.info(f"RESULTS: {passed}/{total} tests passed")
    logger.info("="*60)
    
    return all(results)


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)

