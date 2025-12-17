"""
Test strategy UUID generation and abstract methods in BaseAnalysisModule.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../'))

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from trading_bot.strategies.base import BaseAnalysisModule


class ConcreteStrategy(BaseAnalysisModule):
    """Concrete implementation for testing."""
    
    STRATEGY_TYPE = "price_based"
    STRATEGY_NAME = "TestStrategy"
    STRATEGY_VERSION = "1.0"
    DEFAULT_CONFIG = {"test_param": "value"}
    
    async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
        return []
    
    def validate_signal(self, signal):
        return True
    
    def calculate_risk_metrics(self, signal):
        return {"risk_per_unit": 1.0}
    
    def get_exit_condition(self):
        return {"type": "price_level"}
    
    def get_monitoring_metadata(self):
        return {"entry_price": 100}


class TestStrategyUUID:
    """Test strategy UUID generation."""
    
    def test_strategy_uuid_generation(self):
        """Test that strategy UUID is generated deterministically."""
        config = Mock()
        
        # Create two instances with same config
        strategy1 = ConcreteStrategy(config=config)
        strategy2 = ConcreteStrategy(config=config)
        
        # Same config should produce same UUID
        assert strategy1.strategy_uuid == strategy2.strategy_uuid
        print(f"✓ Same config produces same UUID: {strategy1.strategy_uuid}")
    
    def test_strategy_uuid_different_config(self):
        """Test that different configs produce different UUIDs."""
        config = Mock()
        
        # Create instances with different configs
        strategy1 = ConcreteStrategy(config=config, strategy_config={"param": "value1"})
        strategy2 = ConcreteStrategy(config=config, strategy_config={"param": "value2"})
        
        # Different config should produce different UUID
        assert strategy1.strategy_uuid != strategy2.strategy_uuid
        print(f"✓ Different configs produce different UUIDs:")
        print(f"  Config1: {strategy1.strategy_uuid}")
        print(f"  Config2: {strategy2.strategy_uuid}")
    
    def test_strategy_type_and_name_required(self):
        """Test that STRATEGY_TYPE and STRATEGY_NAME are required."""
        
        class IncompleteStrategy(BaseAnalysisModule):
            STRATEGY_TYPE = None  # Missing
            STRATEGY_NAME = "Test"
            
            async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
                return []
            
            def validate_signal(self, signal):
                return True
            
            def calculate_risk_metrics(self, signal):
                return {}
            
            def get_exit_condition(self):
                return {}
            
            def get_monitoring_metadata(self):
                return {}
        
        config = Mock()
        
        with pytest.raises(ValueError, match="STRATEGY_TYPE and STRATEGY_NAME"):
            IncompleteStrategy(config=config)
        
        print("✓ ValueError raised when STRATEGY_TYPE is missing")
    
    def test_abstract_methods_required(self):
        """Test that abstract methods must be implemented."""
        
        class IncompleteImpl(BaseAnalysisModule):
            STRATEGY_TYPE = "price_based"
            STRATEGY_NAME = "Incomplete"
            
            async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
                return []
            
            # Missing: validate_signal, calculate_risk_metrics, etc.
        
        config = Mock()
        
        # Should raise TypeError when trying to instantiate
        with pytest.raises(TypeError):
            IncompleteImpl(config=config)
        
        print("✓ TypeError raised when abstract methods not implemented")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

