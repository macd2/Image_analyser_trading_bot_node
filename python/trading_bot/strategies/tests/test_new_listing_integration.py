"""
Integration tests for NewListingStrategy with trading engine.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../'))

import pytest
import asyncio
from unittest.mock import Mock, patch
from trading_bot.strategies.new_listing.new_listing_strategy import NewListingStrategy
from trading_bot.strategies import StrategyFactory


class TestNewListingIntegration:
    """Test NewListingStrategy integration with trading engine."""
    
    @pytest.fixture
    def config(self):
        """Create mock config."""
        config = Mock()
        config.bybit = Mock()
        config.bybit.circuit_breaker = Mock(
            error_threshold=5,
            recovery_timeout=300,
            max_recv_window=300000,
            backoff_multiplier=2.0,
            jitter_range=0.1
        )
        config.bybit.recv_window = 5000
        return config
    
    def test_strategy_registered_in_factory(self):
        """Test strategy is registered in factory."""
        assert StrategyFactory.is_strategy_registered("NewListingStrategy")
        assert "NewListingStrategy" in StrategyFactory.STRATEGIES
        print("✓ Strategy registered in factory")
    
    def test_strategy_instantiation(self, config):
        """Test strategy can be instantiated."""
        strategy = NewListingStrategy(config=config, testnet=True)
        assert strategy is not None
        assert strategy.STRATEGY_TYPE == "price_based"
        assert strategy.STRATEGY_NAME == "NewListingStrategy"
        print("✓ Strategy instantiated successfully")
    
    def test_strategy_output_format(self, config):
        """Test strategy output format matches contract."""
        strategy = NewListingStrategy(config=config, testnet=True)
        
        # Create a mock recommendation
        rec = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.75,
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 130.0,
            "risk_reward": 6.0,
            "setup_quality": 0.8,
            "position_size_multiplier": 1.0,
            "market_environment": 0.7,
            "analysis": {
                "strategy": "new_listing",
                "listing_symbol": "BTCUSDT",
            },
            "chart_path": "",
            "timeframe": "1h",
            "cycle_id": "test-cycle",
        }
        
        # Validate signal
        assert strategy.validate_signal(rec) is True
        
        # Calculate risk metrics
        metrics = strategy.calculate_risk_metrics(rec)
        assert "risk_per_unit" in metrics
        assert "rr_ratio" in metrics
        
        print("✓ Strategy output format valid")
    
    def test_strategy_exit_logic(self, config):
        """Test strategy exit logic works correctly."""
        strategy = NewListingStrategy(config=config, testnet=True)

        # Test TP exit - static TP in Phase 1
        trade_tp = {
            "symbol": "TESTUSDT",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 105.0,  # Lower static TP for Phase 1
            "meta": {
                "phase": 1,
                "stop": 92.0,
                "highest": 100.0,
                "candles": [],
            },
        }
        candle_tp = {"close": 105.5, "open": 100.0, "high": 106.0, "low": 99.0}
        with patch.object(strategy, '_get_current_price', return_value=105.5):
            result = asyncio.run(strategy.should_exit(trade_tp, candle_tp))
        assert result["should_exit"] is True
        assert result["exit_details"]["reason"] == "take_profit_hit"

        # Test SL exit
        trade_sl = {
            "symbol": "TESTUSDT",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 130.0,
            "meta": {
                "phase": 1,
                "stop": 92.0,
                "highest": 100.0,
                "candles": [],
            },
        }
        candle_sl = {"close": 91.0, "open": 92.0, "high": 93.0, "low": 90.0}
        with patch.object(strategy, '_get_current_price', return_value=91.0):
            result = asyncio.run(strategy.should_exit(trade_sl, candle_sl))
        assert result["should_exit"] is True
        assert result["exit_details"]["reason"] == "trailing_stop_hit"

        # Test no exit
        trade_no_exit = {
            "symbol": "TESTUSDT",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 130.0,
            "meta": {
                "phase": 1,
                "stop": 92.0,
                "highest": 100.0,
                "candles": [],
            },
        }
        candle_mid = {"close": 110.0, "open": 105.0, "high": 111.0, "low": 104.0}
        with patch.object(strategy, '_get_current_price', return_value=110.0):
            result = asyncio.run(strategy.should_exit(trade_no_exit, candle_mid))
        assert result["should_exit"] is False

        print("✓ Strategy exit logic works correctly")
    
    def test_strategy_required_settings(self):
        """Test strategy provides required settings schema."""
        settings = NewListingStrategy.get_required_settings()
        assert isinstance(settings, dict)
        assert "enable_trailing_stop" in settings
        assert "trailing_stop_config" in settings
        print("✓ Strategy provides required settings")
    
    def test_strategy_monitoring_metadata(self, config):
        """Test strategy provides monitoring metadata."""
        strategy = NewListingStrategy(config=config, testnet=True)
        metadata = strategy.get_monitoring_metadata()
        
        assert "entry_price" in metadata
        assert "stop_loss" in metadata
        assert "take_profit" in metadata
        assert "trailing_stop_enabled" in metadata
        
        print("✓ Strategy provides monitoring metadata")

