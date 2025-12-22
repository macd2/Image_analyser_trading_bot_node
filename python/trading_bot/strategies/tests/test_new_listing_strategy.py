"""
Test NewListingStrategy implementation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../'))

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from trading_bot.strategies.new_listing.new_listing_strategy import NewListingStrategy


class TestNewListingStrategy:
    """Test NewListingStrategy implementation."""
    
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
    
    @pytest.fixture
    def strategy(self, config):
        """Create NewListingStrategy instance."""
        return NewListingStrategy(config=config, testnet=True)
    
    def test_strategy_properties(self, strategy):
        """Test strategy type, name, and version."""
        assert strategy.STRATEGY_TYPE == "price_based"
        assert strategy.STRATEGY_NAME == "NewListingStrategy"
        assert strategy.STRATEGY_VERSION == "1.0"
        print("✓ Strategy properties correct")
    
    def test_default_config(self, strategy):
        """Test default configuration values."""
        config = strategy.DEFAULT_CONFIG
        assert config["fixed_position_size_usd"] == 100.0
        assert config["stop_loss_percent"] == 5.0
        assert config["take_profit_percent"] == 30.0
        assert config["max_candles_after_listing"] == 5
        assert config["candle_fetch_limit"] == 20
        assert config["announcement_lookback_hours"] == 28
        assert config["timeframe"] == "5m"
        assert config["confidence"] == 0.75
        print("✓ Default config values correct")
    
    def test_validate_signal_valid(self, strategy):
        """Test validation of valid signal."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 130.0,
        }
        assert strategy.validate_signal(signal) is True
        print("✓ Valid signal passes validation")
    
    def test_validate_signal_missing_fields(self, strategy):
        """Test validation fails with missing fields."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 95.0,
        }
        assert strategy.validate_signal(signal) is False
        print("✓ Missing fields fail validation")
    
    def test_validate_signal_invalid_sl(self, strategy):
        """Test validation fails when SL >= entry."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 100.0,
            "take_profit": 130.0,
        }
        assert strategy.validate_signal(signal) is False
        print("✓ Invalid SL fails validation")
    
    def test_validate_signal_invalid_tp(self, strategy):
        """Test validation fails when TP <= entry."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 100.0,
        }
        assert strategy.validate_signal(signal) is False
        print("✓ Invalid TP fails validation")
    
    def test_calculate_risk_metrics(self, strategy):
        """Test risk metrics calculation."""
        signal = {
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 130.0,
        }
        metrics = strategy.calculate_risk_metrics(signal)
        assert metrics["risk_per_unit"] == 5.0
        assert metrics["rr_ratio"] == 6.0  # (130-100)/(100-95) = 30/5 = 6
        assert metrics["risk_percent"] == 5.0
        print("✓ Risk metrics calculated correctly")
    
    def test_get_exit_condition(self, strategy):
        """Test exit condition metadata."""
        exit_cond = strategy.get_exit_condition()
        assert exit_cond["type"] == "price_level"
        assert exit_cond["trailing_stop_enabled"] is True
        assert "trailing_stop_config" in exit_cond
        print("✓ Exit condition metadata correct")
    
    def test_should_exit_tp_touched(self, strategy):
        """Test exit when static TP is touched in Phase 1."""
        trade = {
            "symbol": "TESTUSDT",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 105.0,  # Static TP at 105
            "meta": {
                "phase": 1,  # Phase 1 - no dynamic TP
                "stop": 92.0,
                "highest": 100.0,
                "candles": [],
            },
        }
        # In Phase 1, only static TP is used (no dynamic TP)
        # So price >= 105 should trigger exit
        candle = {"close": 105.5, "open": 100.0, "high": 106.0, "low": 99.0}

        # Mock the _get_current_price method
        with patch.object(strategy, '_get_current_price', return_value=105.5):
            result = asyncio.run(strategy.should_exit(trade, candle))
        assert result["should_exit"] is True
        assert result["exit_details"]["reason"] == "take_profit_hit"
        print("✓ Exit on TP touched")

    def test_should_exit_sl_touched(self, strategy):
        """Test exit when SL is touched (trailing stop)."""
        trade = {
            "symbol": "TESTUSDT",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 130.0,
            "meta": {
                "phase": 1,
                "stop": 92.0,  # 8% below entry
                "highest": 100.0,
                "candles": [],
            },
        }
        candle = {"close": 91.0, "open": 92.0, "high": 93.0, "low": 90.0}

        # Mock the _get_current_price method
        with patch.object(strategy, '_get_current_price', return_value=91.0):
            result = asyncio.run(strategy.should_exit(trade, candle))
        assert result["should_exit"] is True
        assert result["exit_details"]["reason"] == "trailing_stop_hit"
        print("✓ Exit on SL touched")

    def test_should_exit_no_exit(self, strategy):
        """Test no exit when price is between SL and TP."""
        trade = {
            "symbol": "TESTUSDT",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 130.0,
            "meta": {},
        }
        candle = {"close": 110.0, "open": 105.0, "high": 111.0, "low": 104.0}

        # Mock the _get_current_price method
        with patch.object(strategy, '_get_current_price', return_value=110.0):
            result = asyncio.run(strategy.should_exit(trade, candle))
        assert result["should_exit"] is False
        assert result["exit_details"]["reason"] == "no_exit"
        print("✓ No exit when price between SL and TP")
    
    def test_extract_symbol_from_title(self, strategy):
        """Test symbol extraction from announcement title."""
        # Test with real Bybit announcement format
        title = "New Listing : RAVEUSDT Perpetual Contract in Innovation Zone, with up to 25x leverage"
        symbol = strategy._extract_symbol_from_title(title)
        assert symbol == "RAVEUSDT"
        print("✓ Symbol extracted correctly")
    
    def test_extract_symbol_no_match(self, strategy):
        """Test symbol extraction with no match."""
        title = "Some announcement without symbol"
        symbol = strategy._extract_symbol_from_title(title)
        assert symbol is None
        print("✓ No symbol extracted when not found")
    
    def test_get_monitoring_metadata(self, strategy):
        """Test monitoring metadata."""
        metadata = strategy.get_monitoring_metadata()
        assert "entry_price" in metadata
        assert "stop_loss" in metadata
        assert "take_profit" in metadata
        assert metadata["trailing_stop_enabled"] is True
        print("✓ Monitoring metadata correct")

    def test_get_current_price_success(self, strategy):
        """Test fetching current price successfully."""
        # Mock the API response
        strategy.api_manager.get_tickers = Mock(return_value={
            "retCode": 0,
            "result": {
                "list": [
                    {"lastPrice": "0.002995"}
                ]
            }
        })

        price = asyncio.run(strategy._get_current_price("COMMONUSDT"))
        assert price == 0.002995
        print("✓ Current price fetched successfully")

    def test_get_current_price_api_error(self, strategy):
        """Test handling of API error when fetching price."""
        # Mock API error response
        strategy.api_manager.get_tickers = Mock(return_value={
            "retCode": -1,
            "retMsg": "API Error"
        })

        price = asyncio.run(strategy._get_current_price("COMMONUSDT"))
        assert price is None
        print("✓ API error handled correctly")

    def test_get_current_price_invalid_price(self, strategy):
        """Test handling of invalid price (zero or negative)."""
        # Mock response with zero price
        strategy.api_manager.get_tickers = Mock(return_value={
            "retCode": 0,
            "result": {
                "list": [
                    {"lastPrice": "0"}
                ]
            }
        })

        price = asyncio.run(strategy._get_current_price("COMMONUSDT"))
        assert price is None
        print("✓ Invalid price handled correctly")

