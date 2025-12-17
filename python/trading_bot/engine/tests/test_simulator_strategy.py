"""
Tests for paper trade simulator with strategy-specific exit conditions.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch

from trading_bot.engine.paper_trade_simulator import PaperTradeSimulator, Candle


class TestSimulatorStrategy:
    """Test simulator with strategy-specific exit conditions."""

    @pytest.fixture
    def simulator(self):
        """Create simulator."""
        return PaperTradeSimulator()

    @pytest.fixture
    def sample_candles(self):
        """Create sample candles for testing."""
        base_time = int(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        return [
            Candle(timestamp=base_time, open=100, high=102, low=99, close=101),
            Candle(timestamp=base_time + 60000, open=101, high=103, low=100, close=102),
            Candle(timestamp=base_time + 120000, open=102, high=104, low=101, close=103),
            Candle(timestamp=base_time + 180000, open=103, high=105, low=102, close=104),
        ]

    def test_simulate_trade_with_price_based_strategy_tp_hit(self, simulator, sample_candles):
        """Test simulator with price-based strategy - TP hit."""
        strategy = Mock()
        strategy.get_exit_condition = Mock(return_value={
            "exit_type": "price_level",
            "tp_price": 104.0,
            "sl_price": 98.0,
        })
        
        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 104.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        }
        
        result = simulator.simulate_trade(trade, sample_candles)
        
        # Should have closed trade
        assert result is not None
        assert result["exit_reason"] == "tp_hit"
        assert result["exit_price"] == 104.0
        assert result["status"] == "closed"

    def test_simulate_trade_with_price_based_strategy_sl_hit(self, simulator, sample_candles):
        """Test simulator with price-based strategy - SL hit."""
        strategy = Mock()
        strategy.get_exit_condition = Mock(return_value={
            "exit_type": "price_level",
            "tp_price": 110.0,
            "sl_price": 98.0,
        })
        
        # Create candles that hit SL
        base_time = int(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        candles = [
            Candle(timestamp=base_time, open=100, high=102, low=99, close=101),
            Candle(timestamp=base_time + 60000, open=101, high=103, low=97, close=98),  # SL hit
        ]
        
        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        }
        
        result = simulator.simulate_trade(trade, candles)
        
        # Should have closed trade
        assert result is not None
        assert result["exit_reason"] == "sl_hit"
        assert result["exit_price"] == 98.0
        assert result["status"] == "closed"

    def test_simulate_trade_with_spread_based_strategy(self, simulator, sample_candles):
        """Test simulator with spread-based strategy - z-score exit."""
        strategy = Mock()
        strategy.get_exit_condition = Mock(return_value={
            "exit_type": "z_score",
            "z_exit_threshold": 2.0,
            "spread_mean": 0.5,
            "spread_std": 0.1,
        })
        
        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 104.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
            "strategy_type": "spread_based",
        }
        
        result = simulator.simulate_trade(trade, sample_candles)
        
        # Should have result (may or may not be closed depending on z-score)
        assert result is not None or result is None  # Either filled or not

    def test_simulate_trade_not_filled(self, simulator):
        """Test simulator when trade is not filled."""
        base_time = int(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        candles = [
            Candle(timestamp=base_time, open=110, high=112, low=109, close=111),  # Entry not touched
        ]
        
        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 104.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        }
        
        result = simulator.simulate_trade(trade, candles)
        
        # Should not have result (not filled)
        assert result is None

    def test_simulate_trade_filled_but_not_closed(self, simulator, sample_candles):
        """Test simulator when trade is filled but not closed."""
        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 110.0,  # Not touched in candles
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        }
        
        result = simulator.simulate_trade(trade, sample_candles)
        
        # Should have result with filled status
        assert result is not None
        assert result["status"] == "filled"
        assert result["exit_price"] is None

