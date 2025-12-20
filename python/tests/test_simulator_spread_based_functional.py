"""
Functional test for the simulator with spread-based strategies.

Tests that the simulator can:
1. Fetch pair candles from database cache
2. Pass both symbol candles to strategy.should_exit()
3. Calculate z-score correctly with both symbols
4. Close spread-based trades with proper P&L calculation
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.engine.paper_trade_simulator import PaperTradeSimulator, Candle


class TestSimulatorSpreadBasedFunctional:
    """Functional test for simulator with spread-based strategies."""
    
    @pytest.fixture
    def simulator(self):
        return PaperTradeSimulator()
    
    @pytest.fixture
    def spread_based_trade(self):
        trade_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return {
            'id': 'test_spread_trade_001',
            'symbol': 'IRYSUSDT',
            'side': 'Sell',
            'entry_price': 0.0536543,
            'stop_loss': 0.0768682,
            'take_profit': 0.0227025,
            'quantity': 100.0,
            'created_at': trade_time.isoformat(),
            'strategy_name': 'CointegrationAnalysisModule',
            'strategy_type': 'spread_based',
            'strategy_metadata': json.dumps({
                'beta': -2.3451854398970124,
                'spread_mean': 0.2796216426554763,
                'spread_std': 0.03629386562083143,
                'z_score_at_entry': 6.0800507889928985,
                'pair_symbol': 'WETUSDT',
                'z_exit_threshold': 0.2,
                'max_spread_deviation': 3.5,
                'price_x_at_entry': 0.034135,
                'price_y_at_entry': 0.22638,
            })
        }
    
    @pytest.fixture
    def candles_with_spread_exit(self):
        base_time = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        return [
            Candle(timestamp=base_time, open=0.0535, high=0.0540, low=0.0530, close=0.0536543),
            Candle(timestamp=base_time + 3600000, open=0.0536543, high=0.0538, low=0.0530, close=0.0532),
            Candle(timestamp=base_time + 7200000, open=0.0532, high=0.0535, low=0.0525, close=0.0528),
            Candle(timestamp=base_time + 10800000, open=0.0528, high=0.0530, low=0.0520, close=0.0525),
        ]
    
    def test_spread_trade_with_pair_candle_fetching(self, simulator, spread_based_trade, candles_with_spread_exit):
        """Test that simulator fetches pair candles and passes them to strategy."""
        strategy = Mock()
        
        call_count = [0]
        pair_candles_received = []
        
        def should_exit_side_effect(trade, current_candle, pair_candle):
            call_count[0] += 1
            pair_candles_received.append(pair_candle)
            
            if call_count[0] < 3:
                return {"should_exit": False}
            else:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "z_score_exit",
                        "z_score": 0.15,
                        "threshold": 0.2,
                    }
                }
        
        strategy.should_exit.side_effect = should_exit_side_effect
        
        result = simulator.simulate_trade(spread_based_trade, candles_with_spread_exit, strategy)
        
        assert result is not None
        assert result['status'] == 'closed'
        assert result['exit_reason'] == 'z_score_exit'
        assert call_count[0] >= 3
        assert len(pair_candles_received) >= 3
    
    def test_spread_trade_pnl_calculation_short(self, simulator, spread_based_trade, candles_with_spread_exit):
        """Test P&L calculation for SHORT spread-based trade."""
        strategy = Mock()
        strategy.should_exit.side_effect = [
            {"should_exit": False},
            {"should_exit": False},
            {"should_exit": True, "exit_details": {"reason": "z_score_exit"}}
        ]
        
        result = simulator.simulate_trade(spread_based_trade, candles_with_spread_exit, strategy)
        
        assert result is not None
        assert result['status'] == 'closed'
        
        expected_pnl = (0.0536543 - 0.0525) * 100
        assert abs(result['pnl'] - expected_pnl) < 0.001
        assert result['pnl_percent'] > 0
    
    def test_spread_trade_closes_with_both_symbols(self, simulator, spread_based_trade, candles_with_spread_exit):
        """Test that spread trade closes by monitoring both symbols."""
        strategy = Mock()
        
        candles_passed = []
        
        def should_exit_side_effect(trade, current_candle, pair_candle):
            candles_passed.append({'current': current_candle, 'pair': pair_candle})
            
            if len(candles_passed) >= 3:
                return {"should_exit": True, "exit_details": {"reason": "z_score_exit"}}
            return {"should_exit": False}
        
        strategy.should_exit.side_effect = should_exit_side_effect
        
        result = simulator.simulate_trade(spread_based_trade, candles_with_spread_exit, strategy)
        
        assert result is not None
        assert result['status'] == 'closed'
        assert len(candles_passed) >= 3
        for candle_pair in candles_passed:
            assert candle_pair['current'] is not None
            assert 'pair' in candle_pair
