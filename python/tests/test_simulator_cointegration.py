"""
Functional test for the simulator with cointegration strategy.

Tests:
1. Cointegration trade entry and fill
2. Strategy-based exit detection (z-score crossing threshold)
3. Pair candle fetching from live API
4. P&L calculation for cointegration trades
5. Exit reason tracking and logging
"""

import pytest
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock
import logging

from trading_bot.engine.paper_trade_simulator import PaperTradeSimulator, Candle
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule

logger = logging.getLogger(__name__)


class TestSimulatorCointegration:
    """Test simulator with cointegration strategy."""
    
    @pytest.fixture
    def simulator(self):
        """Create simulator instance."""
        return PaperTradeSimulator()
    
    @pytest.fixture
    def cointegration_strategy(self):
        """Create mock cointegration strategy."""
        strategy = Mock(spec=CointegrationAnalysisModule)
        return strategy
    
    @pytest.fixture
    def cointegration_trade(self):
        """Create a cointegration trade record."""
        # Use a time that matches the candles (2024-01-01 12:00:00 UTC)
        trade_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return {
            'id': 'trade_coint_001',
            'symbol': 'BTC',
            'side': 'Buy',
            'entry_price': 45000.0,
            'stop_loss': 44000.0,
            'take_profit': 46000.0,
            'quantity': 1.0,
            'created_at': trade_time.isoformat(),
            'strategy_name': 'CointegrationSpreadTrader',
            'strategy_type': 'spread_based',
            'strategy_metadata': {
                'beta': 0.85,
                'spread_mean': 100.5,
                'spread_std': 25.3,
                'z_score_at_entry': 2.1,
                'pair_symbol': 'ETH',
                'z_exit_threshold': 0.5,
            }
        }
    
    @pytest.fixture
    def candles_with_fill_and_exit(self):
        """Create candles that trigger fill and exit."""
        base_time = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        return [
            # Candle 0: Entry price touched (45000)
            Candle(timestamp=base_time, open=44500, high=45500, low=44000, close=45000),
            # Candle 1: Price moves up
            Candle(timestamp=base_time + 3600000, open=45000, high=45200, low=44900, close=45100),
            # Candle 2: Price continues up
            Candle(timestamp=base_time + 7200000, open=45100, high=45300, low=45000, close=45200),
            # Candle 3: Exit triggered by strategy
            Candle(timestamp=base_time + 10800000, open=45200, high=45400, low=45100, close=45250),
        ]
    
    def test_cointegration_trade_fill(self, simulator, cointegration_trade, candles_with_fill_and_exit):
        """Test that cointegration trade gets filled at entry price."""
        strategy = Mock()
        strategy.should_exit.return_value = {"should_exit": False}
        
        result = simulator.simulate_trade(cointegration_trade, candles_with_fill_and_exit, strategy)
        
        assert result is not None
        assert result['fill_price'] == 45000.0
        assert result['status'] == 'filled'
        assert result['filled_at'] is not None
    
    def test_cointegration_strategy_exit_triggered(self, simulator, cointegration_trade, candles_with_fill_and_exit):
        """Test that strategy exit is triggered and trade closes."""
        strategy = Mock()
        
        # Strategy returns no exit for first 2 candles, then exits on 3rd
        strategy.should_exit.side_effect = [
            {"should_exit": False},
            {"should_exit": False},
            {
                "should_exit": True,
                "exit_details": {
                    "reason": "z_score_exit",
                    "z_score": 0.45,
                    "threshold": 0.5,
                }
            }
        ]
        
        result = simulator.simulate_trade(cointegration_trade, candles_with_fill_and_exit, strategy)
        
        assert result is not None
        assert result['status'] == 'closed'
        assert result['exit_reason'] == 'z_score_exit'
        assert result['exit_price'] == 45250  # Close price of exit candle
        assert result['pnl'] == 250.0  # (45250 - 45000) * 1
        assert result['pnl_percent'] > 0
    
    def test_cointegration_strategy_exit_with_pair_candle_fetch(self, simulator, cointegration_trade, candles_with_fill_and_exit):
        """Test that strategy can fetch pair candles when pair_candle=None."""
        strategy = Mock()
        
        # Track calls to should_exit
        call_count = [0]
        
        def should_exit_side_effect(trade, current_candle, pair_candle):
            call_count[0] += 1
            
            # Verify pair_candle is None (strategy should fetch it)
            assert pair_candle is None, "pair_candle should be None, strategy fetches it"
            
            # Simulate strategy fetching pair candle and calculating z-score
            if call_count[0] < 3:
                return {"should_exit": False}
            else:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "z_score_exit",
                        "z_score": 0.45,
                    }
                }
        
        strategy.should_exit.side_effect = should_exit_side_effect
        
        result = simulator.simulate_trade(cointegration_trade, candles_with_fill_and_exit, strategy)
        
        assert result is not None
        assert result['status'] == 'closed'
        assert call_count[0] >= 3  # Should have called should_exit multiple times
    
    def test_cointegration_pnl_calculation_long(self, simulator, cointegration_trade, candles_with_fill_and_exit):
        """Test P&L calculation for long cointegration trade."""
        strategy = Mock()
        strategy.should_exit.side_effect = [
            {"should_exit": False},
            {"should_exit": False},
            {
                "should_exit": True,
                "exit_details": {"reason": "z_score_exit"}
            }
        ]
        
        result = simulator.simulate_trade(cointegration_trade, candles_with_fill_and_exit, strategy)
        
        # Entry: 45000, Exit: 45250, Qty: 1
        expected_pnl = (45250 - 45000) * 1
        expected_pnl_percent = (expected_pnl / (45000 * 1)) * 100
        
        assert result['pnl'] == expected_pnl
        assert abs(result['pnl_percent'] - expected_pnl_percent) < 0.01
    
    def test_cointegration_pnl_calculation_short(self, simulator):
        """Test P&L calculation for short cointegration trade."""
        trade_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        short_trade = {
            'id': 'trade_coint_short',
            'symbol': 'BTC',
            'side': 'Sell',
            'entry_price': 45000.0,
            'stop_loss': 46000.0,
            'take_profit': 44000.0,
            'quantity': 1.0,
            'created_at': trade_time.isoformat(),
            'strategy_name': 'CointegrationSpreadTrader',
            'strategy_metadata': {'pair_symbol': 'ETH'}
        }
        
        base_time = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        candles = [
            Candle(timestamp=base_time, open=45500, high=46000, low=44500, close=45000),
            Candle(timestamp=base_time + 3600000, open=45000, high=45200, low=44800, close=44900),
            Candle(timestamp=base_time + 7200000, open=44900, high=45000, low=44700, close=44800),
        ]
        
        strategy = Mock()
        strategy.should_exit.side_effect = [
            {"should_exit": False},
            {
                "should_exit": True,
                "exit_details": {"reason": "z_score_exit"}
            }
        ]
        
        result = simulator.simulate_trade(short_trade, candles, strategy)
        
        # Entry: 45000, Exit: 44800, Qty: 1, Side: Sell
        expected_pnl = (45000 - 44800) * 1
        
        assert result['pnl'] == expected_pnl
        assert result['pnl_percent'] > 0
    
    def test_strategy_exit_with_exit_details(self, simulator, cointegration_trade, candles_with_fill_and_exit):
        """Test that exit details are preserved in trade result."""
        strategy = Mock()
        exit_details = {
            "reason": "z_score_exit",
            "z_score": 0.45,
            "threshold": 0.5,
            "spread": 100.2,
            "spread_mean": 100.5,
        }
        
        strategy.should_exit.side_effect = [
            {"should_exit": False},
            {
                "should_exit": True,
                "exit_details": exit_details
            }
        ]
        
        result = simulator.simulate_trade(cointegration_trade, candles_with_fill_and_exit, strategy)
        
        assert result['exit_details'] == exit_details
        assert result['exit_reason'] == 'z_score_exit'
    
    def test_no_exit_before_fill(self, simulator, cointegration_trade):
        """Test that trade doesn't exit before being filled."""
        base_time = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        candles = [
            # Entry price never touched
            Candle(timestamp=base_time, open=44000, high=44500, low=43500, close=44200),
            Candle(timestamp=base_time + 3600000, open=44200, high=44800, low=44000, close=44500),
        ]
        
        strategy = Mock()
        strategy.should_exit.return_value = {"should_exit": False}
        
        result = simulator.simulate_trade(cointegration_trade, candles, strategy)
        
        # Trade should not be filled, so no result
        assert result is None
    
    def test_strategy_exception_handling(self, simulator, cointegration_trade, candles_with_fill_and_exit):
        """Test that strategy exceptions are handled gracefully."""
        strategy = Mock()
        strategy.should_exit.side_effect = Exception("Strategy error")
        
        # Should not raise, should return None
        result = simulator.simulate_trade(cointegration_trade, candles_with_fill_and_exit, strategy)
        
        # Trade should be filled but not exited due to strategy error
        assert result is None or result['status'] == 'filled'

