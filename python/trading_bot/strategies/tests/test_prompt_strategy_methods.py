"""
Test PromptStrategy implementation of abstract methods.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../'))

import pytest
from unittest.mock import Mock
from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy


class TestPromptStrategyMethods:
    """Test PromptStrategy method implementations."""
    
    @pytest.fixture
    def strategy(self):
        """Create a PromptStrategy instance for testing."""
        config = Mock()
        config.openai = Mock(api_key="test-key")
        config.trading = Mock(timeframe="1h")
        config.paths = Mock(charts="data/charts")
        config.tradingview = Mock(target_chart=None)
        
        return PromptStrategy(config=config)
    
    def test_strategy_type_and_name(self, strategy):
        """Test strategy type and name are set correctly."""
        assert strategy.STRATEGY_TYPE == "price_based"
        assert strategy.STRATEGY_NAME == "PromptStrategy"
        assert strategy.STRATEGY_VERSION == "1.0"
        print("✓ Strategy type, name, and version set correctly")
    
    def test_validate_signal_long_valid(self, strategy):
        """Test validation of valid long signal."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
        }
        
        assert strategy.validate_signal(signal) is True
        print("✓ Valid long signal passes validation")
    
    def test_validate_signal_short_valid(self, strategy):
        """Test validation of valid short signal."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 101.0,
            "take_profit": 98.0,
        }
        
        assert strategy.validate_signal(signal) is True
        print("✓ Valid short signal passes validation")
    
    def test_validate_signal_low_rr(self, strategy):
        """Test that low RR ratio fails validation."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 99.5,
            "take_profit": 100.2,  # RR = 0.4, below default 1.0
        }
        
        with pytest.raises(ValueError, match="RR ratio"):
            strategy.validate_signal(signal)
        
        print("✓ Low RR ratio fails validation")
    
    def test_validate_signal_wrong_order(self, strategy):
        """Test that wrong price order fails validation."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 101.0,  # Should be below entry for long
            "take_profit": 102.0,
        }
        
        with pytest.raises(ValueError, match="wrong order"):
            strategy.validate_signal(signal)
        
        print("✓ Wrong price order fails validation")
    
    def test_calculate_risk_metrics_long(self, strategy):
        """Test risk metrics calculation for long."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
        }
        
        metrics = strategy.calculate_risk_metrics(signal)
        
        assert metrics["risk_per_unit"] == 2.0
        assert metrics["reward_per_unit"] == 4.0
        assert metrics["risk_reward_ratio"] == 2.0
        print(f"✓ Long risk metrics: {metrics}")
    
    def test_calculate_risk_metrics_short(self, strategy):
        """Test risk metrics calculation for short."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 102.0,
            "take_profit": 96.0,
        }
        
        metrics = strategy.calculate_risk_metrics(signal)
        
        assert metrics["risk_per_unit"] == 2.0
        assert metrics["reward_per_unit"] == 4.0
        assert metrics["risk_reward_ratio"] == 2.0
        print(f"✓ Short risk metrics: {metrics}")
    
    def test_get_exit_condition(self, strategy):
        """Test exit condition metadata."""
        exit_cond = strategy.get_exit_condition()
        
        assert exit_cond["type"] == "price_level"
        assert "description" in exit_cond
        print(f"✓ Exit condition: {exit_cond}")
    
    def test_get_monitoring_metadata(self, strategy):
        """Test monitoring metadata."""
        metadata = strategy.get_monitoring_metadata()
        
        assert metadata["type"] == "price_level"
        assert "enable_position_tightening" in metadata
        assert "enable_sl_tightening" in metadata
        print(f"✓ Monitoring metadata: {metadata}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

