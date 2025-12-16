"""
Mock test for PromptStrategy - Tests with mock config (no database required).

This test verifies:
1. PromptStrategy can be instantiated with mock config
2. Strategy components are properly initialized
3. Strategy validates output format correctly
4. Strategy is completely independent from TradingCycle
"""

import logging
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Mock config classes
@dataclass
class MockPathsConfig:
    database: str = "data/trading.db"
    charts: str = "data/charts"
    logs: str = "logs"
    session_file: str = "data/"


@dataclass
class MockOpenAIConfig:
    api_key: str = "mock-key"
    model: str = "gpt-4-vision"
    assistant_id: str = "mock-assistant"
    max_tokens: int = 4096
    temperature: float = 0.1


@dataclass
class MockCircuitBreakerConfig:
    error_threshold: int = 5
    recovery_timeout: int = 300
    max_recv_window: int = 600000
    backoff_multiplier: float = 2.0
    jitter_range: float = 0.1


@dataclass
class MockBybitConfig:
    use_testnet: bool = True
    recv_window: int = 30000
    max_retries: int = 5
    circuit_breaker: MockCircuitBreakerConfig = field(default_factory=MockCircuitBreakerConfig)


@dataclass
class MockTradingConfig:
    paper_trading: bool = True
    auto_approve_trades: bool = False
    min_confidence_threshold: float = 0.7
    min_rr: float = 1.5
    risk_percentage: float = 2.0
    max_loss_usd: float = 100.0
    leverage: int = 1
    max_concurrent_trades: int = 5
    timeframe: str = "1h"
    enable_position_tightening: bool = False
    enable_sl_tightening: bool = False
    rr_tightening_steps: Dict[str, Any] = field(default_factory=dict)
    use_enhanced_position_sizing: bool = True
    min_position_value_usd: float = 50.0


@dataclass
class MockFileManagementConfig:
    storage_type: str = "local"
    backup_enabled: bool = False


@dataclass
class MockConfigV2:
    paths: MockPathsConfig = field(default_factory=MockPathsConfig)
    openai: MockOpenAIConfig = field(default_factory=MockOpenAIConfig)
    bybit: MockBybitConfig = field(default_factory=MockBybitConfig)
    trading: MockTradingConfig = field(default_factory=MockTradingConfig)
    file_management: MockFileManagementConfig = field(default_factory=MockFileManagementConfig)
    tradingview: Optional[Any] = None


def test_strategy_with_mock_config():
    """Test 1: PromptStrategy works with mock config (no database)."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        
        # Create mock config
        mock_config = MockConfigV2()
        
        # Instantiate strategy
        strategy = PromptStrategy(
            config=mock_config,
            instance_id="mock-instance",
            run_id="mock-run"
        )
        
        assert strategy is not None
        assert strategy.instance_id == "mock-instance"
        assert strategy.run_id == "mock-run"
        
        logger.info("✓ Test 1 PASSED: PromptStrategy works with mock config")
        logger.info(f"  Instance ID: {strategy.instance_id}")
        logger.info(f"  Run ID: {strategy.run_id}")
        return True
    except Exception as e:
        logger.error(f"✗ Test 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_strategy_components_initialized():
    """Test 2: All strategy components are properly initialized."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        
        mock_config = MockConfigV2()
        strategy = PromptStrategy(config=mock_config)
        
        # Verify components exist
        assert hasattr(strategy, "sourcer"), "Missing sourcer"
        assert hasattr(strategy, "cleaner"), "Missing cleaner"
        assert hasattr(strategy, "analyzer"), "Missing analyzer"
        
        # Verify they're not None
        assert strategy.sourcer is not None, "Sourcer is None"
        assert strategy.cleaner is not None, "Cleaner is None"
        assert strategy.analyzer is not None, "Analyzer is None"
        
        logger.info("✓ Test 2 PASSED: All components initialized")
        logger.info(f"  Sourcer: {strategy.sourcer.__class__.__name__}")
        logger.info(f"  Cleaner: {strategy.cleaner.__class__.__name__}")
        logger.info(f"  Analyzer: {strategy.analyzer.__class__.__name__}")
        return True
    except Exception as e:
        logger.error(f"✗ Test 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_output_validation():
    """Test 3: Output validation works correctly."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        
        mock_config = MockConfigV2()
        strategy = PromptStrategy(config=mock_config)
        
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
        
        logger.info("✓ Test 3 PASSED: Output validation works")
        return True
    except Exception as e:
        logger.error(f"✗ Test 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_strategy_independence():
    """Test 4: Strategy is independent from TradingCycle."""
    try:
        from trading_bot.strategies.prompt import PromptStrategy
        
        # Verify PromptStrategy doesn't import TradingCycle
        import inspect
        source = inspect.getsource(PromptStrategy)
        
        assert "TradingCycle" not in source, "PromptStrategy imports TradingCycle"
        assert "trading_cycle" not in source.lower(), "PromptStrategy references trading_cycle"
        
        logger.info("✓ Test 4 PASSED: Strategy is independent from TradingCycle")
        return True
    except Exception as e:
        logger.error(f"✗ Test 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all mock tests."""
    logger.info("\n" + "="*60)
    logger.info("PROMPT STRATEGY MOCK TESTS (No Database Required)")
    logger.info("="*60 + "\n")
    
    tests = [
        test_strategy_with_mock_config,
        test_strategy_components_initialized,
        test_output_validation,
        test_strategy_independence,
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

