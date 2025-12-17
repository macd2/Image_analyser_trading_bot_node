"""
Tests for trading engine strategy-specific signal validation.
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from trading_bot.engine.trading_engine import TradingEngine
from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule


class TestTradingEngineStrategyValidation:
    """Test trading engine with strategy-specific validation."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.trading.min_rr = 1.5
        config.trading.min_confidence_threshold = 0.5
        config.trading.risk_percentage = 2.0
        config.trading.use_kelly_criterion = False
        config.trading.leverage = 1
        config.trading.min_position_value_usd = 0
        config.trading.max_loss_usd = 1000
        config.trading.use_enhanced_position_sizing = False
        return config

    @pytest.fixture
    def mock_engine(self, mock_config):
        """Create mock trading engine."""
        with patch('trading_bot.engine.trading_engine.get_connection'):
            with patch('trading_bot.engine.trading_engine.StateManager'):
                with patch('trading_bot.engine.trading_engine.OrderExecutor'):
                    with patch('trading_bot.engine.trading_engine.PositionSizer'):
                        engine = TradingEngine(config=mock_config, paper_trading=True)
                        engine.order_executor.get_wallet_balance = Mock(return_value={"available": 10000})
                        engine.position_sizer.calculate_position_size = Mock(return_value={
                            "position_size": 1.0,
                            "risk_amount": 100,
                            "position_size_usd": 1000,
                            "risk_amount_usd": 100,
                            "risk_percentage": 1.0,
                            "confidence_weight": 1.0,
                            "risk_per_unit": 100,
                            "sizing_method": "fixed",
                            "risk_pct_used": 2.0,
                        })
                        engine.can_open_trade = Mock(return_value={"can_trade": True})
                        return engine

    def test_execute_signal_with_price_based_strategy_valid(self, mock_engine):
        """Test signal execution with valid price-based strategy signal."""
        strategy = Mock(spec=PromptStrategy)
        strategy.validate_signal = Mock(return_value={"valid": True})
        
        signal = {
            "recommendation": "LONG",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "confidence": 0.8,
            "strategy_uuid": "test-uuid",
            "strategy_type": "price_based",
            "strategy_name": "PromptStrategy",
        }
        
        result = mock_engine.execute_signal(
            symbol="BTCUSDT",
            signal=signal,
            strategy=strategy
        )
        
        # Should call strategy validation
        strategy.validate_signal.assert_called_once_with(signal)
        
        # Should not be rejected
        assert result["status"] != "rejected"

    def test_execute_signal_with_price_based_strategy_invalid(self, mock_engine):
        """Test signal execution with invalid price-based strategy signal."""
        strategy = Mock(spec=PromptStrategy)
        strategy.validate_signal = Mock(return_value={
            "valid": False,
            "error": "RR ratio 0.5 below minimum 1.5"
        })
        
        signal = {
            "recommendation": "LONG",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 102.5,  # Low RR
            "confidence": 0.8,
            "strategy_uuid": "test-uuid",
            "strategy_type": "price_based",
            "strategy_name": "PromptStrategy",
        }
        
        result = mock_engine.execute_signal(
            symbol="BTCUSDT",
            signal=signal,
            strategy=strategy
        )
        
        # Should be rejected
        assert result["status"] == "rejected"
        assert "RR ratio" in result["error"]

    def test_execute_signal_with_spread_based_strategy_valid(self, mock_engine):
        """Test signal execution with valid spread-based strategy signal."""
        strategy = Mock(spec=CointegrationAnalysisModule)
        strategy.validate_signal = Mock(return_value={"valid": True})
        
        signal = {
            "recommendation": "LONG",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "confidence": 0.8,
            "strategy_uuid": "test-uuid",
            "strategy_type": "spread_based",
            "strategy_name": "CointegrationAnalysisModule",
            "z_score": 2.5,
            "z_exit": 0.5,
        }
        
        result = mock_engine.execute_signal(
            symbol="BTCUSDT",
            signal=signal,
            strategy=strategy
        )
        
        # Should call strategy validation
        strategy.validate_signal.assert_called_once_with(signal)
        
        # Should not be rejected
        assert result["status"] != "rejected"

    def test_execute_signal_without_strategy_fallback(self, mock_engine):
        """Test signal execution without strategy (fallback validation)."""
        signal = {
            "recommendation": "LONG",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "confidence": 0.8,
        }
        
        result = mock_engine.execute_signal(
            symbol="BTCUSDT",
            signal=signal,
            strategy=None  # No strategy provided
        )
        
        # Should not be rejected (fallback validation passes)
        assert result["status"] != "rejected"

    def test_execute_signal_without_strategy_missing_prices(self, mock_engine):
        """Test signal execution without strategy and missing prices."""
        signal = {
            "recommendation": "LONG",
            "entry_price": 100.0,
            # Missing stop_loss and take_profit
            "confidence": 0.8,
        }
        
        result = mock_engine.execute_signal(
            symbol="BTCUSDT",
            signal=signal,
            strategy=None
        )
        
        # Should be rejected
        assert result["status"] == "rejected"
        assert "Missing entry, TP, or SL price" in result["error"]

