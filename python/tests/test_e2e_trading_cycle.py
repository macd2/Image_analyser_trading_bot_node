"""
End-to-End Trading Cycle Test

Tests the complete flow from strategy analysis through trade execution:
1. Strategy analysis cycle
2. Signal ranking
3. Slot checking
4. Trade execution
5. Position monitoring
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from trading_bot.config.settings_v2 import Config
from trading_bot.engine.trading_cycle import TradingCycle
from trading_bot.strategies.factory import StrategyFactory


class TestE2ETradingCycle:
    """End-to-end trading cycle tests."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock(spec=Config)
        config.trading = Mock()
        config.trading.timeframe = "1h"
        config.trading.max_concurrent_trades = 3
        config.trading.risk_percentage = 0.02
        config.trading.leverage = 10
        config.trading.min_rr = 1.5
        config.paths = Mock()
        config.paths.charts = "data/charts"
        return config
    
    @pytest.fixture
    def mock_execute_signal(self):
        """Create mock execute signal callback."""
        return Mock(return_value={
            "id": "trade_123",
            "status": "submitted",
            "symbol": "BTCUSDT",
        })
    
    def test_trading_cycle_initialization(self, mock_config, mock_execute_signal):
        """Test 1: Trading cycle initializes correctly."""
        cycle = TradingCycle(
            config=mock_config,
            execute_signal_callback=mock_execute_signal,
            testnet=True,
            run_id="test_run_123",
            instance_id="test_instance",
        )
        
        assert cycle.config == mock_config
        assert cycle.execute_signal == mock_execute_signal
        assert cycle.testnet is True
        assert cycle.run_id == "test_run_123"
        assert cycle.instance_id == "test_instance"
        assert cycle._running is False
        print("✓ Test 1 PASSED: Cycle initialization")
    
    def test_trading_cycle_start_stop(self, mock_config, mock_execute_signal):
        """Test 2: Trading cycle start/stop works."""
        cycle = TradingCycle(
            config=mock_config,
            execute_signal_callback=mock_execute_signal,
            testnet=True,
        )
        
        # Start cycle
        cycle.start()
        assert cycle._running is True
        
        # Stop cycle
        cycle.stop()
        assert cycle._running is False
        print("✓ Test 2 PASSED: Cycle start/stop")
    
    def test_strategy_stop_signal_propagation(self, mock_config, mock_execute_signal):
        """Test 3: Stop signal propagates to strategy."""
        cycle = TradingCycle(
            config=mock_config,
            execute_signal_callback=mock_execute_signal,
            testnet=True,
        )
        
        # Create mock strategy
        mock_strategy = Mock()
        mock_strategy.request_stop = Mock()
        cycle.strategy = mock_strategy
        
        # Stop cycle should call strategy.request_stop()
        cycle.stop()
        mock_strategy.request_stop.assert_called_once()
        print("✓ Test 3 PASSED: Stop signal propagation")
    
    def test_signal_validation(self, mock_config, mock_execute_signal):
        """Test 4: Signal validation works."""
        cycle = TradingCycle(
            config=mock_config,
            execute_signal_callback=mock_execute_signal,
            testnet=True,
        )
        
        # Valid signal
        valid_signal = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 52000,
            "confidence": 0.8,
            "risk_reward": 2.0,
        }
        
        # Should not raise
        try:
            cycle._validate_signal(valid_signal)
            print("✓ Test 4a PASSED: Valid signal accepted")
        except Exception as e:
            pytest.fail(f"Valid signal rejected: {e}")
        
        # Invalid signal (wrong order)
        invalid_signal = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "entry_price": 50000,
            "stop_loss": 51000,  # SL > Entry for long
            "take_profit": 52000,
            "confidence": 0.8,
            "risk_reward": 2.0,
        }
        
        # Should raise
        with pytest.raises(ValueError):
            cycle._validate_signal(invalid_signal)
        print("✓ Test 4b PASSED: Invalid signal rejected")
    
    def test_signal_ranking(self, mock_config, mock_execute_signal):
        """Test 5: Signal ranking by quality."""
        cycle = TradingCycle(
            config=mock_config,
            execute_signal_callback=mock_execute_signal,
            testnet=True,
        )
        
        signals = [
            {
                "symbol": "BTCUSDT",
                "recommendation": "BUY",
                "confidence": 0.9,
                "risk_reward": 2.5,
                "setup_quality": 0.8,
                "market_environment": 0.7,
            },
            {
                "symbol": "ETHUSDT",
                "recommendation": "BUY",
                "confidence": 0.7,
                "risk_reward": 1.8,
                "setup_quality": 0.6,
                "market_environment": 0.5,
            },
        ]
        
        ranked = cycle._rank_signals(signals)
        
        # First signal should be BTCUSDT (higher quality)
        assert ranked[0]["symbol"] == "BTCUSDT"
        assert ranked[1]["symbol"] == "ETHUSDT"
        print("✓ Test 5 PASSED: Signal ranking")
    
    def test_slot_checking(self, mock_config, mock_execute_signal):
        """Test 6: Available slots calculation."""
        cycle = TradingCycle(
            config=mock_config,
            execute_signal_callback=mock_execute_signal,
            testnet=True,
        )
        
        # Mock position manager
        cycle.position_manager = Mock()
        cycle.position_manager.get_open_positions = Mock(return_value={
            "BTCUSDT": {"size": 1.0},
            "ETHUSDT": {"size": 2.0},
        })
        
        # Max 3 trades, 2 open = 1 slot available
        slots = cycle._get_available_slots()
        assert slots == 1
        print("✓ Test 6 PASSED: Slot checking")
    
    def test_cycle_error_handling(self, mock_config, mock_execute_signal):
        """Test 7: Cycle error handling."""
        cycle = TradingCycle(
            config=mock_config,
            execute_signal_callback=mock_execute_signal,
            testnet=True,
        )
        
        # Mock strategy to raise error
        mock_strategy = AsyncMock()
        mock_strategy.run_analysis_cycle = AsyncMock(
            side_effect=Exception("Strategy error")
        )
        cycle.strategy = mock_strategy
        
        # Cycle should handle error gracefully
        result = asyncio.run(cycle.run_cycle_async())
        
        assert "errors" in result
        assert len(result["errors"]) > 0
        print("✓ Test 7 PASSED: Error handling")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

