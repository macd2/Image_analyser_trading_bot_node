"""
Test suite for the pluggable strategy system.

Tests:
1. StrategyFactory strategy registration and creation
2. CandleAdapter initialization
3. Strategy output format validation
4. Instance-specific configuration loading
"""

import pytest
import json
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock

# Import strategy system
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.strategies.candle_adapter import CandleAdapter
from trading_bot.strategies.factory import StrategyFactory
from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
from trading_bot.strategies.alex.alex_analysis_module import AlexAnalysisModule


class TestStrategyFactory:
    """Test StrategyFactory strategy registration and creation."""

    def test_strategies_are_registered(self):
        """Test that all strategies are registered with correct names."""
        strategies = StrategyFactory.get_available_strategies()

        # Check that all expected strategies are registered
        assert "AiImageAnalyzer" in strategies
        assert "MarketStructure" in strategies
        assert "CointegrationSpreadTrader" in strategies

        # Verify they map to correct classes
        assert strategies["AiImageAnalyzer"] == PromptStrategy
        assert strategies["MarketStructure"] == AlexAnalysisModule
        assert strategies["CointegrationSpreadTrader"] == CointegrationAnalysisModule

    def test_is_strategy_registered(self):
        """Test checking if strategy is registered."""
        # MarketStructure should be registered (not "alex")
        assert StrategyFactory.is_strategy_registered("MarketStructure")
        assert StrategyFactory.is_strategy_registered("AiImageAnalyzer")
        assert StrategyFactory.is_strategy_registered("CointegrationSpreadTrader")

        # Non-existent strategy should not be registered
        assert not StrategyFactory.is_strategy_registered("nonexistent")

    def test_get_available_strategies(self):
        """Test getting available strategies."""
        strategies = StrategyFactory.get_available_strategies()

        assert isinstance(strategies, dict)
        assert len(strategies) >= 3  # At least 3 strategies

        # Check strategy names match current registration
        assert "MarketStructure" in strategies
        assert "AiImageAnalyzer" in strategies
        assert "CointegrationSpreadTrader" in strategies
    



class TestStrategyMetadata:
    """Test strategy metadata and class attributes."""

    def test_prompt_strategy_has_metadata(self):
        """Test PromptStrategy has required metadata."""
        # Check class attributes without instantiation
        assert hasattr(PromptStrategy, 'STRATEGY_TYPE')
        assert hasattr(PromptStrategy, 'STRATEGY_NAME')
        assert hasattr(PromptStrategy, 'STRATEGY_VERSION')
        assert PromptStrategy.STRATEGY_TYPE == "price_based"
        assert PromptStrategy.STRATEGY_NAME == "PromptStrategy"

    def test_cointegration_strategy_has_metadata(self):
        """Test CointegrationAnalysisModule has required metadata."""
        # Check class attributes without instantiation
        assert hasattr(CointegrationAnalysisModule, 'STRATEGY_TYPE')
        assert hasattr(CointegrationAnalysisModule, 'STRATEGY_NAME')
        assert hasattr(CointegrationAnalysisModule, 'STRATEGY_VERSION')
        assert CointegrationAnalysisModule.STRATEGY_TYPE == "spread_based"
        assert CointegrationAnalysisModule.STRATEGY_NAME == "CointegrationAnalysisModule"

    def test_all_strategies_inherit_from_base(self):
        """Test all strategies inherit from BaseAnalysisModule."""
        assert issubclass(PromptStrategy, BaseAnalysisModule)
        assert issubclass(CointegrationAnalysisModule, BaseAnalysisModule)
        assert issubclass(AlexAnalysisModule, BaseAnalysisModule)


class TestCandleAdapter:
    """Test CandleAdapter initialization."""

    def test_candle_adapter_initialization(self):
        """Test CandleAdapter initialization."""
        adapter = CandleAdapter(instance_id="test-1")

        # Verify instance_id is set
        assert adapter.instance_id == "test-1"

        # Verify logger is initialized
        assert adapter.logger is not None

        # Verify internal state is initialized
        assert adapter._available_symbols is None
        assert adapter._symbols_fetched_at == 0


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

