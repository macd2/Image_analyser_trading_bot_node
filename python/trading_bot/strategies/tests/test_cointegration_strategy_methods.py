"""
Test CointegrationAnalysisModule implementation of abstract methods.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../'))

import pytest
from unittest.mock import Mock
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule


class TestCointegrationStrategyMethods:
    """Test CointegrationAnalysisModule method implementations."""
    
    @pytest.fixture
    def strategy(self):
        """Create a CointegrationAnalysisModule instance for testing."""
        config = Mock()
        return CointegrationAnalysisModule(config=config)
    
    def test_strategy_type_and_name(self, strategy):
        """Test strategy type and name are set correctly."""
        assert strategy.STRATEGY_TYPE == "spread_based"
        assert strategy.STRATEGY_NAME == "CointegrationAnalysisModule"
        assert strategy.STRATEGY_VERSION == "1.0"
        print("✓ Strategy type, name, and version set correctly")
    
    def test_validate_signal_long_valid(self, strategy):
        """Test validation of valid long spread signal."""
        signal = {
            "z_score": 2.5,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
        }
        
        assert strategy.validate_signal(signal) is True
        print("✓ Valid long spread signal passes validation")
    
    def test_validate_signal_short_valid(self, strategy):
        """Test validation of valid short spread signal."""
        signal = {
            "z_score": -2.5,
            "entry_price": 100.0,
            "stop_loss": 101.0,
            "take_profit": 98.0,
        }
        
        assert strategy.validate_signal(signal) is True
        print("✓ Valid short spread signal passes validation")
    
    def test_validate_signal_low_z_distance(self, strategy):
        """Test that low z-score distance fails validation."""
        signal = {
            "z_score": 0.2,  # Below default min_z_distance of 0.5
            "entry_price": 100.0,
            "stop_loss": 99.5,
            "take_profit": 100.5,
        }
        
        with pytest.raises(ValueError, match="Z-score distance"):
            strategy.validate_signal(signal)
        
        print("✓ Low z-score distance fails validation")
    
    def test_validate_signal_wrong_order(self, strategy):
        """Test that wrong price order fails validation."""
        signal = {
            "z_score": 2.0,
            "entry_price": 100.0,
            "stop_loss": 101.0,  # Should be below entry for long
            "take_profit": 102.0,
        }
        
        with pytest.raises(ValueError, match="wrong order"):
            strategy.validate_signal(signal)
        
        print("✓ Wrong price order fails validation")
    
    def test_calculate_risk_metrics_long(self, strategy):
        """Test risk metrics calculation for long spread."""
        signal = {
            "z_score": 2.5,
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
        }
        
        metrics = strategy.calculate_risk_metrics(signal)
        
        assert metrics["z_score"] == 2.5
        assert metrics["z_distance_to_sl"] == 2.5
        assert metrics["risk_per_unit"] == 2.0
        assert metrics["reward_per_unit"] == 4.0
        assert metrics["risk_reward_ratio"] == 2.0
        print(f"✓ Long spread risk metrics: {metrics}")
    
    def test_calculate_risk_metrics_short(self, strategy):
        """Test risk metrics calculation for short spread."""
        signal = {
            "z_score": -2.5,
            "entry_price": 100.0,
            "stop_loss": 102.0,
            "take_profit": 96.0,
        }
        
        metrics = strategy.calculate_risk_metrics(signal)
        
        assert metrics["z_score"] == -2.5
        assert metrics["z_distance_to_sl"] == 2.5
        assert metrics["risk_per_unit"] == 2.0
        assert metrics["reward_per_unit"] == 4.0
        assert metrics["risk_reward_ratio"] == 2.0
        print(f"✓ Short spread risk metrics: {metrics}")
    
    def test_get_exit_condition(self, strategy):
        """Test exit condition metadata."""
        exit_cond = strategy.get_exit_condition()
        
        assert exit_cond["type"] == "z_score"
        assert "z_exit" in exit_cond
        assert "description" in exit_cond
        print(f"✓ Exit condition: {exit_cond}")
    
    def test_get_monitoring_metadata(self, strategy):
        """Test monitoring metadata."""
        metadata = strategy.get_monitoring_metadata()
        
        assert metadata["type"] == "z_score"
        assert "z_exit" in metadata
        assert "enable_spread_monitoring" in metadata
        assert "z_score_monitoring_interval" in metadata
        print(f"✓ Monitoring metadata: {metadata}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

