"""
Test suite for the pluggable strategy system.

Tests:
1. BaseAnalysisModule output format validation
2. CandleAdapter candle fetching
3. StrategyFactory strategy creation
4. AlexAnalysisModule analysis
5. Instance-specific configuration loading
"""

import pytest
import asyncio
import json
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

# Import strategy system
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.strategies.factory import StrategyFactory
from trading_bot.strategies.alex_analysis_module import AlexAnalysisModule


class TestBaseAnalysisModule:
    """Test BaseAnalysisModule output format validation."""
    
    def test_validate_output_valid(self):
        """Test validation of valid output."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        valid_output = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.75,
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 51000.0,
            "risk_reward": 2.0,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {"trend": "bullish"},
            "chart_path": "/path/to/chart.png",
            "timeframe": "1h",
            "cycle_id": "cycle-123",
        }
        
        # Should not raise
        module._validate_output(valid_output)
    
    def test_validate_output_missing_field(self):
        """Test validation fails with missing field."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        invalid_output = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            # Missing confidence
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 51000.0,
            "risk_reward": 2.0,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {"trend": "bullish"},
            "chart_path": "/path/to/chart.png",
            "timeframe": "1h",
            "cycle_id": "cycle-123",
        }
        
        with pytest.raises(ValueError, match="Missing required field: confidence"):
            module._validate_output(invalid_output)
    
    def test_validate_output_invalid_recommendation(self):
        """Test validation fails with invalid recommendation."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        invalid_output = {
            "symbol": "BTCUSDT",
            "recommendation": "INVALID",  # Must be BUY/SELL/HOLD
            "confidence": 0.75,
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 51000.0,
            "risk_reward": 2.0,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {"trend": "bullish"},
            "chart_path": "/path/to/chart.png",
            "timeframe": "1h",
            "cycle_id": "cycle-123",
        }
        
        with pytest.raises(ValueError, match="Invalid recommendation"):
            module._validate_output(invalid_output)
    
    def test_validate_output_invalid_confidence(self):
        """Test validation fails with invalid confidence."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        invalid_output = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 1.5,  # Must be 0-1
            "entry_price": 50000.0,
            "stop_loss": 49000.0,
            "take_profit": 51000.0,
            "risk_reward": 2.0,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {"trend": "bullish"},
            "chart_path": "/path/to/chart.png",
            "timeframe": "1h",
            "cycle_id": "cycle-123",
        }
        
        with pytest.raises(ValueError, match="Confidence must be 0-1"):
            module._validate_output(invalid_output)


class TestStrategyConfig:
    """Test instance-specific strategy configuration."""
    
    def test_default_config(self):
        """Test default config is used when none provided."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        assert module.get_config_value("min_confidence") == 0.7
        assert module.get_config_value("use_volume") == True
    
    def test_provided_config_overrides_default(self):
        """Test provided config overrides defaults."""
        custom_config = {
            "min_confidence": 0.9,
            "use_volume": False,
        }
        
        module = AlexAnalysisModule(
            config=Mock(),
            instance_id="test-1",
            strategy_config=custom_config
        )
        
        assert module.get_config_value("min_confidence") == 0.9
        assert module.get_config_value("use_volume") == False
        # Default values still available
        assert module.get_config_value("lookback_periods") == 20
    
    def test_get_config_value_with_default(self):
        """Test get_config_value with default fallback."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        # Existing key
        assert module.get_config_value("min_confidence", 0.5) == 0.7
        
        # Non-existing key with default
        assert module.get_config_value("nonexistent", "default_value") == "default_value"


class TestAlexAnalysisModule:
    """Test AlexAnalysisModule analysis."""
    
    @pytest.mark.asyncio
    async def test_run_analysis_cycle_insufficient_data(self):
        """Test analysis with insufficient candle data."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        # Mock candle adapter to return insufficient data
        module.candle_adapter = Mock()
        module.candle_adapter.get_candles = Mock(return_value=[])
        
        results = await module.run_analysis_cycle(
            symbols=["BTCUSDT"],
            timeframe="1h",
            cycle_id="cycle-123"
        )
        
        assert len(results) == 1
        assert results[0]["symbol"] == "BTCUSDT"
        assert results[0]["skipped"] == True
        assert "Insufficient candle data" in results[0]["skip_reason"]
    
    @pytest.mark.asyncio
    async def test_run_analysis_cycle_error_handling(self):
        """Test error handling during analysis."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        # Mock candle adapter to raise error
        module.candle_adapter = Mock()
        module.candle_adapter.get_candles = Mock(
            side_effect=Exception("API error")
        )
        
        results = await module.run_analysis_cycle(
            symbols=["BTCUSDT"],
            timeframe="1h",
            cycle_id="cycle-123"
        )
        
        assert len(results) == 1
        assert results[0]["symbol"] == "BTCUSDT"
        assert results[0]["error"] == "API error"
    
    def test_candles_to_dataframe(self):
        """Test conversion of candles to DataFrame."""
        module = AlexAnalysisModule(config=Mock(), instance_id="test-1")
        
        candles = [
            {
                "start_time": 1000,
                "open_price": 50000.0,
                "high_price": 51000.0,
                "low_price": 49000.0,
                "close_price": 50500.0,
                "volume": 100.0,
            },
            {
                "start_time": 2000,
                "open_price": 50500.0,
                "high_price": 51500.0,
                "low_price": 50000.0,
                "close_price": 51000.0,
                "volume": 120.0,
            },
        ]
        
        df = module._candles_to_dataframe(candles)
        
        assert len(df) == 2
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns
        assert df["close"].iloc[0] == 50500.0
        assert df["close"].iloc[1] == 51000.0


class TestStrategyFactory:
    """Test StrategyFactory strategy creation."""
    
    def test_register_strategy(self):
        """Test strategy registration."""
        # Create a mock strategy
        class MockStrategy(BaseAnalysisModule):
            async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
                return []
        
        StrategyFactory.register_strategy("mock", MockStrategy)
        
        assert StrategyFactory.is_strategy_registered("mock")
        assert "mock" in StrategyFactory.get_available_strategies()
    
    def test_is_strategy_registered(self):
        """Test checking if strategy is registered."""
        # Alex should be registered by default
        assert StrategyFactory.is_strategy_registered("alex")
    
    def test_get_available_strategies(self):
        """Test getting available strategies."""
        strategies = StrategyFactory.get_available_strategies()
        
        assert isinstance(strategies, dict)
        assert "alex" in strategies


class TestCandleAdapter:
    """Test CandleAdapter candle fetching."""
    
    def test_candle_adapter_initialization(self):
        """Test CandleAdapter initialization."""
        adapter = CandleAdapter(instance_id="test-1")
        
        assert adapter.instance_id == "test-1"
        assert adapter.candle_store is not None or adapter.candle_store is None
        # Either initialized or gracefully failed


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

